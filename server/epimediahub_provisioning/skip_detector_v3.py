#!/usr/bin/env python3
"""
skip_detector_v3_1.py - Intro/Outro-Erkennung per Chromaprint-Fingerprint-Vergleich.

Aenderungen gegenueber V2
-------------------------
* Kandidatensuche per FFT-Kreuzkorrelation der 32 Bit-Spuren statt 12-Bit-Praefix-
  Voting. Hamming-tolerante Treffer gehen nicht mehr schon in der Vorfilterung verloren.
* Jedes Fenster traegt seine absolute Zeitbasis (start_sec, item_sec, delay_sec).
  Dadurch sind separat geladene Anfangs-/Endfenster korrekt in Dateizeit umrechenbar.
* Fingerprint-Indexzeit = start + n * item_sec (exklusive Grenze).
  Der Chromaprint-Delay beschreibt die Hash-Abdeckung und wird NICHT von der Dateizeit abgezogen.
* Mehrere Kandidaten je Partner, Konsens ueber verschiedene Partner (eine Stimme je Partner).
* Leere/zu kurze Partner zaehlen nicht im Nenner der Confidence.
* "trusted"-Partner (bereits freigegebene Referenz): 2 Partner genuegen fuer
  AUTO_CONFIRMED, wenn mindestens einer trusted ist.
* Fensterplanung fuer kurze Folgen (kein Ueberlappen von Intro- und Outro-Fenster).
* Optionales Einrasten der Grenzen auf Stille- und echte Schwarzbild-Punkte.
* Pair-Cache (Rueckrichtung kostenlos), kompakte Fingerprint-Serialisierung.
* ffmpeg/fpcalc-Helfer: nur Fenster decodieren, Mono 11025 Hz; fpcalc Algorithmus 2 explizit.

Das Modul speichert nichts und kennt weder Queue noch Datenbank.
V3.1 korrigiert ausserdem die TEST2-Zeitbasis und trennt Chromaprint-delay von einer Zeitkalibrierung.

Beispiel
--------
    cfg = Config()
    iw, ow = plan_windows(duration_sec, cfg)
    win = fingerprint_window(url, iw[0], iw[1] - iw[0], duration_sec=duration_sec,
                             episode_id="s02e13")
    det = detect(win, [partner_win_1, partner_win_2, ref_win], "intro", cfg)
    if det.status == "AUTO_CONFIRMED": ...
"""
from __future__ import annotations

import json
import hashlib
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import wave
import zlib
from collections import OrderedDict
from threading import RLock
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# fpcalc zaehlt Algorithmen fuer die CLI ab 1, die C-API dagegen ab 0.
# `fpcalc -algorithm 2` entspricht CHROMAPRINT_ALGORITHM_TEST2 == 1.
CHROMAPRINT_C_ALGO_TEST2 = 1
FPCALC_ALGORITHM = 2

# Chromaprint TEST2: 11025 Hz, Hop 1365 Samples, interner Puffer 28666 Samples.
DEFAULT_SAMPLE_RATE = 11025
DEFAULT_ITEM_SEC = 1365.0 / DEFAULT_SAMPLE_RATE
DEFAULT_DELAY_SEC = 28666.0 / DEFAULT_SAMPLE_RATE

AUTO = "AUTO_CONFIRMED"
REVIEW = "REVIEW"
REJECTED = "REJECTED"

_POP16 = np.array([bin(i).count("1") for i in range(1 << 16)], dtype=np.uint8)


def popcount32(x: np.ndarray) -> np.ndarray:
    return _POP16[x & 0xFFFF] + _POP16[x >> 16]


# --------------------------------------------------------------------------- #
# Konfiguration und Datentypen
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Config:
    # exakter Vergleich
    bit_threshold: int = 8            # max. Hamming-Distanz eines lokalen Treffers
    bit_threshold_fallback: int = 10  # zweiter Versuch bei stark verrauschten Paaren
    max_gap_items: int = 8            # tolerierte Fehlstellen in Folge
    min_match_ratio: float = 0.78
    min_seconds: float = 15.0
    max_seconds: float = 120.0
    # Suchfenster
    intro_window_sec: float = 720.0
    outro_window_sec: float = 720.0
    max_shift_sec: float = 300.0      # max. Zeitversatz des Segments zwischen zwei Folgen
    # FFT-Kandidaten
    top_offsets: int = 8
    min_z: float = 4.0                # Mindest-z-Wert der Korrelationsspitze
    peak_merge_items: int = 4
    # Konsens
    partners_per_episode: int = 4
    cands_per_partner: int = 2
    cluster_endpoint_tolerance_sec: float = 8.0
    cluster_min_iou: float = 0.55
    min_consensus_partners: int = 2
    auto_partners: int = 3
    auto_partners_with_trusted: int = 2
    auto_confirm_threshold: float = 0.92
    review_threshold: float = 0.72
    # Grenzen
    snap_sec: float = 2.0
    min_partner_seconds: float = 30.0  # kuerzere Partner-Fenster gelten als leer


