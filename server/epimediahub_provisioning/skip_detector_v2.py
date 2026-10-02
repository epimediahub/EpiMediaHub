"""Bounded Chromaprint candidate search and independent episode consensus.

Confidence is an evidence score, not a calibrated probability. The worker
supplies the actual Chromaprint frame duration and checks decoded coverage.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ceil, exp, floor, isfinite
from statistics import median
from typing import Callable, Iterable

POLICY = "chromaprint_v2_1"


class MarkerType(str, Enum):
    INTRO = "INTRO"
    OUTRO = "OUTRO"


class Status(str, Enum):
    AUTO_CONFIRMED = "AUTO_CONFIRMED"
    REVIEW = "REVIEW"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class Segment:
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class Config:
    item_duration_sec: float = 0.1238
    chromaprint_delay_sec: float = 0.0
    bit_threshold: int = 8
    max_gap_frames: int = 8
    min_match_ratio: float = 0.78
    min_seconds: float = 15.0
    max_seconds: float = 120.0
    intro_search_window_sec: float = 12.0 * 60.0
    outro_search_window_sec: float = 12.0 * 60.0
    alignment_bits: int = 12
    top_offsets: int = 12
    min_offset_votes: int = 3
    max_alignment_bucket_size: int = 96
    offset_peak_merge_frames: int = 2
    partners_per_episode: int = 4
    cluster_endpoint_tolerance_sec: float = 8.0
    cluster_min_iou: float = 0.55
    min_consensus_partners: int = 2
    auto_confirm_threshold: float = 0.92
    review_threshold: float = 0.72
    auto_boundary_tolerance_sec: float = 1.0
    min_auto_pair_quality: float = 0.92
    min_auto_match_ratio: float = 0.90
    max_fingerprint_frames: int = 36000
    # Algorithm 1's analysis/filter lookahead at 11025 Hz. The transition
    # away from a flat fingerprint appears before the underlying sound starts.
    stationary_transition_sec: float = 2.6


@dataclass(frozen=True)
class PairCandidate:
    segment: Segment
    partner_segment: Segment
    offset_frames: int
    histogram_votes: int
    match_ratio: float
    average_hamming: float
    quality: float


@dataclass(frozen=True)
class Detection:
    type: MarkerType
    segment: Segment | None
    confidence: float
    status: Status
    support: int
    attempted_partners: int
    mean_pair_quality: float
    temporal_consistency: float
    position_plausibility: float
    chromaprint_delay_sec: float
    supported_partners: tuple[int, ...] = ()
    min_pair_quality: float = 0.0
    min_match_ratio: float = 0.0
    boundary_spread_sec: float = 0.0


class IntroOutroDetectorV2:
    def __init__(self, config: Config | None = None, busy: Callable[[], bool] | None = None):
        self.c = config or Config()
        self.busy = busy or (lambda: False)
        if (not all(isfinite(x) for x in (self.c.item_duration_sec, self.c.chromaprint_delay_sec,
                self.c.min_seconds, self.c.max_seconds, self.c.intro_search_window_sec,
                self.c.outro_search_window_sec, self.c.stationary_transition_sec)) or self.c.item_duration_sec <= 0
                or self.c.chromaprint_delay_sec < 0 or self.c.min_seconds <= 0
                or self.c.max_seconds < self.c.min_seconds
                or min(self.c.intro_search_window_sec, self.c.outro_search_window_sec) <= 0
                or not 1 <= self.c.alignment_bits <= 16
                or not 0 <= self.c.bit_threshold <= 16
                or not 0 <= self.c.max_gap_frames <= 32
                or not 1 <= self.c.top_offsets <= 24
                or not 2 <= self.c.min_consensus_partners <= self.c.partners_per_episode <= 8
                or not 0 <= self.c.review_threshold <= self.c.auto_confirm_threshold <= 1
                or not 0 < self.c.min_match_ratio <= 1
                or not 0 < self.c.min_auto_match_ratio <= 1
                or not 0 < self.c.min_auto_pair_quality <= 1
                or not 0 < self.c.auto_boundary_tolerance_sec <= self.c.cluster_endpoint_tolerance_sec
                or not 0 < self.c.cluster_min_iou <= 1
                or not 1 <= self.c.min_offset_votes <= 100
                or not 1 <= self.c.max_alignment_bucket_size <= 128
                or not 0 <= self.c.offset_peak_merge_frames <= 8
                or not 1 <= self.c.max_fingerprint_frames <= 36000):
            raise ValueError("invalid detector configuration")
        if not 0 <= self.c.stationary_transition_sec <= 5:
            raise ValueError("invalid detector configuration")

    def _checkpoint(self) -> None:
        if self.busy():
            raise ValueError("analysis_deferred")

    @staticmethod
    def _ham(a: int, b: int) -> int:
        return ((a ^ b) & 0xFFFFFFFF).bit_count()

    def _seconds_to_frames(self, seconds: float) -> int:
        return max(1, round(seconds / self.c.item_duration_sec))

    def _frame_start(self, index: int) -> float:
        return max(0, index) * self.c.item_duration_sec + self.c.chromaprint_delay_sec

    def _frame_end(self, end_exclusive: int) -> float:
        if end_exclusive <= 0:
            return 0.0
        return end_exclusive * self.c.item_duration_sec + self.c.chromaprint_delay_sec

    def _window(self, size: int, marker_type: MarkerType) -> tuple[int, int]:
        seconds = self.c.intro_search_window_sec if marker_type == MarkerType.INTRO else self.c.outro_search_window_sec
        frames = self._seconds_to_frames(seconds)
        if marker_type == MarkerType.INTRO:
            return 0, min(size, frames)
        return max(0, size - frames), size

    def _likely_offsets(
        self,
        a: list[int], b: list[int],
        a0: int, a1: int, b0: int, b1: int,
        informative_a: list[bool], informative_b: list[bool],
    ) -> list[tuple[int, int]]:
        # Several disjoint bands avoid missing every anchor when a stable
        # encode difference affects the most significant fingerprint bits.
        bands = [(shift, (1 << min(self.c.alignment_bits, 32 - shift)) - 1)
                 for shift in range(0, 32, self.c.alignment_bits)]
        buckets: dict[tuple[int, int], list[int]] = {}
        for j in range(b0, b1):
            if j % 512 == 0:
                self._checkpoint()
            if not informative_b[j]:
                continue
            for shift, mask in bands:
                key = (shift, ((b[j] & 0xFFFFFFFF) >> shift) & mask)
                positions = buckets.setdefault(key, [])
                if len(positions) <= self.c.max_alignment_bucket_size:
                    positions.append(j)

        hist: dict[int, int] = {}
        for i in range(a0, a1):
            if i % 512 == 0:
                self._checkpoint()
            if not informative_a[i]:
                continue
            for shift, mask in bands:
                positions = buckets.get((shift, ((a[i] & 0xFFFFFFFF) >> shift) & mask))
                if not positions or len(positions) > self.c.max_alignment_bucket_size:
                    continue
                for j in positions:
                    d = i - j
                    hist[d] = hist.get(d, 0) + 1

        ranked = sorted(
            ((d, votes) for d, votes in hist.items() if votes >= self.c.min_offset_votes),
            key=lambda x: (-x[1], abs(x[0])),
        )
        selected: list[tuple[int, int]] = []
        for d, votes in ranked:
            if any(abs(d - old_d) <= self.c.offset_peak_merge_frames for old_d, _ in selected):
                continue
            selected.append((d, votes))
            if len(selected) >= self.c.top_offsets:
                break
        return selected

    def _build_candidate(
        self, a: list[int], b: list[int], start: int, end: int, offset: int, votes: int
    ) -> PairCandidate | None:
        total = end - start
        if total <= 0:
            return None
        # Constant/silent or tiny repeating patterns are not independent
        # evidence of a title sequence, even with a perfect Hamming score.
        if min(len(set(a[start:end])), len(set(b[start-offset:end-offset]))) < max(15, total // 10):
            return None
        matches = 0
        hsum = 0
        for i in range(start, end):
            if i % 512 == 0:
                self._checkpoint()
            j = i - offset
            if j < 0 or j >= len(b):
                return None
            h = self._ham(a[i], b[j])
            hsum += h
            if h <= self.c.bit_threshold:
                matches += 1
        ratio = matches / total
        if ratio < self.c.min_match_ratio:
            return None
        avg_h = hsum / total
        hq = max(0.0, min(1.0, 1.0 - avg_h / 32.0))
        quality = max(0.0, min(1.0, 0.65 * ratio + 0.35 * hq))
        b_start, b_end = start - offset, end - offset
        return PairCandidate(
            segment=Segment(self._frame_start(start), self._frame_end(end)),
            partner_segment=Segment(self._frame_start(b_start), self._frame_end(b_end)),
            offset_frames=offset,
            histogram_votes=votes,
            match_ratio=ratio,
            average_hamming=avg_h,
            quality=quality,
        )

    def _verify_offset(
        self,
        a: list[int], b: list[int],
        a0: int, a1: int, b0: int, b1: int,
        offset: int, votes: int, marker_type: MarkerType,
        informative_a: list[bool], informative_b: list[bool],
    ) -> list[PairCandidate]:
        overlap0 = max(a0, b0 + offset)
        overlap1 = min(a1, b1 + offset)
        if overlap0 >= overlap1:
            return []

        min_frames = ceil(self.c.min_seconds / self.c.item_duration_sec)
        max_frames = floor(self.c.max_seconds / self.c.item_duration_sec)
        found: list[PairCandidate] = []
        run_start = -1
        last_match = -1
        gap = 0

        def close_run() -> None:
            nonlocal run_start, last_match, gap
            if run_start >= 0 and last_match >= run_start:
                s, e = run_start, last_match + 1
                # Reject overlong common scenes; do not manufacture a 120s
                # intro by truncating them. Continue checking later runs.
                if min_frames <= e - s <= max_frames:
                    cand = self._build_candidate(a, b, s, e, offset, votes)
                    if cand:
                        found.append(cand)
            run_start = -1
            last_match = -1
            gap = 0

        for i in range(overlap0, overlap1):
            if i % 512 == 0:
                self._checkpoint()
            j = i - offset
            ok = informative_a[i] and informative_b[j] and self._ham(a[i], b[j]) <= self.c.bit_threshold
            if ok:
                if run_start < 0:
                    run_start = i
                last_match = i
                gap = 0
            elif run_start >= 0:
                gap += 1
                if gap > self.c.max_gap_frames:
                    close_run()
        close_run()
        return found

    def _informative(self, words: list[int]) -> list[bool]:
        # Silence and stationary audio can flank a real title. Global segment
        # diversity alone does not prevent those flat margins from extending it.
        informative = [True] * len(words)
        begin = 0
        flat_frames = max(8, ceil(1.5 / self.c.item_duration_sec))
        for end in range(1, len(words) + 1):
            if end == len(words) or words[end] != words[begin]:
                if end - begin >= flat_frames:
                    finish = min(len(words), end + ceil(self.c.stationary_transition_sec / self.c.item_duration_sec))
                    informative[begin:finish] = [False] * (finish - begin)
                begin = end
        return informative

    def find_pair_candidate(self, target: Iterable[int], partner: Iterable[int], marker_type: MarkerType) -> PairCandidate | None:
        a, b = list(target), list(partner)
        if (not a or not b or max(len(a), len(b)) > self.c.max_fingerprint_frames
                or any(type(x) is not int or not -(1 << 31) <= x < (1 << 32) for x in a + b)):
            return None
        a0, a1 = self._window(len(a), marker_type)
        b0, b1 = self._window(len(b), marker_type)
        informative_a, informative_b = self._informative(a), self._informative(b)
        candidates: list[PairCandidate] = []
        for offset, votes in self._likely_offsets(a, b, a0, a1, b0, b1, informative_a, informative_b):
            candidates.extend(self._verify_offset(a, b, a0, a1, b0, b1, offset, votes, marker_type,
                                                  informative_a, informative_b))
        if not candidates:
            return None
        best = max(candidates, key=lambda c: (c.quality, c.segment.length))
        # A second comparable occurrence in either file is ambiguous, even
        # when an early position happens to have a better heuristic score.
        if any((abs(c.segment.start - best.segment.start) > 2.0
                or abs(c.partner_segment.start - best.partner_segment.start) > 2.0)
               and c.quality >= best.quality - .03
               and c.segment.length >= best.segment.length * .8 for c in candidates):
            return None
        return best

    @staticmethod
    def _iou(a: Segment, b: Segment) -> float:
        inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
        union = max(a.end, b.end) - min(a.start, b.start)
        return 0.0 if union <= 0 else inter / union

    def _same_cluster(self, a: Segment, b: Segment) -> bool:
        close = abs(a.start - b.start) <= self.c.cluster_endpoint_tolerance_sec and abs(a.end - b.end) <= self.c.cluster_endpoint_tolerance_sec
        return close and self._iou(a, b) >= self.c.cluster_min_iou

    def _clusters(self, candidates: list[PairCandidate]) -> list[list[PairCandidate]]:
        clusters: list[list[PairCandidate]] = []
        for cand in sorted(candidates, key=lambda x: x.quality, reverse=True):
            best_idx, best_sim = None, -10.0
            for idx, cluster in enumerate(clusters):
                rep = Segment(median(x.segment.start for x in cluster), median(x.segment.end for x in cluster))
                if not self._same_cluster(cand.segment, rep):
                    continue
                penalty = (abs(cand.segment.start - rep.start) + abs(cand.segment.end - rep.end)) / max(1.0, 2 * self.c.cluster_endpoint_tolerance_sec)
                sim = self._iou(cand.segment, rep) - 0.15 * penalty
                if sim > best_sim:
                    best_idx, best_sim = idx, sim
            if best_idx is None:
                clusters.append([cand])
            else:
                clusters[best_idx].append(cand)
        return clusters

    def _position(self, marker_type: MarkerType, seg: Segment, fp_size: int) -> float:
        preferred = 8.0 * 60.0
        if marker_type == MarkerType.INTRO:
            if seg.start <= preferred:
                return 1.0
            if seg.start >= self.c.intro_search_window_sec:
                return 0.0
            return max(0.0, min(1.0, 1.0 - (seg.start - preferred) / max(1.0, self.c.intro_search_window_sec - preferred)))
        approx_end = self._frame_end(fp_size)
        dist = max(0.0, approx_end - seg.end)
        if dist <= preferred:
            return 1.0
        if dist >= self.c.outro_search_window_sec:
            return 0.0
        return max(0.0, min(1.0, 1.0 - (dist - preferred) / max(1.0, self.c.outro_search_window_sec - preferred)))

    def _select_partners(self, target: int, count: int) -> list[int]:
        out: list[int] = []
        d = 1
        while len(out) < min(self.c.partners_per_episode, count - 1):
            right, left = target + d, target - d
            if right < count:
                out.append(right)
            if len(out) >= min(self.c.partners_per_episode, count - 1):
                break
            if left >= 0:
                out.append(left)
            d += 1
        return out

    def _rejected(self, marker_type: MarkerType, attempted: int) -> Detection:
        return Detection(marker_type, None, 0.0, Status.REJECTED, 0, attempted, 0.0, 0.0, 0.0, self.c.chromaprint_delay_sec)

    def detect_for_episode(self, target_index: int, fingerprints: list[list[int]], marker_type: MarkerType) -> Detection:
        if target_index < 0 or target_index >= len(fingerprints):
            raise IndexError(target_index)
        if len(fingerprints) < 3 or not fingerprints[target_index]:
            return self._rejected(marker_type, 0)
        partners = self._select_partners(target_index, len(fingerprints))
        pairs = [
            (p, c) for p in partners
            if fingerprints[p]
            for c in [self.find_pair_candidate(fingerprints[target_index], fingerprints[p], marker_type)]
            if c is not None
        ]
        candidates = [c for _, c in pairs]
        if len(candidates) < self.c.min_consensus_partners:
            return self._rejected(marker_type, len(partners))
        clusters = self._clusters(candidates)
        best = max(clusters, key=lambda cl: (len(cl), sum(x.quality for x in cl) / len(cl)))
        if len(best) < self.c.min_consensus_partners:
            return self._rejected(marker_type, len(partners))
        starts = [x.segment.start for x in best]
        ends = [x.segment.end for x in best]
        seg = Segment(median(starts), median(ends))
        if seg.end <= seg.start:
            return self._rejected(marker_type, len(partners))
        mean_q = sum(x.quality for x in best) / len(best)
        support_score = min(1.0, len(best) / max(1, len(partners)))
        mad_start = median(abs(x - median(starts)) for x in starts)
        mad_end = median(abs(x - median(ends)) for x in ends)
        consistency = max(0.0, min(1.0, exp(-(mad_start + mad_end) / self.c.cluster_endpoint_tolerance_sec)))
        position = self._position(marker_type, seg, len(fingerprints[target_index]))
        confidence = max(0.0, min(1.0, 0.45 * mean_q + 0.30 * support_score + 0.15 * consistency + 0.10 * position))
        runner = max((len(cl) for cl in clusters if cl is not best), default=0)
        if runner >= len(best):
            return self._rejected(marker_type, len(partners))
        tight = max(starts) - min(starts) <= self.c.auto_boundary_tolerance_sec and max(ends) - min(ends) <= self.c.auto_boundary_tolerance_sec
        if (confidence >= self.c.auto_confirm_threshold and len(best) >= 3 and tight
                and all(c.quality >= self.c.min_auto_pair_quality and c.match_ratio >= self.c.min_auto_match_ratio for c in best)):
            status = Status.AUTO_CONFIRMED
        elif confidence >= self.c.review_threshold:
            status = Status.REVIEW
        else:
            return self._rejected(marker_type, len(partners))
        return Detection(marker_type, seg, confidence, status, len(best), len(partners), mean_q,
                         consistency, position, self.c.chromaprint_delay_sec,
                         tuple(p for p, c in pairs if any(c is x for x in best)),
                         min(c.quality for c in best), min(c.match_ratio for c in best),
                         max(max(starts) - min(starts), max(ends) - min(ends)))

    def detect_all(self, fingerprints: list[list[int]], marker_type: MarkerType) -> dict[int, Detection]:
        return {i: self.detect_for_episode(i, fingerprints, marker_type) for i in range(len(fingerprints))}


def _self_test() -> None:
    import random
    rng = random.Random(42)
    intro = [rng.getrandbits(32) for _ in range(260)]
    fps: list[list[int]] = []
    for cold in (80, 130, 40, 170, 100):
        prefix = [rng.getrandbits(32) for _ in range(cold)]
        suffix = [rng.getrandbits(32) for _ in range(900)]
        fps.append(prefix + intro + suffix)
    d = IntroOutroDetectorV2(Config(min_seconds=20.0, max_seconds=45.0, intro_search_window_sec=180.0))
    results = d.detect_all(fps, MarkerType.INTRO)
    accepted = sum(r.status != Status.REJECTED for r in results.values())
    if accepted < 4:
        raise SystemExit(f"SELFTEST FAILED: only {accepted}/5 episodes detected")
    print(f"SELFTEST OK: {accepted}/5 intro detections; statuses={[r.status.value for r in results.values()]}")


if __name__ == "__main__":
    _self_test()
