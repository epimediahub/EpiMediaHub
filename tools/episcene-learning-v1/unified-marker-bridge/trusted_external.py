#!/usr/bin/env python3
"""Trusted, metadata-bound IntroDB and TheIntroDB resolver for EpiScene.

External markers are accepted as playback-ready *without human review* when
the episode identity was established independently by the authenticated
EpiScene backend and the available cut data does not contradict playback.
Only the existing playback route may expose this helper to a device.
Never imports a live server module or changes its SQLite databases.
"""
from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path

from bridge import Episode, KINDS, _get_json, parse_introdb, parse_theintrodb
from runtime_integration import _cache_path, playback_resolution

MAX_VERSION_DRIFT_MS = 30000
TIME_MATCH_TOLERANCE_MS = 2500
SCHEMA = """
CREATE TABLE IF NOT EXISTS trusted_external_cache (
 identity TEXT PRIMARY KEY, expires_at INT NOT NULL, created_at INT NOT NULL,
 response TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS trusted_cache_expiry ON trusted_external_cache(expires_at);
"""


def _call(fetch, url):
    try:
        reply = fetch(url)
    except (OSError, ValueError, TimeoutError):
        return {"status": "network_error", "data": None}
    if not isinstance(reply, dict) or not isinstance(reply.get("status"), str):
        return {"status": "invalid_response", "data": None}
    return reply


def _identity_ok(payload, ep, provider):
    """Reject an explicit identity mismatch; no fabricated identity fallback."""
    if not isinstance(payload, dict):
        return False
    if provider == "introdb":
        if payload.get("imdb_id") not in (None, ep.imdb_id):
            return False
    else:
        if ep.tvdb_id and payload.get("tvdb_id") not in (None, ep.tvdb_id):
            return False
        if ep.tmdb_id and payload.get("tmdb_id") not in (None, ep.tmdb_id):
            return False
    for field in ("season", "episode"):
        if field in payload and payload[field] is not None:
            try:
                if int(payload[field]) != getattr(ep, field):
                    return False
            except (ValueError, TypeError):
                return False
    if payload.get("kind") in ("versions", "episodes"):
        return False
    if provider == "theintrodb":
        duration = payload.get("group_duration_ms")
        if duration is not None:
            if type(duration) not in (float, int) or not math.isfinite(duration):
                return False
            if abs(duration - ep.duration_ms) > MAX_VERSION_DRIFT_MS:
                return False
    return True


def _get_candidates(ep, fetch):
    from urllib.parse import urlencode
    status, rows, absent = {}, [], set()
    if ep.imdb_id:
        url = "https://api.introdb.app/segments?" + urlencode({
            "imdb_id": ep.imdb_id, "season": ep.season, "episode": ep.episode})
        reply = _call(fetch, url)
        if reply["status"] == "ok" and _identity_ok(reply.get("data"), ep, "introdb"):
            payload = reply["data"]
            rows.extend(parse_introdb(payload, ep))
            absent.update(kind for kind in KINDS if payload.get("no_"+kind) is True)
        status["introdb"] = ("identity_or_cut_mismatch" if reply["status"] == "ok"
                            and not _identity_ok(reply.get("data"), ep, "introdb")
                            else reply["status"])
    else:
        status["introdb"] = "missing_imdb_id"
    key, value = (("tvdb_id", ep.tvdb_id) if ep.tvdb_id else
                  ("tmdb_id", ep.tmdb_id) if ep.tmdb_id else
                  ("imdb_id", ep.imdb_id))
    if value:
        url = "https://api.theintrodb.org/v4/media?" + urlencode({
            key: value, "season": ep.season, "episode": ep.episode,
            "duration_ms": ep.duration_ms, "mapping": ep.mapping,
            "details": "true", "merge_unknown": "false"})
        reply = _call(fetch, url)
        if reply["status"] == "ok" and _identity_ok(reply.get("data"), ep, "theintrodb"):
            rows.extend(parse_theintrodb(reply["data"], ep))
        status["theintrodb"] = ("identity_or_cut_mismatch" if reply["status"] == "ok"
                               and not _identity_ok(reply.get("data"), ep, "theintrodb")
                               else reply["status"])
    else:
        status["theintrodb"] = "missing_external_id"
    return rows, status, absent


def _near(a, b):
    return (a["kind"] == b["kind"]
            and abs(a["start_ms"] - b["start_ms"]) <= TIME_MATCH_TOLERANCE_MS
            and abs(a["end_ms"] - b["end_ms"]) <= TIME_MATCH_TOLERANCE_MS)