@dataclass
class FpWindow:
    fp: np.ndarray
    start_sec: float = 0.0            # absolute Dateizeit des extrahierten Fensters
    item_sec: float = DEFAULT_ITEM_SEC
    delay_sec: float = DEFAULT_DELAY_SEC  # Chromaprint-Puffer; Metadatum, KEIN Zeitoffset
    time_offset_sec: float = 0.0      # optionale empirische Kalibrierung der Dateizeit
    episode_id: str = ""
    duration_sec: Optional[float] = None
    trusted: bool = False
    trusted_ranges: Sequence[Tuple[float, float]] = ()
    _sig: str = field(init=False, repr=False)

    def __post_init__(self):
        self.fp = np.ascontiguousarray(np.asarray(self.fp, dtype=np.uint64) & 0xFFFFFFFF,
                                       dtype=np.uint32)
        # Verhindert PairCache-Kollisionen, auch wenn episode_id leer oder doppelt ist.
        self.fp.flags.writeable = False
        self._sig = hashlib.sha256(self.fp.tobytes()).hexdigest()

    def __len__(self):
        return int(self.fp.shape[0])

    def t(self, i: float) -> float:
        """Dateizeit der Fingerprint-Item-Grenze i.

        Wichtig: Chromaprints interner `delay` ist die Audioabdeckung eines Hashes,
        nicht eine Verschiebung der Hash-Index-Zeit. Der offizielle Matcher setzt
        hash_time(i) = i * item_duration. Eine manuell gemessene konstante Korrektur
        gehoert daher in `time_offset_sec`, nicht in `delay_sec`.
        """
        return self.start_sec + i * self.item_sec + self.time_offset_sec

    def coverage_end(self, i: float) -> float:
        """Spaetestes Audioende, das der Hash an Index i intern mit abdeckt."""
        return self.t(i) + self.delay_sec

    @property
    def key(self) -> Tuple:
        return (
            self.episode_id,
            self.start_sec,
            len(self),
            self.item_sec,
            self.time_offset_sec,
            self.duration_sec,
            self._sig,
        )


@dataclass
class Cand:
    a_s: int
    a_e: int
    b_s: int
    b_e: int
    quality: float
    ratio: float
    mean_ham: float
    z: float
    truncated: bool = False

    def swapped(self) -> "Cand":
        return Cand(self.b_s, self.b_e, self.a_s, self.a_e, self.quality, self.ratio,
                    self.mean_ham, self.z, self.truncated)


@dataclass
class Detection:
    kind: str
    status: str
    start_sec: Optional[float] = None
    end_sec: Optional[float] = None
    confidence: float = 0.0
    partners_supporting: int = 0
    partners_used: int = 0
    details: Dict = field(default_factory=dict)

    @property
    def found(self) -> bool:
        return self.start_sec is not None and self.status != REJECTED


# --------------------------------------------------------------------------- #
# Fenster planen
# --------------------------------------------------------------------------- #
def plan_windows(duration_sec: float, cfg: Config = Config()):
    """Liefert ((intro_start, intro_end), (outro_start, outro_end)) in Dateizeit.
    Kurze Folgen: jedes Fenster hoechstens ein Drittel der Laufzeit, kein Ueberlappen."""
    il = min(cfg.intro_window_sec, duration_sec / 3.0)
    ol = min(cfg.outro_window_sec, duration_sec / 3.0)
    return (0.0, il), (max(0.0, duration_sec - ol), duration_sec)


# --------------------------------------------------------------------------- #
# Kandidaten per FFT-Kreuzkorrelation
# --------------------------------------------------------------------------- #
def _bit_matrix(fp: np.ndarray) -> np.ndarray:
    bits = (fp[:, None] >> np.arange(32, dtype=np.uint32)) & 1
    return bits.astype(np.float32) * 2.0 - 1.0


def _xcorr_lags(a: np.ndarray, b: np.ndarray, cache=None):
    """corr[k] = sum_i sum_bit sa[i]*sb[i+k]  =  sum_i (32 - 2*hamming(a[i], b[i+k]))."""
    na, nb = len(a), len(b)
    n = na + nb - 1
    nfft = 1 << (n - 1).bit_length()
    A = cache.transform(a, nfft) if cache is not None else np.fft.rfft(_bit_matrix(a), nfft, axis=0)
    B = cache.transform(b, nfft) if cache is not None else np.fft.rfft(_bit_matrix(b), nfft, axis=0)
    s = (np.conj(A) * B).sum(axis=1)
    c = np.fft.irfft(s, nfft)
    lags = np.arange(-(na - 1), nb)
    vals = c[lags % nfft]
    overlap = np.minimum(na, nb - lags) - np.maximum(0, -lags)
    return lags, vals, overlap


def _select_offsets(a: FpWindow, b: FpWindow, kind: str, cfg: Config, cache=None):
    min_items = max(8, int(cfg.min_seconds / a.item_sec))
    lags, vals, overlap = _xcorr_lags(a.fp, b.fp, cache)
    z = vals / np.sqrt(32.0 * np.maximum(overlap, 1))
    ok = overlap >= min_items
    # erlaubter Zeitversatz des Segments
    delta = (b.t(0) - a.t(0)) + lags * a.item_sec
    if kind == "outro" and a.duration_sec and b.duration_sec:
        delta = delta - (b.duration_sec - a.duration_sec)
    ok &= np.abs(delta) <= cfg.max_shift_sec
    ok &= z >= cfg.min_z
    idx = np.flatnonzero(ok)
    if idx.size == 0:
        return []
    order = idx[np.argsort(-z[idx])]
    chosen: List[int] = []
    for i in order:
        if all(abs(int(lags[i]) - int(lags[j])) > cfg.peak_merge_items for j in chosen):
            chosen.append(i)
            if len(chosen) >= cfg.top_offsets:
                break
    return [(int(lags[i]), float(z[i])) for i in chosen]


