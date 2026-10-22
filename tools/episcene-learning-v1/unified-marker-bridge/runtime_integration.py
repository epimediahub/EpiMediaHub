#!/usr/bin/env python3
"""Backend integration contract for EpiScene unified markers.

- Playback: authorization supplied by EXISTING server; verified markers only.
- Analysis: two dedicated playlists, cached external hints, no IPTV streams.
- No untrusted HTTP service or customer marker changes are created here.
"""
from __future__ import annotations

import json
import os
import stat
import sqlite3
import time
from pathlib import Path
from typing import Callable

from bridge import ANALYSIS_PLAYLISTS, Episode, evaluate, find_verified, remote_candidates, windows

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS external_advice_cache (
 cache_key TEXT PRIMARY KEY,
 fetched_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 response_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS external_advice_expiry_idx ON external_advice_cache(expires_at);
"""


def playback_resolution(request: dict, *, authorize: Callable[[int, str], bool], store: Path):
    """Return ONLY confirmed skips to an authorized existing playback endpoint.

    The backend must authorize the *actual account/device* to play asset_key
    from playlist_id before calling this function; never use a request boolean.
    The backend remains responsible for its own session/token/CSRF policy.
    """
    if not callable(authorize):
        raise TypeError("A trusted backend authorization callback is required")
    ep = Episode.from_dict(request)
    if authorize(ep.playlist_id, ep.asset_key) is not True:
        raise PermissionError("Episode not authorized for this playback session")
    result = evaluate(ep, store, external=False)
    # When trusted annotations from two releases overlap, prefer labels made
    # against this exact asset. If the conflicting labels share the same
    # evidence rank, withhold both rather than guessing which scene to skip.
    ready = result["ready_verified"]
    excluded = set()
    overlaps = []
    for i, first in enumerate(ready):
        for j in range(i + 1, len(ready)):
            second = ready[j]
            length = min(first["end_ms"], second["end_ms"]) - max(
                first["start_ms"], second["start_ms"])
            if length <= 1000:
                continue
            first_exact = first["match"] == "same_asset"
            second_exact = second["match"] == "same_asset"
            if first_exact != second_exact:
                excluded.add(j if first_exact else i)
            else:
                excluded.update((i, j))
            overlaps.append((first["kind"], second["kind"]))
    ready = [marker for i, marker in enumerate(ready) if i not in excluded]
    return {
        "asset_key": ep.asset_key,
        "playlist_id": ep.playlist_id,
        "markers": [{"type": marker["kind"], "start_ms": marker["start_ms"],
                     "end_ms": marker["end_ms"], "source": marker["source"],
                     "marker_id": marker["marker_id"]}
                    for marker in ready],
        "conflicts": result["conflicts"] + ["overlap:" + a + ":" + b for a, b in overlaps],
        "schema": "episcene_verified_skip_v1",
        "only_authenticated_verified_markers": True
    }


def _cache_key(ep):
    return json.dumps({
        "playlist": ep.playlist_id, "asset": ep.asset_key,
        "season": ep.season, "episode": ep.episode, "duration": ep.duration_ms,
        "imdb_id": ep.imdb_id, "tvdb_id": ep.tvdb_id, "mapping": ep.mapping
    }, sort_keys=True, separators=(",", ":"))


TRUSTED_SOURCE_CACHE = Path("/var/lib/episcene-learning/trusted-sources.sqlite3")
TRUSTED_SOURCE_READER = "epimediahub"


def _trusted_cache_readonly_acl(p):
    """Permit only the exact Linux POSIX ACL for the API's read-only cache.

    POSIX ACL masks appear in stat() group bits. Do not weaken the general
    0700/0600 advisory-store rule for other paths or unrestricted ACLs.
    """
    import pwd
    import struct

    if p != TRUSTED_SOURCE_CACHE or p.is_symlink() or not p.is_file():
        return False
    try:
        uid = pwd.getpwnam(TRUSTED_SOURCE_READER).pw_uid
        d, f = p.parent.stat(), p.stat()
        if uid in (d.st_uid, f.st_uid):
            return False
        if stat.S_IMODE(d.st_mode) != 0o710 or stat.S_IMODE(f.st_mode) != 0o640:
            return False
        specs = ((p.parent, 0o7, 0o1), (p, 0o6, 0o4))
        for path, owner_perms, reader_perms in specs:
            acl = os.getxattr(path, "system.posix_acl_access")
            if len(acl) != 44 or struct.unpack_from("<I", acl)[0] != 2:
                return False
            entries = [struct.unpack_from("<HHI", acl, i) for i in range(4, len(acl), 8)]
            expected = [
                (1, owner_perms, 0xffffffff),  # owning user
                (2, reader_perms, uid),        # API account only
                (4, 0, 0xffffffff),            # owning group: denied
                (16, reader_perms, 0xffffffff),# effective ACL mask
                (32, 0, 0xffffffff),           # everyone else: denied
            ]
            if entries != expected:
                return False
        return True
    except (KeyError, OSError, ValueError, struct.error):
        return False


def _cache_path(path):
    p = Path(path)
    if p.parent.is_symlink() or not p.parent.is_dir():
        raise ValueError("Cache parent must exist and not be a symlink")
    acl_private = _trusted_cache_readonly_acl(p)
    if stat.S_IMODE(p.parent.stat().st_mode) & 0o077 and not acl_private:
        raise ValueError("Advisory cache directory must be private (0700)")
    if p.is_symlink() or (p.exists() and not p.is_file()):
        raise ValueError("Refusing nonregular/symlink advisory cache")
    if not p.exists():
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
    if (p.is_symlink() or not p.is_file() or
            (stat.S_IMODE(p.stat().st_mode) & 0o077 and not acl_private)):
        raise ValueError("Advisory cache file must be private (0600)")
    return p


def external_review_resolution(request: dict, *, cache: Path, fetch=None,
                               now: int | None = None):
    """Review-only source hints, cached to avoid hammering external APIs.

    Only intended for the independent analysis inventories 8 and 10.
    NEVER produce public playback timestamps and NEVER open a video stream.
    """
    ep = Episode.from_dict(request)
    if ep.playlist_id not in ANALYSIS_PLAYLISTS:
        raise PermissionError("External analysis restricted to analysis playlists")
    now = int(time.time()) if now is None else int(now)
    p = _cache_path(cache)
    with sqlite3.connect(p, timeout=10) as db:
        with db:
            db.executescript(CACHE_SCHEMA)
        key = _cache_key(ep)
        row = db.execute("SELECT response_json,expires_at FROM external_advice_cache "
                         "WHERE cache_key=?", (key,)).fetchone()
        if row and row[1] > now:
            prior = json.loads(row[0])
            prior["cached"] = True
            return prior
        candidates, statuses = remote_candidates(ep, fetch=fetch) if fetch is not None else remote_candidates(ep)
        # Do not mark API timeouts as permanent absence.
        degraded = any(s in ("rate_limited", "network_error", "http_error", "oversize")
                       for s in statuses.values())
        ttl = 900 if degraded else 21600  # 15 min on failures, six hours on success
        output = {
            "playlist_id": ep.playlist_id,
            "asset_key": ep.asset_key,
            "search_windows_ms": windows(ep.duration_ms),
            "review_candidates": [dict(c, status="needs_cut_verification")
                                  for c in candidates],
            "source_status": statuses,
            "published": False,
            "cached": False
        }
        with db:
            db.execute("INSERT INTO external_advice_cache VALUES(?,?,?,?) "
                       "ON CONFLICT(cache_key) DO UPDATE SET "
                       "fetched_at=excluded.fetched_at,expires_at=excluded.expires_at,"
                       "response_json=excluded.response_json",
                       (key, now, now + ttl, json.dumps(output, separators=(",", ":"))))
        return output


def planning_hints(episodes: list[dict], *, max_per_playlist: int = 1):
    """Choose advisory lookup jobs only; does not execute or reserve streams.

    A deliberately bounded candidate list allows scheduling WITHOUT violating
    the one-stream-per-provider budget of either analysis playlist.
    """
    if type(max_per_playlist) is not int or max_per_playlist != 1:
        raise ValueError("Analysis stream budget fixed at one per playlist")
    chosen, counts = [], {8: 0, 10: 0}
    for item in episodes:
        ep = Episode.from_dict(item)
        if ep.playlist_id not in ANALYSIS_PLAYLISTS:
            continue
        if counts[ep.playlist_id] >= 1:
            continue
        chosen.append({"playlist_id": ep.playlist_id,
                       "asset_key": ep.asset_key,
                       "search_windows_ms": windows(ep.duration_ms),
                       "external_lookup_only": True,
                       "stream_slots_reserved": 0})
        counts[ep.playlist_id] += 1
    return chosen
