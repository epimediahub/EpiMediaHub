"""Read-only trusted-marker cache bridge for original EpiScene device lookup.

Original Flask endpoint MUST authenticate and rate limit before calling.
The caller passes canonical IDs from the persisted server identity row,
NOT client-supplied identifiers. No IPTV, remote calls, or database writes.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

IMDB_PATTERN = re.compile(r"^tt[0-9]{7,9}$")
CATEGORIES = frozenset(("intro", "recap", "outro"))
TRUSTED_SOURCES = frozenset(("introdb", "theintrodb"))
CACHE = Path("/var/lib/episcene-learning/trusted-sources.sqlite3")
MAX_SEGMENTS = 12
MAX_MATCHING_CACHE_ROWS = 40
MAX_DURATION_DELTA_MS = 1500


def _valid_id(name, value):
    if name == "imdb_id":
        value = str(value or "").strip()
        return value if IMDB_PATTERN.fullmatch(value) else ""
    try:
        number = int(value or 0)
        return number if 0 < number < 1000000000 else 0
    except (ValueError, TypeError, OverflowError):
        return 0


def _valid_descriptor(desc):
    if not isinstance(desc, dict) or desc.get("media_type") != "episode":
        return None
    try:
        season, episode, duration = (int(desc[k]) for k in
                                     ("season", "episode", "duration_ms"))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not (0 <= season <= 100 and 1 <= episode <= 2000
            and 30000 <= duration <= 86400000):
        return None
    return (season, episode, duration)


def _server_ids(identity, desc):
    if not isinstance(identity, dict):
        return None
    source_key = identity.get("source_key")
    if source_key is not None and source_key != desc.get("source_key"):
        return None
    found = {k: _valid_id(k, identity.get(k)) for k in
             ("imdb_id", "tvdb_id", "tmdb_id")}
    return found if any(found.values()) else None


def _marker_shape(segment, duration):
    if not isinstance(segment, dict):
        return None
    kind = segment.get("segment_type", segment.get("type"))
    a, b = segment.get("start_ms"), segment.get("end_ms")
    if kind not in CATEGORIES or type(a) is not int or type(b) is not int:
        return None
    if not 0 <= a < b <= duration:
        return None
    return kind, a, b


def _cache_candidates(conn, ids, episode, duration):
    """Query trusted cache by validated episode identity and cut duration."""
    season, ep = episode
    terms, params = [], []
    for idx, name in enumerate(("imdb_id", "tvdb_id", "tmdb_id")):
        value = ids[name]
        if not value:
            continue
        terms.append("json_extract(identity, '$[" + str(idx) + "]') = ?")
        params.append(value)
    if not terms:
        return []
    sql = (
        "SELECT identity,response FROM trusted_external_cache "
        "WHERE expires_at > CAST(strftime('%s','now') AS INTEGER) "
        "AND json_extract(identity,'$[4]')=? "
        "AND json_extract(identity,'$[5]')=? "
        "AND ABS(json_extract(identity,'$[6]')-?) <= ? "
        "AND (" + " OR ".join(terms) + ") "
        "LIMIT " + str(MAX_MATCHING_CACHE_ROWS))
    rows = conn.execute(sql, (season, ep, duration, MAX_DURATION_DELTA_MS, *params))
    candidates = []
    for raw_key, raw_value in rows:
        try:
            key, value = json.loads(raw_key), json.loads(raw_value)
            if not isinstance(key, list) or len(key) != 7 or not isinstance(value, dict):
                continue
            if key[3] != "default":
                continue
            if not any(ids[n] and key[i] == ids[n]
                       for i, n in enumerate(("imdb_id","tvdb_id","tmdb_id"))):
                continue
            if any(ids[n] and key[i] and ids[n] != key[i]
                   for i, n in enumerate(("imdb_id","tvdb_id","tmdb_id"))):
                continue
            candidates.append(value)
        except (ValueError, TypeError, KeyError):
            continue
    return candidates


def augment_authorized_segments(
    current,
    *,
    descriptor,
    persisted_identity,
    cache=CACHE,
):
    """Append trusted segments after the original authenticated lookup.

    The caller passes dict(identity) obtained from server SQLite, not
    identifiers from the untrusted device JSON body. All failure paths
    return current unchanged, and no original marker is replaced.
    """
    if not isinstance(current, list) or len(current) > MAX_SEGMENTS:
        return current
    parsed = _valid_descriptor(descriptor)
    if parsed is None:
        return current
    season, episode, duration = parsed
    existing = [_marker_shape(seg, duration) for seg in current]
    if any(row is None for row in existing):
        return current
    ids = _server_ids(persisted_identity, descriptor)
    if ids is None:
        return current
    p = Path(cache)
    if p.is_symlink() or not p.is_file():
        return current
    try:
        with sqlite3.connect(p.resolve().as_uri()+"?mode=ro", uri=True,
                             timeout=0.4) as conn:
            conn.execute("PRAGMA query_only=ON")
            batches = _cache_candidates(conn, ids, (season,episode), duration)
    except (sqlite3.Error, OSError, ValueError):
        return current
    if not batches:
        return current

    accepted = {}
    rejected = set()
    for batch in batches:
        rejected.update(kind for kind in (batch.get("conflicts") or []) if
                        kind in CATEGORIES)
        rows = batch.get("trusted_segments")
        if not isinstance(rows, list):
            continue
        for seg in rows:
            shape = _marker_shape(seg, duration)
            if (shape is None or seg.get("source") not in TRUSTED_SOURCES
                    or seg.get("trusted") is not True):
                continue
            kind, start, end = shape
            if kind in accepted:
                prior = accepted[kind]
                if abs(prior[0]-start) > 2500 or abs(prior[1]-end) > 2500:
                    rejected.add(kind)
            else:
                accepted[kind] = (start, end, seg["source"])
    result = list(current)
    seen = {entry[0] for entry in existing}
    for kind in ("recap", "intro", "outro"):
        if kind in seen or kind in rejected or kind not in accepted:
            continue
        start, end, source = accepted[kind]
        if any(min(end, b)-max(start,a) > 1000 for _,a,b in existing):
            continue
        if len(result) >= MAX_SEGMENTS:
            break
        item = {"segment_type": kind, "start_ms": start, "end_ms": end,
                "duration_ms": duration, "status": "approved",
                "source": source}
        result.append(item)
        existing.append((kind, start, end))
    return sorted(result, key=lambda x: (x["start_ms"], x["end_ms"]))