def _segments_at(a: FpWindow, b: FpWindow, k: int, z: float, kind: str, cfg: Config) -> List[Cand]:
    """Strenge Schwelle zuerst; nur wenn nichts passt, die lockerere (Re-Encodes, Mix-Unterschiede).
    Die Match-Rate-Pflicht (min_match_ratio) schuetzt weiterhin vor Zufallstreffern."""
    for thr in dict.fromkeys((cfg.bit_threshold, cfg.bit_threshold_fallback)):
        out = _segments_thr(a, b, k, z, kind, cfg, thr)
        if out:
            return out
    return []


def _segments_thr(a: FpWindow, b: FpWindow, k: int, z: float, kind: str, cfg: Config,
                  thr: int) -> List[Cand]:
    i0 = max(0, -k)
    i1 = min(len(a), len(b) - k)
    if i1 - i0 < 2:
        return []
    d = popcount32(a.fp[i0:i1] ^ b.fp[i0 + k:i1 + k]).astype(np.int16)
    good = d <= thr
    idx = np.flatnonzero(good)
    if idx.size == 0:
        return []
    cuts = np.flatnonzero(np.diff(idx) > cfg.max_gap_items + 1)
    starts = np.concatenate(([idx[0]], idx[cuts + 1]))
    ends = np.concatenate((idx[cuts], [idx[-1]])) + 1
    slack = thr + 2
    max_items = int(cfg.max_seconds / a.item_sec)
    min_items = int(cfg.min_seconds / a.item_sec)
    out: List[Cand] = []
    for s, e in zip(starts, ends):
        s, e = int(s), int(e)
        # Raender mit etwas lockererer Schwelle um hoechstens 4 Items erweitern
        for _ in range(4):
            if s > 0 and d[s - 1] <= slack:
                s -= 1
            else:
                break
        for _ in range(4):
            if e < len(d) and d[e] <= slack:
                e += 1
            else:
                break
        truncated = False
        if e - s > max_items:
            truncated = True
            if kind == "outro":
                s = e - max_items       # Outro: Ende bleibt
            else:
                e = s + max_items       # Intro: Anfang bleibt
        if e - s < min_items:
            continue
        seg = d[s:e]
        ratio = float((seg <= thr).mean())
        if ratio < cfg.min_match_ratio:
            continue
        # Silence, drones and tiny repeating loops carry too little information
        # to identify a title sequence, even if their Hamming score is perfect.
        if min(len(np.unique(a.fp[i0+s:i0+e])), len(np.unique(b.fp[i0+s+k:i0+e+k]))) < max(15, (e-s)//5):
            continue
        mh = float(seg.mean())
        q = 0.65 * ratio + 0.35 * (1.0 - mh / 32.0)
        out.append(Cand(i0 + s, i0 + e, i0 + s + k, i0 + e + k, q, ratio, mh, z, truncated))
    return out


class PairCache:
    """Cache fuer Paarvergleiche; Gegenrichtung wird aus demselben Eintrag abgeleitet."""

    def __init__(self, max_pairs=128, max_fft_bytes=16 * 1024 * 1024):
        self._d = OrderedDict()
        self._fft = OrderedDict()
        self.max_pairs, self.max_fft_bytes = max_pairs, max_fft_bytes
        self.fft_bytes = self.pair_hits = self.fft_hits = 0
        self._lock = RLock()

    def get(self, a: FpWindow, b: FpWindow, kind: str, cfg=Config()):
        ka, kb = a.key, b.key
        with self._lock:
            for key, reverse in (((ka, kb, kind, cfg), False), ((kb, ka, kind, cfg), True)):
                if key in self._d:
                    self._d.move_to_end(key)
                    self.pair_hits += 1
                    return [c.swapped() for c in self._d[key]] if reverse else list(self._d[key])
        return None

    def put(self, a: FpWindow, b: FpWindow, kind: str, cands: List[Cand], cfg=Config()):
        with self._lock:
            key = (a.key, b.key, kind, cfg)
            self._d[key] = list(cands)
            self._d.move_to_end(key)
            while len(self._d) > self.max_pairs:
                self._d.popitem(last=False)

    def transform(self, fp, nfft):
        key = (hashlib.sha256(fp.tobytes()).digest(), len(fp), nfft)
        with self._lock:
            if key in self._fft:
                self._fft.move_to_end(key)
                self.fft_hits += 1
                return self._fft[key]
        value = np.fft.rfft(_bit_matrix(fp), nfft, axis=0)
        value.flags.writeable = False
        with self._lock:
            if key not in self._fft and value.nbytes <= self.max_fft_bytes:
                while self._fft and self.fft_bytes + value.nbytes > self.max_fft_bytes:
                    self.fft_bytes -= self._fft.popitem(last=False)[1].nbytes
                self._fft[key] = value
                self.fft_bytes += value.nbytes
        return value

    def stats(self):
        with self._lock:
            return dict(pairs=len(self._d), pair_hits=self.pair_hits,
                        fft_entries=len(self._fft), fft_bytes=self.fft_bytes, fft_hits=self.fft_hits)


def pair_candidates(a: FpWindow, b: FpWindow, kind: str, cfg: Config = Config(),
                    cache: Optional[PairCache] = None) -> List[Cand]:
    if abs(a.item_sec - b.item_sec) > 1e-9:
        raise ValueError("unterschiedliche item_sec")
    if cache is not None:
        hit = cache.get(a, b, kind, cfg)
        if hit is not None:
            return hit
    cands: List[Cand] = []
    for k, z in _select_offsets(a, b, kind, cfg, cache):
        cands.extend(_segments_at(a, b, k, z, kind, cfg))
    cands.sort(key=lambda c: -(c.quality * math.sqrt(c.a_e - c.a_s)))
    cands = cands[:cfg.cands_per_partner]
    if cache is not None:
        cache.put(a, b, kind, cands, cfg)
    return cands


# --------------------------------------------------------------------------- #
# Konsens
# --------------------------------------------------------------------------- #
@dataclass
class _C:
    ts: float
    te: float
    q: float
    pid: int
    trusted: bool
    trunc: bool


def _iou(a0, a1, b0, b1):
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    union = max(a1, b1) - min(a0, b0)
    return inter / union if union > 0 else 0.0


def _close(c: _C, r: _C, cfg: Config) -> bool:
    tol = cfg.cluster_endpoint_tolerance_sec
    if abs(c.ts - r.ts) <= tol and abs(c.te - r.te) <= tol:
        return True
    return _iou(c.ts, c.te, r.ts, r.te) >= cfg.cluster_min_iou


def _best_per_partner(cl: List[_C]) -> List[_C]:
    best: Dict[int, _C] = {}
    for c in cl:
        if c.pid not in best or c.q > best[c.pid].q:
            best[c.pid] = c
    return list(best.values())


def _position_score(kind: str, start: float, end: float, target: FpWindow) -> float:
    if kind == "intro":
        return float(np.clip(1.0 - (start - 180.0) / 720.0, 0.0, 1.0))
    total = target.duration_sec or target.t(len(target))
    tail = total - end
    return float(np.clip(1.0 - (tail - 120.0) / 780.0, 0.0, 1.0))


def snap_to(t: float, points: Sequence[float], tol: float) -> float:
    """Rastet t auf den naechsten Punkt (Stille/Schwarzbild) innerhalb tol ein."""
    if not points:
        return t
    p = min(points, key=lambda x: abs(x - t))
    return p if abs(p - t) <= tol else t


def detect(target: FpWindow, partners: Sequence[FpWindow], kind: str,
           cfg: Config = Config(), cache: Optional[PairCache] = None,
           snap_points: Sequence[float] = ()) -> Detection:
    """kind: 'intro' oder 'outro'. Partner der gleichen Staffel liefert der Aufrufer."""
    if kind not in ("intro", "outro"):
        raise ValueError(kind)
    min_items = int(cfg.min_partner_seconds / target.item_sec)
    # trusted zuerst, dann Reihenfolge des Aufrufers (z.B. naechste Folgennummern)
    plist = [p for p in partners if p is not target]
    plist.sort(key=lambda p: not p.trusted)
    valid = [p for p in plist if len(p) >= min_items][:cfg.partners_per_episode]
    det = Detection(kind=kind, status=REJECTED, partners_used=len(valid))
    if len(target) < min_items or len(valid) < cfg.min_consensus_partners:
        det.details["reason"] = "zu wenige gueltige Fingerprints/Partner"
        return det

    allc: List[_C] = []
    for pid, p in enumerate(valid):
        for c in pair_candidates(target, p, kind, cfg, cache):
            # Trust belongs to the approved segment, not every recurring song
            # anywhere in the same episode's twelve-minute window.
            trusted = p.trusted and (not p.trusted_ranges or any(
                abs(p.t(c.b_s)-start) <= cfg.snap_sec and abs(p.t(c.b_e)-end) <= cfg.snap_sec
                for start, end in p.trusted_ranges))
            allc.append(_C(target.t(c.a_s), target.t(c.a_e), c.quality, pid, trusted, c.truncated))
    if not allc:
        det.details["reason"] = "keine Kandidaten"
        return det

    clusters: List[List[_C]] = []
    for c in sorted(allc, key=lambda x: -x.q):
        for cl in clusters:
            if _close(c, cl[0], cfg):
                cl.append(c)
                break
        else:
            clusters.append([c])
    best_cl = max(clusters, key=lambda cl: (len(_best_per_partner(cl)),
                                            sum(c.q for c in _best_per_partner(cl))))
    members = _best_per_partner(best_cl)
    support = len(members)
    starts = np.array([m.ts for m in members])
    ends = np.array([m.te for m in members])
    start, end = float(np.median(starts)), float(np.median(ends))
    det.partners_supporting = support
    det.details.update(raw_start=start, raw_end=end,
                       truncated=any(m.trunc for m in members),
                       clusters=len(clusters))
    det.details['trusted_episode_ids'] = [valid[m.pid].episode_id for m in members if m.trusted]

    mean_q = float(np.mean([m.q for m in members]))
    spread = (float(np.std(starts)) + float(np.std(ends))) / 2.0
    consistency = max(0.0, 1.0 - spread / cfg.cluster_endpoint_tolerance_sec)
    pos = _position_score(kind, start, end, target)
    conf = (0.45 * mean_q + 0.30 * (support / len(valid)) + 0.15 * consistency + 0.10 * pos)
    det.confidence = round(conf, 4)
    det.details.update(mean_quality=mean_q, spread_sec=spread, position=pos)

    # An equally plausible recurring recap/song is a competing interpretation,
    # not another vote for the chosen title. Preserve it for human inspection.
    rivals = [_best_per_partner(cl) for cl in clusters if cl is not best_cl]
    ambiguous = any(len(rival) >= support and
                    float(np.mean([m.q for m in rival])) >= mean_q - .025
                    for rival in rivals)
    det.details['ambiguous'] = ambiguous
    if ambiguous:
        det.details['reason'] = 'mehrere gleichwertige wiederkehrende Abschnitte'
        return det

    if support < cfg.min_consensus_partners:
        det.details["reason"] = "kein Konsens"
        return det

    if snap_points:
        start = snap_to(start, snap_points, cfg.snap_sec)
        end = snap_to(end, snap_points, cfg.snap_sec)
    det.start_sec, det.end_sec = round(start, 3), round(end, 3)

    has_trusted = any(m.trusted for m in members)
    enough = support >= cfg.auto_partners or (has_trusted and support >= cfg.auto_partners_with_trusted)
    bounds_consistent = float(np.ptp(starts)) <= 2.0 and float(np.ptp(ends)) <= 2.0
    det.details['boundaries_consistent'] = bounds_consistent
    if conf >= cfg.auto_confirm_threshold and enough and spread <= 1.0 and bounds_consistent and not det.details['truncated']:
        det.status = AUTO
    elif conf >= cfg.review_threshold:
        det.status = REVIEW
    else:
        det.status = REJECTED
    return det


def resolve_overlap(intro: Detection, outro: Detection) -> Tuple[Detection, Detection]:
    """Gleicher Abschnitt fuer Intro und Outro vorgeschlagen: nur der staerkere bleibt."""
    if not (intro.found and outro.found):
        return intro, outro
    if _iou(intro.start_sec, intro.end_sec, outro.start_sec, outro.end_sec) > 0.0:
        weak = outro if outro.confidence < intro.confidence else intro
        weak.status = REJECTED
        weak.details["reason"] = "ueberlappt mit staerkerem Abschnitt"
    return intro, outro


# --------------------------------------------------------------------------- #
# Zeitbasis und Kalibrierung
# --------------------------------------------------------------------------- #
def chromaprint_timebase(algorithm: int = CHROMAPRINT_C_ALGO_TEST2) -> Tuple[float, float, str]:
    """(item_sec, delay_sec, quelle) fuer den C-API-Algorithmus.

    `fpcalc -algorithm 2` mappt intern auf C-Algorithmus 1 (TEST2). Deshalb darf
    hier NICHT die CLI-Zahl 2 direkt an chromaprint_new() uebergeben werden.
    """
    try:
        import ctypes
        import ctypes.util

        name = ctypes.util.find_library("chromaprint")
        if not name:
            raise OSError("libchromaprint nicht gefunden")
        lib = ctypes.CDLL(name)
        vp = ctypes.c_void_p

        lib.chromaprint_new.restype = vp
        lib.chromaprint_new.argtypes = [ctypes.c_int]
        lib.chromaprint_free.argtypes = [vp]

        for fn in ("chromaprint_get_sample_rate",
                   "chromaprint_get_item_duration",
                   "chromaprint_get_delay"):
            f = getattr(lib, fn)
            f.argtypes = [vp]
            f.restype = ctypes.c_int

        ctx = lib.chromaprint_new(int(algorithm))
        if not ctx:
            raise RuntimeError("chromaprint_new() fehlgeschlagen")
        try:
            sr = int(lib.chromaprint_get_sample_rate(ctx))
            item = int(lib.chromaprint_get_item_duration(ctx))
            delay = int(lib.chromaprint_get_delay(ctx))
            if sr <= 0 or item <= 0 or delay < 0:
                raise RuntimeError(f"ungueltige Timebase sr={sr} item={item} delay={delay}")

            # Wenn verfuegbar, pruefen wir auch, ob der Kontext wirklich TEST2 nutzt.
            try:
                lib.chromaprint_get_algorithm.argtypes = [vp]
                lib.chromaprint_get_algorithm.restype = ctypes.c_int
                actual = int(lib.chromaprint_get_algorithm(ctx))
                if actual != int(algorithm):
                    raise RuntimeError(f"Algorithmus-Mismatch: angefordert={algorithm}, aktiv={actual}")
            except AttributeError:
                pass
        finally:
            lib.chromaprint_free(ctx)

        return item / sr, delay / sr, f"libchromaprint:{name}:c_algo={algorithm}"
    except Exception as exc:  # noqa: BLE001
        return DEFAULT_ITEM_SEC, DEFAULT_DELAY_SEC, f"Standardwerte TEST2 ({exc})"


def suggest_time_offset(pred_starts: Sequence[float], true_starts: Sequence[float],
                        current_offset: float = 0.0) -> float:
    """Schaetzt eine additive Zeitkorrektur aus manuell geprueften Grenzen.

    Wenn erkannte Starts z.B. konstant 0.4 s zu frueh liegen, wird +0.4 s
    vorgeschlagen. Das ist absichtlich getrennt vom Chromaprint-internen delay.
    """
    if len(pred_starts) != len(true_starts) or not pred_starts:
        raise ValueError("pred_starts und true_starts muessen gleich lang und nicht leer sein")
    diff = np.median(np.asarray(true_starts, float) - np.asarray(pred_starts, float))
    return float(current_offset + diff)


def suggest_delay(pred_starts: Sequence[float], true_starts: Sequence[float],
                  current_delay: float = 0.0) -> float:
    """Rueckwaertskompatibler Alias. Rueckgabewert ist jetzt ein ADDITIVER Zeitoffset.

    Neue Aufrufer sollten `suggest_time_offset()` verwenden.
    """
    return suggest_time_offset(pred_starts, true_starts, current_delay)


# --------------------------------------------------------------------------- #
# Serialisierung
# --------------------------------------------------------------------------- #
def fp_to_blob(fp: np.ndarray) -> bytes:
    return np.ascontiguousarray(fp, dtype="<u4").tobytes()


def blob_to_fp(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype="<u4").astype(np.uint32)


def fp_cache_key(asset_key: str, audio_track: int, start_sec: float, dur_sec: float,
                 algo_version: str = "cp2-v3.1") -> str:
    return f"{asset_key}|a{audio_track}|{start_sec:.1f}+{dur_sec:.1f}|{algo_version}"


# --------------------------------------------------------------------------- #
# ffmpeg / fpcalc (nur Fenster decodieren)
# --------------------------------------------------------------------------- #
def extract_audio_window(src: str, start_sec: float, dur_sec: float, out_wav: str,
                         audio_track: int = 0, sample_rate: int = 11025,
                         timeout: int = 300) -> None:
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y",
           "-ss", f"{max(0.0, start_sec):.3f}", "-i", src,
           "-t", f"{dur_sec:.3f}", "-map", f"0:a:{audio_track}",
           "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "wav", out_wav]
    subprocess.run(cmd, check=True, timeout=timeout, capture_output=True)


def fingerprint_wav(wav: str, max_len_sec: int = 3600, timeout: int = 300,
                    fpcalc_algorithm: int = FPCALC_ALGORITHM) -> np.ndarray:
    # Algorithmus explizit setzen, damit fpcalc-Defaults die Zeitbasis nicht unbemerkt aendern.
    cmd = ["fpcalc", "-algorithm", str(fpcalc_algorithm),
           "-raw", "-json", "-length", str(max_len_sec), wav]
    try:
        res = subprocess.run(cmd, check=True, timeout=timeout, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("fpcalc fehlt (Debian/Raspberry Pi: Paket libchromaprint-tools)") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"fpcalc fehlgeschlagen: {exc.stderr.strip()}") from exc
    data = json.loads(res.stdout)
    fp = data.get("fingerprint")
    if isinstance(fp, str):
        fp = [int(x) for x in fp.split(",") if x]
    if not fp:
        raise RuntimeError("fpcalc lieferte einen leeren Fingerprint")
    return (np.asarray(fp, dtype=np.int64) & 0xFFFFFFFF).astype(np.uint32)


def fingerprint_window(src: str, start_sec: float, dur_sec: float, audio_track: int = 0,
                       episode_id: str = "", duration_sec: Optional[float] = None,
                       trusted: bool = False,
                       timebase: Optional[Tuple[float, float]] = None,
                       time_offset_sec: float = 0.0) -> FpWindow:
    item, delay = timebase if timebase else chromaprint_timebase()[:2]
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "w.wav")
        extract_audio_window(src, start_sec, dur_sec, wav, audio_track)
        fp = fingerprint_wav(wav)
    return FpWindow(fp, start_sec=start_sec, item_sec=item, delay_sec=delay,
                    time_offset_sec=time_offset_sec, episode_id=episode_id,
                    duration_sec=duration_sec, trusted=trusted)