def _promote(rows, absent):
    """Both sources are trusted, but never auto-skip contradictory segments."""
    accepted, conflicts = [], set()
    for kind in KINDS:
        one = [r for r in rows if r["kind"] == kind and r["source"] == "introdb"]
        two = [r for r in rows if r["kind"] == kind and r["source"] == "theintrodb"]
        if kind in absent:
            if one or two:
                conflicts.add(kind)
            continue
        if one and two and any(not any(_near(a, b) for b in two) for a in one):
            conflicts.add(kind)
            continue
        if one and two and any(not any(_near(a, b) for a in one) for b in two):
            conflicts.add(kind)
            continue
        dedup = []
        for r in one + two:
            if not any(_near(r, x) for x in dedup):
                dedup.append(r)
        accepted.extend(dedup)
    # Different skip actions must not overlap and accidentally hide content.
    for a in accepted:
        for b in accepted:
            if a is b or a["kind"] == b["kind"]:
                continue
            if min(a["end_ms"], b["end_ms"]) - max(a["start_ms"], b["start_ms"]) > 1000:
                conflicts.add(a["kind"])
                conflicts.add(b["kind"])
    ready = [
        {"segment_type": r["kind"], "start_ms": r["start_ms"],
         "end_ms": r["end_ms"], "source": r["source"], "trusted": True,
         "auto_seek": False}
        for r in accepted if r["kind"] not in conflicts
    ]
    return ready, sorted(conflicts)


def _key(ep):
    # Known-cut duration prevents blindly reusing timestamp sets for other edits.
    return json.dumps([ep.imdb_id, ep.tvdb_id, ep.tmdb_id, ep.mapping, ep.season,
                       ep.episode, ep.duration_ms], separators=(",", ":"))


def resolve_external(ep: Episode, cache: Path, *, fetch=_get_json, now=None,
                     offline=False):
    """Cache by metadata identity, shared by playlists, with 6h freshness.

    Never stores customer credentials, device identifiers or provider URLs.
    """
    now = int(time.time()) if now is None else int(now)
    if not ep.imdb_id and not ep.tvdb_id and not ep.tmdb_id:
        return {"trusted_segments": [], "conflicts": [],
                "sources": {"introdb": "missing_imdb_id",
                            "theintrodb": "missing_external_id"},
                "cached": False}
    cache = _cache_path(cache)
    with sqlite3.connect(cache, timeout=5) as db:
        with db:
            db.executescript(SCHEMA)
        k = _key(ep)
        row = db.execute(
            "SELECT response, expires_at FROM trusted_external_cache WHERE identity=?",
            (k,)).fetchone()
        if row and (row[1] > now or offline):
            value = json.loads(row[0])
            return dict(value, cached=True, stale=row[1] <= now)
        if offline:
            return {"trusted_segments": [], "conflicts": [],
                    "sources": {"offline": "not_cached"}, "cached": False}
        rows, sources, absent = _get_candidates(ep, fetch)
        ready, conflicts = _promote(rows, absent)
        output = {"trusted_segments": ready, "conflicts": conflicts,
                  "sources": sources, "cached": False}
        failed = any(s in ("network_error", "http_error", "rate_limited",
                           "invalid_response", "oversize")
                     for s in sources.values())
        if failed and row:
            # Keep previously trusted markers; mark stale on lost connectivity.
            previous = json.loads(row[0])
            return dict(previous, cached=True, stale=True,
                        source_refresh_failed=True)
        ttl = 900 if failed else 21600
        with db:
            db.execute("INSERT INTO trusted_external_cache VALUES(?,?,?,?) "
                       "ON CONFLICT(identity) DO UPDATE SET expires_at=excluded.expires_at,"
                       "created_at=excluded.created_at,response=excluded.response",
                       (k, now+ttl, now, json.dumps(output, separators=(",", ":"))))
        return output


def trusted_playback_resolution(request: dict, *,
                                authorize, trusted_identity,
                                store: Path, cache: Path,
                                fetch=_get_json, offline=False):
    """Authenticated backend integration facade; no public endpoint registered.

    Backend's *trusted_identity* callback MUST resolve the real provider
    episode for the authenticated device; never use client-supplied IMDb/TVDB.
    This function can be called only after existing session authorization.
    """
    if not callable(authorize) or not callable(trusted_identity):
        raise TypeError("Trusted server callbacks are required")
    pid, asset = int(request["playlist_id"]), str(request["asset_key"])
    if authorize(pid, asset) is not True:
        raise PermissionError("Device not permitted to play this media")
    canonical = trusted_identity(pid, asset)
    if not isinstance(canonical, dict):
        raise ValueError("No server-verified episode metadata")
    ep = Episode.from_dict(dict(canonical, playlist_id=pid, asset_key=asset))
    local = playback_resolution(ep.__dict__, authorize=authorize, store=store)
    external = resolve_external(ep, cache, fetch=fetch, offline=offline)
    occupied = {m["type"] for m in local["markers"]}
    merged = [{
        "segment_type": m["type"], "start_ms": m["start_ms"],
        "end_ms": m["end_ms"], "source": m["source"], "trusted": True,
        "auto_seek": False
    } for m in local["markers"]]
    for marker in external["trusted_segments"]:
        if marker["segment_type"] in occupied:
            continue
        if marker["segment_type"] in local["conflicts"]:
            continue
        if any(min(marker["end_ms"], other["end_ms"]) -
               max(marker["start_ms"], other["start_ms"]) > 1000
               for other in merged):
            continue
        merged.append(marker)
    return {
        "asset_key": asset, "segments": sorted(
            merged, key=lambda m: (m["start_ms"], m["end_ms"])),
        "trusted_external_sources": external["sources"],
        "external_conflicts": external["conflicts"],
        "external_cache_hit": external["cached"],
        "playback_contract": "existing_skip_lookup_v1_compatible_segments",
        "automatic_skip_disabled": True,
        "authorization_was_checked": True,
    }
