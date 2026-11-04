#!/usr/bin/env python3
"""Bounded content-based audio-fingerprint matcher for SHADOW evaluation only.

Uses EpiScene's real cache format (signed 32-bit JSON words, 123.81-ms
floating sample step, thousands of words) and separates candidate retrieval
from >=15-second high-confidence content verification.
NOT an approval gate. No file/database/network operations.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import math

from fingerprint_cohort import (
    Fingerprint, Match, near_record, inspect_cohort,
    MIN_DURATION_MS, MAX_HAMMING_BITS_PER_WORD,
    MIN_GOOD_FRAME_RATIO, MAX_MEAN_DIFFERING_BITS, MIN_DIVERSE_WORDS,
)

MAX_WORDS = 10_000
MAX_JSON_CHARS = 256_000
MAX_CANDIDATE_OFFSETS = 24
MAX_ANCHORS = 64
MAX_BUCKET_OCCURRENCES = 256


def decode(raw, *, step_ms, offset_ms):
    if type(step_ms) not in (int, float) or not math.isfinite(step_ms):
        raise ValueError("bad fingerprint sampling step")
    if not 50 <= step_ms <= 2000:
        raise ValueError("bad fingerprint sampling step")
    if type(offset_ms) not in (int, float) or not math.isfinite(offset_ms):
        raise ValueError("bad fingerprint offset")
    if offset_ms < 0:
        raise ValueError("bad fingerprint offset")
    if not isinstance(raw, str) or len(raw) > MAX_JSON_CHARS:
        raise ValueError("fingerprint payload too large / invalid")
    try:
        words = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid fingerprint json") from exc
    if not isinstance(words, list) or not 1 <= len(words) <= MAX_WORDS:
        raise ValueError("invalid fingerprint shape")
    if any(type(x) is not int or not -(1 << 31) <= x < (1 << 32) for x in words):
        raise ValueError("invalid fingerprint word")
    return Fingerprint(tuple(x & 0xFFFFFFFF for x in words),
                       float(step_ms), round(offset_ms))


def match(target, reference):
    if not (isinstance(target, Fingerprint) and isinstance(reference, Fingerprint)):
        return None
    if not (math.isfinite(target.step_ms) and math.isfinite(reference.step_ms)):
        return None
    if abs(target.step_ms - reference.step_ms) > 0.02:
        return None
    step = target.step_ms
    count_needed = math.ceil(MIN_DURATION_MS / step)
    a, b = target.words, reference.words
    if not (count_needed <= len(a) <= MAX_WORDS
            and count_needed <= len(b) <= MAX_WORDS):
        return None
    # Four different byte signatures per word. Large repetitive buckets are
    # ignored to avoid low-information anchors and excessive comparisons.
    index = defaultdict(list)
    for j, word in enumerate(b):
        for byte in range(4):
            index[(byte, (word >> (byte * 8)) & 255)].append(j)
    stride = max(1, len(a) // MAX_ANCHORS)
    sampled = list(range(0, len(a), stride))[:MAX_ANCHORS]
    offsets = Counter()
    for i in sampled:
        word = a[i]
        for byte in range(4):
            locations = index[(byte, (word >> (byte * 8)) & 255)]
            if len(locations) > MAX_BUCKET_OCCURRENCES:
                continue
            for j in locations:
                shift = i - j
                overlap = min(len(a), len(b) + shift) - max(0, shift)
                if overlap >= count_needed:
                    offsets[shift] += 1
    # Distinct offsets only, with cap; subsequent full verification is still
    # responsible for declaring whether the contents actually agree.
    selected = sorted((x for x,n in offsets.items() if n >= 2),
                      key=lambda x: (-offsets[x], abs(x), x))[:MAX_CANDIDATE_OFFSETS]
    best = None
    quality_key = (-1.0, float('-inf'))
    for shift in selected:
        left = max(0, shift)
        right = min(len(a), shift + len(b))
        n = right - left
        if n < count_needed:
            continue
        ref_at = left - shift
        distances = [(a[left+k] ^ b[ref_at+k]).bit_count() for k in range(n)]
        mismatches = sum(x > MAX_HAMMING_BITS_PER_WORD
                         for x in distances[:count_needed])
        errors = sum(distances[:count_needed])
        for start in range(n - count_needed + 1):
            if start:
                out, new = distances[start-1], distances[start+count_needed-1]
                mismatches += (new > MAX_HAMMING_BITS_PER_WORD) - (
                    out > MAX_HAMMING_BITS_PER_WORD)
                errors += new - out
            ratio = (count_needed - mismatches) / count_needed
            mean_error = errors / count_needed
            if ratio < MIN_GOOD_FRAME_RATIO or mean_error > MAX_MEAN_DIFFERING_BITS:
                continue
            target_words = a[left+start:left+start+count_needed]
            peer_words = b[ref_at+start:ref_at+start+count_needed]
            if (len(set(target_words)) < MIN_DIVERSE_WORDS
                    or len(set(peer_words)) < MIN_DIVERSE_WORDS):
                continue
            key = (ratio, -mean_error)
            if key <= quality_key:
                continue
            quality_key = key
            ts = round(target.offset_ms + (left+start)*step)
            rs = round(reference.offset_ms + (ref_at+start)*step)
            best = Match(target_start_ms=ts, reference_start_ms=rs,
                         length_ms=round(count_needed*step),
                         frame_ratio=round(ratio, 6),
                         mean_bit_error=round(mean_error, 6),
                         shift_ms=ts-rs)
    return best