def find_silence_boundary_points(src: str, start_sec: float, dur_sec: float,
                                 audio_track: int = 0, noise_db: int = -35,
                                 min_silence: float = 0.25,
                                 timeout: int = 120) -> List[float]:
    """Stille-Raender als absolute Dateizeit.

    `asetpts=PTS-STARTPTS` erzwingt relative Filter-Zeiten; danach wird start_sec
    genau einmal addiert. So sind lokale Dateien und gesuchte Remote-Quellen konsistent.
    """
    af = (f"asetpts=PTS-STARTPTS,"
          f"silencedetect=noise={noise_db}dB:d={min_silence}")
    cmd = ["ffmpeg", "-hide_banner", "-nostdin",
           "-ss", f"{max(0.0, start_sec):.3f}", "-i", src,
           "-t", f"{dur_sec:.3f}", "-map", f"0:a:{audio_track}", "-vn",
           "-af", af, "-f", "null", "-"]
    try:
        res = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg fehlt") from exc
    pts = [float(m.group(1)) + start_sec
           for m in re.finditer(r"silence_(?:start|end):\s*(-?[\d.]+)", res.stderr)]
    return sorted(set(round(p, 3) for p in pts if start_sec - 0.1 <= p <= start_sec + dur_sec + 0.1))


def find_black_boundary_points(src: str, start_sec: float, dur_sec: float,
                               min_black: float = 0.20, pix_th: float = 0.10,
                               timeout: int = 120) -> List[float]:
    """Schwarzbild-Raender als absolute Dateizeit (optional, da zusaetzlicher Video-Decode)."""
    vf = (f"setpts=PTS-STARTPTS,"
          f"blackdetect=d={min_black}:pix_th={pix_th}")
    cmd = ["ffmpeg", "-hide_banner", "-nostdin",
           "-ss", f"{max(0.0, start_sec):.3f}", "-i", src,
           "-t", f"{dur_sec:.3f}", "-an",
           "-vf", vf, "-f", "null", "-"]
    try:
        res = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg fehlt") from exc
    pts = [float(m.group(1)) + start_sec
           for m in re.finditer(r"black_(?:start|end):\s*(-?[\d.]+)", res.stderr)]
    return sorted(set(round(p, 3) for p in pts if start_sec - 0.1 <= p <= start_sec + dur_sec + 0.1))


