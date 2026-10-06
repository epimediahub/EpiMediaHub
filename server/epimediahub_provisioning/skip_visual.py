"""EpiScene: bounded, temporal visual fingerprints and independent consensus.

Pixels are decoded only by the Hetzner execution role. Stored data consists of
two perceptual hashes per small, centrally cropped grayscale frame. Matching
requires an ordered, changing sequence; black frames and static logos cannot
authorize a marker. A quality score is similarity, not a probability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import OrderedDict
import copy
import hashlib
import json
import math
import numpy as np

POLICY = 'episcene_visual_v1'
MAX_FRAMES = 1444
STEPS = (500, 1000)
_POPCOUNT = np.array([n.bit_count() for n in range(256)], dtype=np.uint8)
_DCT = np.cos(np.pi / 32 * (np.arange(32)[None, :] + .5) * np.arange(8)[:, None]).astype(np.float32)


@dataclass
class VisualWindow:
    frames: list
    offset_ms: int
    step_ms: int
    length_ms: int
    duration_ms: int
    episode_id: str
    episode: int
    trusted_ranges: list = field(default_factory=list)

    def __post_init__(self):
        for value in (self.offset_ms, self.step_ms, self.length_ms, self.duration_ms, self.episode):
            if type(value) is not int:
                raise ValueError('invalid_request')
        if (self.step_ms not in STEPS or not 0 <= self.offset_ms < self.duration_ms <= 86_400_000
                or not 5000 <= self.length_ms <= 720_000
                or self.offset_ms + self.length_ms > self.duration_ms + self.step_ms
                or not 1 <= self.episode <= 10000
                or not isinstance(self.episode_id, str) or not 1 <= len(self.episode_id) <= 128
                or not isinstance(self.frames, list) or not 1 <= len(self.frames) <= MAX_FRAMES
                or len(self.frames) != math.ceil(self.length_ms / self.step_ms)
                or not isinstance(self.trusted_ranges, list) or len(self.trusted_ranges) > 3):
            raise ValueError('invalid_request')
        for frame in self.frames:
            if (not isinstance(frame, list) or len(frame) != 4
                    or any(type(v) is not int for v in frame)
                    or not 0 <= frame[0] < 1 << 63 or not 0 <= frame[1] < 1 << 64
                    or not 0 <= frame[2] <= 128 or not 0 <= frame[3] <= 255):
                raise ValueError('invalid_request')
        for pair in self.trusted_ranges:
            if (not isinstance(pair, list) or len(pair) != 2 or any(type(v) is not int for v in pair)
                    or not self.offset_ms <= pair[0] < pair[1] <= self.offset_ms + self.length_ms
                    or pair[1] - pair[0] < 15000):
                raise ValueError('invalid_request')

    def payload(self):
        return dict(frames=self.frames, offset_ms=self.offset_ms, step_ms=self.step_ms,
                    length_ms=self.length_ms, duration_ms=self.duration_ms,
                    episode_id=self.episode_id, episode=self.episode,
                    trusted_ranges=self.trusted_ranges)

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise ValueError('invalid_request')
        return cls(**value)


def hashes(pixels):
    """Return pHash, dHash, contrast and brightness for 32x32 grayscale frames."""
    frames = np.asarray(pixels, dtype=np.uint8)
    if frames.ndim != 3 or frames.shape[1:] != (32, 32) or not 1 <= len(frames) <= MAX_FRAMES:
        raise ValueError('visual_failed')
    values = frames.astype(np.float32)
    coefficients = (_DCT @ values @ _DCT.T).reshape(len(frames), 64)[:, 1:]
    bits = coefficients > np.median(coefficients, axis=1)[:, None]
    phash = np.sum(bits.astype(np.uint64) * (np.uint64(1) << np.arange(63, dtype=np.uint64)), axis=1)
    # Average tiles before differences to avoid sensitivity to individual pixels.
    small = values.reshape(len(frames), 8, 4, 8, 4).mean(axis=(2, 4))
    difference = np.concatenate(((small[:, :, 1:] > small[:, :, :-1]).reshape(len(frames), 56),
                                 small[:, 1, :] > small[:, 6, :]), axis=1)
    dhash = np.sum(difference.astype(np.uint64) * (np.uint64(1) << np.arange(64, dtype=np.uint64)), axis=1)
    contrast = np.rint(values.std(axis=(1, 2))).astype(int)
    brightness = np.rint(values.mean(axis=(1, 2))).astype(int)
    return [[int(p), int(d), int(c), int(b)] for p, d, c, b in zip(phash, dhash, contrast, brightness)]


def extract(source, start_ms, length_ms, step_ms=1000, busy=lambda: False):
    from skip_analysis import input_options, run
    if (type(start_ms) is not int or not 0 <= start_ms <= 86_400_000
            or type(length_ms) is not int or not 5000 <= length_ms <= 720_000
            or type(step_ms) is not int or step_ms not in STEPS):
        raise ValueError('invalid_request')
    maximum = math.ceil(length_ms / step_ms) + 2
    raw = run(['ffmpeg', '-nostdin', '-v', 'error', '-threads', '2', '-filter_threads', '1',
               *input_options(source), '-ss', str(start_ms / 1000), '-i', source,
               '-t', str(length_ms / 1000), '-map', '0:v:0', '-an', '-sn', '-dn',
               '-vf', f'setpts=PTS-STARTPTS,fps=1000/{step_ms}:start_time=0:round=near,'
                      'crop=iw*0.88:ih*0.78:iw*0.06:ih*0.08,scale=32:32:flags=area,format=gray',
               '-frames:v', str(maximum), '-f', 'rawvideo', '-pix_fmt', 'gray', 'pipe:1'],
              max_bytes=maximum * 1024, timeout=100, busy=busy)
    if (not raw or len(raw) % 1024 or len(raw) // 1024 < math.ceil(length_ms / step_ms) - 2):
        raise ValueError('visual_incomplete')
    expected = math.ceil(length_ms / step_ms)
    frames = hashes(np.frombuffer(raw, dtype=np.uint8).reshape(-1, 32, 32))[:expected]
    # Preserve the time grid when EOF removes a final sample; unknown frames
    # carry zero contrast and cannot support either boundary or a match.
    return frames + [[0, 0, 0, 0] for _ in range(expected - len(frames))]


def _count(value):
    contiguous = np.ascontiguousarray(value, dtype=np.uint64)
    return _POPCOUNT[contiguous.view(np.uint8).reshape(*contiguous.shape, 8)].sum(axis=-1)


def _informative(frames):
    return (frames[:, 2] >= 10) & (frames[:, 3] >= 8) & (frames[:, 3] <= 247)


def _diverse(frames):
    if len(frames) < 8 or len(set(int(x) for x in frames[:, 0])) < 8:
        return False
    return int(np.sum(_count(frames[1:, 0] ^ frames[:-1, 0]) >= 5)) >= 4


def _distinct_structure(frames):
    # Several camera views are needed for an unreviewed visual-only intro.
    # Small changes in a face against one recurring room/background are not
    # six independent structures, even if every frame has a different hash.
    representatives = []
    for value in frames[:, 0]:
        value = int(value)
        if all((value ^ previous).bit_count() > 12 for previous in representatives):
            representatives.append(value)
            if len(representatives) >= 6:
                return True
    return False


class VisualCache:
    def __init__(self, capacity=128):
        self.capacity, self.items, self.hits, self.misses = capacity, OrderedDict(), 0, 0

    def key(self, target, reference, kind):
        # Includes current trusted bounds, episode identity and every hash value.
        return hashlib.sha256(json.dumps([POLICY, kind, target.payload(), reference.payload()],
                                         separators=(',', ':')).encode()).hexdigest()

    def get(self, key):
        if key not in self.items:
            self.misses += 1
            return None
        self.hits += 1
        self.items.move_to_end(key)
        return copy.deepcopy(self.items[key])

    def put(self, key, value):
        self.items[key] = copy.deepcopy(value)
        self.items.move_to_end(key)
        while len(self.items) > self.capacity:
            self.items.popitem(last=False)

    def stats(self):
        return dict(pairs=len(self.items), capacity=self.capacity, hits=self.hits, misses=self.misses)


def pair_candidates(target, reference, kind, busy=lambda: False, cache=None):
    if busy():
        raise ValueError('analysis_deferred')
    key = cache.key(target, reference, kind) if cache is not None else None
    cached = cache.get(key) if cache is not None else None
    if cached is not None:
        return cached
    result = _pair_candidates(target, reference, kind, busy)
    if cache is not None:
        cache.put(key, result)
    return result


def _pair_candidates(target, reference, kind, busy):
    if (target.step_ms != reference.step_ms or target.episode_id == reference.episode_id
            or target.episode == reference.episode):
        return []
    a, b = np.asarray(target.frames, dtype=np.uint64), np.asarray(reference.frames, dtype=np.uint64)
    # At most 1444x1444 entries and one partner at a time. No FFT/pair cache
    # keyed by mutable objects, and no unbounded all-episode comparison.
    p = _count(a[:, None, 0] ^ b[None, :, 0])
    if busy():
        raise ValueError('analysis_deferred')
    d = _count(a[:, None, 1] ^ b[None, :, 1])
    good = (p <= 8) & (d <= 10) & _informative(a)[:, None] & _informative(b)[None, :]
    good &= np.abs(a[:, None, 3].astype(int) - b[None, :, 3].astype(int)) <= 40
    ai, bi = np.nonzero(good)
    if not len(ai):
        return []
    votes = np.bincount(ai - bi + len(b), minlength=len(a) + len(b))
    offsets = sorted(np.flatnonzero(votes >= max(15, 15000 // target.step_ms)),
                     key=lambda i: int(votes[i]), reverse=True)[:12]
    candidates = []
    step = target.step_ms
    for index in offsets:
        if busy():
            raise ValueError('analysis_deferred')
        shift = int(index) - len(b)
        begin_a, begin_b = max(0, shift), max(0, -shift)
        n = min(len(a) - begin_a, len(b) - begin_b)
        mask = good[begin_a + np.arange(n), begin_b + np.arange(n)]
        matched = np.flatnonzero(mask)
        groups = np.split(matched, np.flatnonzero(np.diff(matched) > 2) + 1)
        absolute_shift = target.offset_ms - reference.offset_ms + shift * step
        for group in groups:
            if not len(group):
                continue
            lo, hi = int(group[0]), int(group[-1]) + 1
            length, ratio = (hi - lo) * step, len(group) / (hi - lo)
            if not 15000 <= length <= (300000 if kind == 'intro' else 900000) or ratio < .90:
                continue
            aa, bb = a[begin_a + lo:begin_a + hi], b[begin_b + lo:begin_b + hi]
            if not _diverse(aa) or not _diverse(bb):
                continue
            structure = _distinct_structure(aa) and _distinct_structure(bb)
            if not reference.trusted_ranges and not structure:
                continue
            ia, ib = begin_a + np.arange(lo, hi), begin_b + np.arange(lo, hi)
            quality = float(np.mean(1 - (p[ia, ib] + d[ia, ib]) / 127.0))
            start = target.offset_ms + (begin_a + lo) * step
            end = target.offset_ms + (begin_a + hi - 1) * step
            ref_start = reference.offset_ms + (begin_b + lo) * step
            ref_end = reference.offset_ms + (begin_b + hi) * step
            trusted = None
            if reference.trusted_ranges:
                trusted = next((r for r in reference.trusted_ranges
                                if ref_start <= r[0] + step and ref_end >= r[1] - step
                                and length >= .90 * (r[1] - r[0])), None)
                if trusted is None:
                    continue
                start, end = trusted[0] + absolute_shift, trusted[1] + absolute_shift
            bounds = bool(np.all(mask[lo:lo + 2]) and np.all(mask[max(lo, hi - 2):hi]))
            if not trusted and (end >= target.offset_ms + target.length_ms - 2 * step
                    and target.offset_ms + target.length_ms < target.duration_ms - step
                    or ref_end >= reference.offset_ms + reference.length_ms - step
                    and reference.offset_ms + reference.length_ms < reference.duration_ms - step):
                bounds = False  # A sequence clipped by a search window has no known end.
            if start < 0 or end > target.duration_ms or end <= start:
                continue
            if kind == 'intro' and (start > min(720000, target.duration_ms * .4) or end - start > 300000):
                continue
            if kind == 'outro' and start < target.duration_ms * .65:
                continue
            candidates.append(dict(start_ms=start, end_ms=end, quality=round(quality, 6),
                                   ratio=round(ratio, 6), boundaries_confirmed=bounds,
                                   partner=reference.episode_id, episode=reference.episode,
                                   trusted_range=trusted, shift_ms=absolute_shift,
                                   structural_diversity=structure,
                                   informative_frames=int(np.sum(mask[lo:hi]))))
    # Adjacent temporal samples represent the same candidate, not separate evidence.
    chosen = []
    for value in sorted(candidates, key=lambda c: (c['quality'] * c['ratio'], c['end_ms'] - c['start_ms']), reverse=True):
        if not any(abs(value['start_ms'] - c['start_ms']) <= step and abs(value['end_ms'] - c['end_ms']) <= step for c in chosen):
            chosen.append(value)
    return chosen[:6]


def detect(target, partners, kind, busy=lambda: False, cache=None):
    if kind not in ('intro', 'outro') or len(partners) > 4:
        raise ValueError('invalid_request')
    result = dict(policy=POLICY, status='NO_MATCH', start_ms=None, end_ms=None,
                  confidence=0.0, support=0, ambiguous=False, boundaries_confirmed=False,
                  boundary_spread_ms=0, matches=[])
    used, identities, pairs = {target.episode}, {target.episode_id}, []
    for partner in partners:
        if partner.episode in used or partner.episode_id in identities:
            continue
        used.add(partner.episode); identities.add(partner.episode_id)
        candidates = pair_candidates(target, partner, kind, busy, cache)
        if candidates:
            best = candidates[0]
            # Different plausible locations or materially different ends require review.
            if any(c['quality'] >= best['quality'] - .035
                   and c['end_ms'] - c['start_ms'] >= .8 * (best['end_ms'] - best['start_ms'])
                   for c in candidates[1:]):
                result['ambiguous'] = True
            pairs.append(best)
    if not pairs:
        return result
    groups = []
    tolerance = max(1000, target.step_ms)
    for pair in pairs:
        group = next((g for g in groups if abs(g[0]['start_ms'] - pair['start_ms']) <= tolerance
                      and abs(g[0]['end_ms'] - pair['end_ms']) <= tolerance), None)
        if group is None:
            groups.append([pair])
        else:
            group.append(pair)
    groups.sort(key=lambda g: (len(g), min(c['quality'] for c in g)), reverse=True)
    chosen = groups[0]
    if len(groups) > 1:
        result['ambiguous'] = True
    start = max(c['start_ms'] for c in chosen)
    end = min(c['end_ms'] for c in chosen) - target.step_ms // 2
    if end - start < 15000:
        return result
    spread = max(max(c[k] for c in chosen) - min(c[k] for c in chosen) for k in ('start_ms', 'end_ms'))
    trusted = any(c['trusted_range'] for c in chosen)
    quality, ratio = min(c['quality'] for c in chosen), min(c['ratio'] for c in chosen)
    bounds = all(c['boundaries_confirmed'] for c in chosen)
    automatic = (not result['ambiguous'] and bounds and quality >= .955 and ratio >= .94
                 and spread <= 1000 and (trusted or len(chosen) >= 3)
                 and end - start >= 15000)
    # Unknown credits before a possible post-credit scene must never cut dialogue.
    if kind == 'outro' and target.duration_ms - end > max(1000, target.step_ms):
        automatic = False
    result.update(status='AUTO_CONFIRMED' if automatic else 'REVIEW', start_ms=start, end_ms=end,
                  confidence=round(min(quality, ratio), 6), support=len(chosen),
                  boundaries_confirmed=bounds, boundary_spread_ms=spread, matches=chosen)
    return result


def validate_result(value, target, partners, kind):
    """Validate RPC/evidence structure, identity, bounds and auto-release rules."""
    expected = {'policy', 'status', 'start_ms', 'end_ms', 'confidence', 'support',
                'ambiguous', 'boundaries_confirmed', 'boundary_spread_ms', 'matches'}
    if (not isinstance(value, dict) or set(value) != expected or value['policy'] != POLICY
            or value['status'] not in ('NO_MATCH', 'REVIEW', 'AUTO_CONFIRMED')
            or type(value['ambiguous']) is not bool or type(value['boundaries_confirmed']) is not bool
            or type(value['support']) is not int or not 0 <= value['support'] <= 4
            or type(value['boundary_spread_ms']) is not int or not 0 <= value['boundary_spread_ms'] <= 720000
            or type(value['confidence']) not in (int, float) or not 0 <= value['confidence'] <= 1
            or not isinstance(value['matches'], list) or len(value['matches']) != value['support']):
        raise ValueError('invalid_visual_result')
    if value['status'] == 'NO_MATCH':
        if value['start_ms'] is not None or value['end_ms'] is not None or value['support'] or value['confidence']:
            raise ValueError('invalid_visual_result')
        return value
    start, end = value['start_ms'], value['end_ms']
    if (type(start) is not int or type(end) is not int or not 0 <= start < end <= target.duration_ms
            or start < target.offset_ms or end > target.offset_ms + target.length_ms
            or not 15000 <= end - start <= (300000 if kind == 'intro' else 900000)
            or not value['matches']):
        raise ValueError('invalid_visual_result')
    by_id = {p.episode_id: p for p in partners}
    ids, episodes, trusted = {target.episode_id}, {target.episode}, False
    for match in value['matches']:
        if not isinstance(match, dict) or match.get('partner') not in by_id:
            raise ValueError('invalid_visual_result')
        reference = by_id[match['partner']]
        if (match['partner'] in ids or reference.episode in episodes or match.get('episode') != reference.episode
                or type(match.get('start_ms')) is not int or type(match.get('end_ms')) is not int
                or not 0 <= match['start_ms'] < match['end_ms'] <= target.duration_ms
                or type(match.get('boundaries_confirmed')) is not bool
                or type(match.get('structural_diversity')) is not bool
                or type(match.get('informative_frames')) is not int or not 15 <= match['informative_frames'] <= MAX_FRAMES
                or type(match.get('shift_ms')) is not int):
            raise ValueError('invalid_visual_result')
        for name in ('quality', 'ratio'):
            if type(match.get(name)) not in (int, float) or not 0 <= match[name] <= 1:
                raise ValueError('invalid_visual_result')
        marker = match.get('trusted_range')
        if marker is not None:
            if (marker not in reference.trusted_ranges or match['start_ms'] != marker[0] + match['shift_ms']
                    or match['end_ms'] != marker[1] + match['shift_ms']):
                raise ValueError('invalid_visual_result')
            trusted = True
        ids.add(reference.episode_id); episodes.add(reference.episode)
    matches = value['matches']
    spread = max(max(m[k] for m in matches) - min(m[k] for m in matches) for k in ('start_ms', 'end_ms'))
    if (start != max(m['start_ms'] for m in matches) or end != min(m['end_ms'] for m in matches) - target.step_ms // 2
            or value['boundary_spread_ms'] != spread
            or abs(value['confidence'] - min(min(m['quality'], m['ratio']) for m in matches)) > .000002):
        raise ValueError('invalid_visual_result')
    if value['status'] == 'AUTO_CONFIRMED' and (
            value['ambiguous'] or not value['boundaries_confirmed'] or spread > 1000
            or not all(m['boundaries_confirmed'] and m['quality'] >= .955 and m['ratio'] >= .94 for m in matches)
            or not (trusted or value['support'] >= 3)
            or not trusted and not all(m['structural_diversity'] for m in matches)
            or kind == 'intro' and start > min(720000, target.duration_ms * .4)
            or kind == 'outro' and (start < target.duration_ms * .65 or target.duration_ms - end > 1000)):
        raise ValueError('invalid_visual_result')
    return value
