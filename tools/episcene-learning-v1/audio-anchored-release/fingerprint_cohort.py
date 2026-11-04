#!/usr/bin/env python3
"""Bounded, shift-invariant audio fingerprint proof of concept: SHADOW ONLY.

Compares cached Chromaprint-like 32-bit fingerprint words without using
episode start/end timestamps as equality keys. It is not an authorization
gate, a release decision, or a production patch.

The strict thresholds here are hypotheses; synthetic tests can check safety
properties but only a server cache replay can show real match coverage.
"""
from __future__ import annotations
from dataclasses import dataclass
import json

MAX_WORDS = 720
MIN_DURATION_MS = 15_000
MAX_HAMMING_BITS_PER_WORD = 8
MIN_GOOD_FRAME_RATIO = 0.90
MAX_MEAN_DIFFERING_BITS = 5.0
MIN_DIVERSE_WORDS = 12


@dataclass(frozen=True)
class Fingerprint:
    words: tuple[int, ...]
    step_ms: int
    offset_ms: int


@dataclass(frozen=True)
class Match:
    target_start_ms: int
    reference_start_ms: int
    length_ms: int
    frame_ratio: float
    mean_bit_error: float
    shift_ms: int


def decode(raw, *, step_ms, offset_ms):
    """Accept only bounded JSON arrays of 32-bit fingerprint words."""
    if type(step_ms) is not int or not 100 <= step_ms <= 2000:
        raise ValueError("bad fingerprint sampling step")
    if type(offset_ms) is not int or offset_ms < 0:
        raise ValueError("bad fingerprint offset")
    if not isinstance(raw, str) or len(raw) > 12 * MAX_WORDS:
        raise ValueError("fingerprint payload too large / invalid")
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as err:
        raise ValueError("invalid fingerprint json") from err
    if not isinstance(data, list) or not 1 <= len(data) <= MAX_WORDS:
        raise ValueError("invalid fingerprint shape")
    if any(type(w) is not int or not -(2**31) <= w < 2**32 for w in data):
        raise ValueError("invalid fingerprint word")
    return Fingerprint(tuple(x & 0xffffffff for x in data), step_ms, offset_ms)


def match(target: Fingerprint, reference: Fingerprint) -> Match | None:
    """Find strongest 15s+ content overlap at ANY relative window position.

    Sample steps MUST match; unmatched sampling cannot produce approval.
    The last criterion checks structural diversity, avoiding silent/flat scenes.
    Return the strongest candidate only; never infer a release decision.
    """
    if target.step_ms != reference.step_ms:
        return None
    step = target.step_ms
    need = (MIN_DURATION_MS + step - 1) // step
    a, b = target.words, reference.words
    if not need <= len(a) <= MAX_WORDS or not need <= len(b) <= MAX_WORDS:
        return None
    best = None
    best_rank = (-1.0, -1, float('-inf'))
    # shift means partner index = target index - shift. No episode-time equality.
    for shift in range(-len(b) + need, len(a) - need + 1):
        ai = max(0, shift)
        bi = max(0, -shift)
        count = min(len(a) - ai, len(b) - bi)
        if count < need:
            continue
        # Compare all local minimum-duration sections to tolerate slight clip
        # differences; at most MAX_WORDS squared under explicit bounds.
        bad = 0
        errors = 0
        diffs = []
        for k in range(count):
            diffs.append((a[ai + k] ^ b[bi + k]).bit_count())
        for k in range(need):
            bitdiff = diffs[k]
            bad += (bitdiff > MAX_HAMMING_BITS_PER_WORD)
            errors += bitdiff
        for start in range(count - need + 1):
            if start:
                outgoing, incoming = diffs[start - 1], diffs[start + need - 1]
                bad += (incoming > MAX_HAMMING_BITS_PER_WORD) - (outgoing > MAX_HAMMING_BITS_PER_WORD)
                errors += incoming - outgoing
            ratio = (need - bad) / need
            mean_error = errors / need
            if ratio < MIN_GOOD_FRAME_RATIO or mean_error > MAX_MEAN_DIFFERING_BITS:
                continue
            xs = a[ai + start:ai + start + need]
            ys = b[bi + start:bi + start + need]
            if len(set(xs)) < MIN_DIVERSE_WORDS or len(set(ys)) < MIN_DIVERSE_WORDS:
                continue
            rank = (ratio, need, -mean_error)
            if rank <= best_rank:
                continue
            best_rank = rank
            at = target.offset_ms + (ai + start) * step
            bt = reference.offset_ms + (bi + start) * step
            best = Match(
                target_start_ms=at, reference_start_ms=bt,
                length_ms=need * step, frame_ratio=round(ratio, 4),
                mean_bit_error=round(mean_error, 4), shift_ms=at - bt)
    return best


def near_record(match: Match, *, start_ms, end_ms, target=True):
    """Matched segment must overlap the candidate intro/outro window."""
    if type(start_ms) is not int or type(end_ms) is not int or start_ms >= end_ms:
        return False
    beginning = match.target_start_ms if target else match.reference_start_ms
    ending = beginning + match.length_ms
    overlap = max(0, min(end_ms, ending) - max(start_ms, beginning))
    return overlap >= min(MIN_DURATION_MS, int((end_ms - start_ms) * 0.70))


def inspect_cohort(target, peer_matches: list[tuple[int, Match, bool]]):
    """Aggregate independent matches; do NOT turn it into an approval.

    target is a record with start_ms/end_ms. Each peer tuple has episode,
    fingerprint match, and whether it is a verified approved device marker.
    """
    distinct = {}
    for episode, result, human in peer_matches:
        if type(episode) is not int or episode in distinct or result is None:
            continue
        if near_record(result, start_ms=target['start_ms'],
                       end_ms=target['end_ms']):
            distinct[episode] = human
    if len(distinct) >= 3 and any(distinct.values()):
        return "SHADOW_FINGERPRINT_PLUS_MANUAL_NOT_RELEASED"
    if len(distinct) >= 2:
        return "SHADOW_MULTIPLE_AUDIO_MATCHES_NOT_RELEASED"
    if distinct:
        return "SHADOW_SINGLE_AUDIO_MATCH_NOT_RELEASED"
    return "NO_FINGERPRINT_PROOF"