def find_boundary_points(src: str, start_sec: float, dur_sec: float, audio_track: int = 0,
                         noise_db: int = -35, min_silence: float = 0.25,
                         include_black: bool = False, min_black: float = 0.20,
                         pix_th: float = 0.10, timeout: int = 120) -> List[float]:
    """Stille-Raender und optional Schwarzbild-Raender als Einrast-Kandidaten."""
    pts = find_silence_boundary_points(
        src, start_sec, dur_sec, audio_track=audio_track,
        noise_db=noise_db, min_silence=min_silence, timeout=timeout
    )
    if include_black:
        pts.extend(find_black_boundary_points(
            src, start_sec, dur_sec, min_black=min_black, pix_th=pix_th, timeout=timeout
        ))
    return sorted(set(pts))


# --------------------------------------------------------------------------- #
# Selbsttest (synthetisch, ohne Audio)
# --------------------------------------------------------------------------- #
def _rand_fp(rng, n):
    return rng.integers(0, 2 ** 32, n, dtype=np.uint64).astype(np.uint32)


def _noisy(rng, fp, p_bit, p_high=None):
    n = len(fp)
    flips = rng.random((n, 32)) < p_bit
    if p_high is not None:
        flips[:, 20:] = rng.random((n, 12)) < p_high
    mask = (flips.astype(np.uint64) << np.arange(32, dtype=np.uint64)).sum(axis=1)
    return fp ^ mask.astype(np.uint32)


def _make_set(rng, n_eps, shared_len, kind, p_bit=0.04, p_high=None, total=5800,
              dur=2700.0, shared=True):
    item = DEFAULT_ITEM_SEC
    shared_fp = _rand_fp(rng, shared_len)
    wins, truths = [], []
    for e in range(n_eps):
        if kind == "intro":
            pre = int(rng.integers(0, 500))
            start_sec = 0.0
        else:
            tail = int(rng.integers(40, 600))
            pre = total - shared_len - tail
            start_sec = dur - total * item
        post = total - pre - shared_len
        mid = _noisy(rng, shared_fp, p_bit, p_high) if shared else _rand_fp(rng, shared_len)
        fp = np.concatenate([_rand_fp(rng, pre), mid, _rand_fp(rng, post)])
        wins.append(FpWindow(fp, start_sec=start_sec, episode_id=f"e{e}", duration_sec=dur))
        truths.append((start_sec + pre * item, start_sec + (pre + shared_len) * item))
    return wins, truths


def _selftest() -> int:
    rng = np.random.default_rng(7)
    cfg = Config()
    fails = 0
    rows = []

    def check(name, cond, info=""):
        nonlocal fails
        rows.append(("OK  " if cond else "FAIL") + f" {name} {info}")
        fails += 0 if cond else 1

    # 1/2/3: Intro, Intro mit hohem Bitrauschen, Outro mit absoluter Fensterbasis
    for name, kind, kw, tol in [
        ("intro_normal", "intro", dict(p_bit=0.04), 0.4),
        ("intro_hochbit_rauschen", "intro", dict(p_bit=0.04, p_high=0.40), 1.0),
        ("outro_fensterbasis", "outro", dict(p_bit=0.05), 0.4),
    ]:
        wins, truths = _make_set(rng, 5, 420, kind, **kw)
        t0 = time.perf_counter()
        det = detect(wins[0], wins[1:], kind, cfg)
        dt = (time.perf_counter() - t0) * 1000
        es = abs(det.start_sec - truths[0][0]) if det.found else 99
        ee = abs(det.end_sec - truths[0][1]) if det.found else 99
        check(name, det.found and es <= tol and ee <= tol,
              f"status={det.status} conf={det.confidence} start_err={es:.2f}s end_err={ee:.2f}s {dt:.0f} ms")
        if name == "intro_normal":
            check("intro_normal_auto", det.status == AUTO)

    # 4: nur zwei Partner ohne/mit trusted
    wins, truths = _make_set(rng, 3, 420, "intro")
    det2 = detect(wins[0], wins[1:], "intro", cfg)
    check("zwei_partner_nicht_auto", det2.found and det2.status != AUTO, f"status={det2.status}")
    wins[1].trusted = True
    det2t = detect(wins[0], wins[1:], "intro", cfg)
    check("zwei_partner_mit_trusted_auto", det2t.status == AUTO, f"status={det2t.status} conf={det2t.confidence}")

    # 5: gemeinsamer Abschnitt fehlt
    wins, _ = _make_set(rng, 5, 420, "intro", shared=False)
    det3 = detect(wins[0], wins[1:], "intro", cfg)
    check("kein_gemeinsamer_abschnitt", det3.status == REJECTED, f"status={det3.status}")

    # 6: Fensterplanung kurzer Folge
    iw, ow = plan_windows(20 * 60.0, cfg)
    check("kurze_folge_kein_ueberlappen", iw[1] <= ow[0], f"intro={iw} outro={ow}")

    # 7: Pair-Cache (Gegenrichtung)
    wins, _ = _make_set(rng, 3, 420, "intro")
    cache = PairCache()
    c1 = pair_candidates(wins[0], wins[1], "intro", cfg, cache)
    c2 = pair_candidates(wins[1], wins[0], "intro", cfg, cache)
    check("pair_cache_rueckrichtung",
          bool(c1) and bool(c2) and c1[0].a_s == c2[0].b_s and len(cache._d) == 1)

    # 8: Serialisierung
    fp = wins[0].fp
    check("blob_roundtrip", np.array_equal(blob_to_fp(fp_to_blob(fp)), fp) and len(fp_to_blob(fp)) == 4 * len(fp))

    # 9: additive Zeit-Kalibrierung (Chromaprint-delay wird NICHT als Offset benutzt)
    nd = suggest_time_offset([10.0, 20.0, 30.0], [10.4, 20.4, 30.4], 0.0)
    check("zeitoffset_kalibrierung", abs(nd - 0.4) < 1e-9, f"neuer offset={nd:.2f}")

    # 10: Timebase-Semantik: Index 0 liegt am Fensterstart, nicht start-delay.
    tw = FpWindow(np.array([1, 2, 3], dtype=np.uint32), start_sec=100.0,
                  delay_sec=DEFAULT_DELAY_SEC, time_offset_sec=0.25)
    check("timebase_kein_delay_shift",
          abs(tw.t(0) - 100.25) < 1e-9 and abs(tw.coverage_end(0) - (100.25 + DEFAULT_DELAY_SEC)) < 1e-9)

    # 11: Cache-Schluessel unterscheiden identisch dimensionierte, aber andere Fingerprints.
    wa = FpWindow(np.array([1, 2, 3, 4], dtype=np.uint32), episode_id="")
    wb = FpWindow(np.array([1, 2, 3, 5], dtype=np.uint32), episode_id="")
    check("cache_key_inhaltssicher", wa.key != wb.key)

    print("\n".join(rows))
    print(f"SELFTEST {'OK' if fails == 0 else 'FEHLER'}: {len(rows) - fails}/{len(rows)}")
    return 0 if fails == 0 else 1


def _doctor() -> int:
    """Prueft Laufzeit-Abhaengigkeiten und die TEST2-Zeitbasis ohne Medien zu veraendern."""
    errors = 0
    print(f"Python: {sys.version.split()[0]}")
    print(f"NumPy: {np.__version__}")
    for exe in ("ffmpeg", "fpcalc"):
        path = shutil.which(exe)
        print(f"{exe}: {path or 'FEHLT'}")
        if not path:
            errors += 1

    item, delay, source = chromaprint_timebase()
    print(f"Chromaprint TEST2: item={item:.9f}s delay={delay:.6f}s source={source}")
    if abs(item - DEFAULT_ITEM_SEC) > 0.002:
        print("FEHLER: item_sec passt nicht zu TEST2/fpcalc -algorithm 2")
        errors += 1
    if abs(delay - DEFAULT_DELAY_SEC) > 0.15:
        print("WARNUNG: delay weicht von TEST2-Referenz ab; Version/Build pruefen")

    if shutil.which("fpcalc"):
        try:
            ver = subprocess.run(["fpcalc", "-version"], capture_output=True, text=True, timeout=10)
            print((ver.stdout or ver.stderr).strip())
        except Exception as exc:  # noqa: BLE001
            print(f"WARNUNG: fpcalc-Version nicht lesbar: {exc}")

    print("DOCTOR OK" if errors == 0 else f"DOCTOR FEHLER: {errors}")
    return 0 if errors == 0 else 2


def _write_e2e_wav(path: str, seconds: float = 36.0, sr: int = DEFAULT_SAMPLE_RATE) -> None:
    """Deterministisches Testsignal fuer einen echten ffmpeg/fpcalc-End-to-End-Test."""
    n = int(seconds * sr)
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(12345)
    # Zeitlich veraenderliches, breitbandiges Signal; deutlich robuster als ein einzelner Sinus.
    sweep = np.sin(2 * np.pi * (180.0 * t + 7.5 * t * t))
    tone2 = np.sin(2 * np.pi * (430.0 + 55.0 * np.sin(2 * np.pi * 0.17 * t)) * t)
    steps = ((np.floor(t * 2.0) % 7) - 3.0) / 3.0
    noise = rng.normal(0.0, 0.16, n)
    x = np.clip(0.40 * sweep + 0.32 * tone2 + 0.16 * steps + noise, -0.95, 0.95)
    pcm = (x * 30000.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def _e2e_test() -> int:
    """Echter Test ueber WAV -> ffmpeg-Fenster -> fpcalc -> FFT/Hamming-Matcher."""
    if _doctor() != 0:
        return 2
    item, delay, _ = chromaprint_timebase()
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "full.wav")
        cut = os.path.join(td, "cut.wav")
        _write_e2e_wav(src)
        extract_audio_window(src, 10.0, 18.0, cut)
        full_fp = fingerprint_wav(src, max_len_sec=40)
        cut_fp = fingerprint_wav(cut, max_len_sec=20)

        a = FpWindow(full_fp, start_sec=0.0, item_sec=item, delay_sec=delay,
                     episode_id="full", duration_sec=36.0)
        b = FpWindow(cut_fp, start_sec=10.0, item_sec=item, delay_sec=delay,
                     episode_id="cut", duration_sec=18.0)
        cfg = Config(min_seconds=5.0, max_seconds=25.0, max_shift_sec=20.0,
                     min_match_ratio=0.70, top_offsets=8)
        cands = pair_candidates(a, b, "intro", cfg)
        if not cands:
            print("E2E FEHLER: kein gemeinsames Segment gefunden")
            return 3
        c = cands[0]
        got = a.t(c.a_s)
        err = abs(got - 10.0)
        print(f"E2E bester Treffer: start={got:.3f}s erwartet~10.000s "
              f"err={err:.3f}s ratio={c.ratio:.3f} mean_ham={c.mean_ham:.2f}")
        if err > 1.0:
            print("E2E FEHLER: Zeitbasis/Seek-Ausrichtung ausserhalb Toleranz")
            return 4
    print("E2E OK")
    return 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--selftest"
    if arg == "--timebase":
        print(chromaprint_timebase())
    elif arg == "--doctor":
        sys.exit(_doctor())
    elif arg == "--e2e":
        sys.exit(_e2e_test())
    elif arg == "--selftest":
        sys.exit(_selftest())
    else:
        print("Usage: skip_detector_v3_1.py [--selftest|--doctor|--e2e|--timebase]", file=sys.stderr)
        sys.exit(2)
