"""Add trusted external markers to an EXISTING, authorized lookup response.

This module deliberately does not define a Flask route, bypass an existing
authorization check or modify first-party records. It must be called INSIDE
the original authenticated /v1/device/skip/lookup handler only after that
handler has successfully built the response for the requested asset.

Only cached IntroDB/TheIntroDB segments are used; no HTTP during playback.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from bridge import Episode
from trusted_external import resolve_external

KINDS = frozenset(("intro", "recap", "outro"))
MAX_SEGMENTS = 8
SOURCES = frozenset(("introdb", "theintrodb"))


def _kind(marker):
    return marker.get("segment_type", marker.get("type"))


def _range(marker, duration):
    try:
        start = marker["start_ms"]
        end = marker["end_ms"]
    except (KeyError, TypeError):
        return None
    if type(start) is not int or type(end) is not int:
        return None
    if not (0 <= start < end <= duration):
        return None
    return start, end


def append_trusted_to_existing_lookup(
    existing: dict,
    *,
    playlist_id: int,
    asset_key: str,
    authorized: Callable[[int, str], bool],
    canonical_episode: Callable[[int, str], dict | None],
    cache: Path = Path("/var/lib/episcene-learning/trusted-sources.sqlite3"),
):
    """Return original response or append validated skip segments.

    authorized and canonical_episode MUST be existing trusted server-side
    callbacks (never parameters received from an app/device). In particular:
    - Caller must first run the existing device authentication;
    - authorized must check that this same authenticated device may play
      the identified playlist and asset;
    - canonical_episode must independently map real series IDs, season,
      episode, cut duration and ordering. Title-only matches are not enough.

    existing is the success JSON dictionary produced by the original
    endpoint, not a tuple/Flask Response/error object. The function does
    not alter it in place, and on error returns it unchanged.
    """
    if not isinstance(existing, dict) or not callable(authorized) or not callable(canonical_episode):
        return existing
    items = existing.get("segments")
    if not isinstance(items, list) or len(items) > MAX_SEGMENTS:
        return existing
    if existing.get("error") or existing.get("success") is False:
        return existing
    if not isinstance(playlist_id, int) or not isinstance(asset_key, str) or not asset_key:
        return existing
    try:
        if authorized(playlist_id, asset_key) is not True:
            return existing
        identity = canonical_episode(playlist_id, asset_key)
        if not isinstance(identity, dict):
            return existing
        # No client-supplied imdb_id, tmdb_id or duration is trusted.
        ep = Episode.from_dict(dict(identity, playlist_id=playlist_id, asset_key=asset_key))
        if ep.playlist_id != playlist_id or ep.asset_key != asset_key:
            return existing
        if not (ep.imdb_id or ep.tvdb_id or ep.tmdb_id):
            return existing
        resolved = resolve_external(ep, cache, offline=True)
        if resolved.get("stale"):
            return existing
        candidates = resolved.get("trusted_segments")
        if not isinstance(candidates, list):
            return existing
        # Only merge when all existing marker shapes are understood.
        for marker in items:
            if not isinstance(marker, dict):
                return existing
            if _kind(marker) not in KINDS or _range(marker, ep.duration_ms) is None:
                return existing
        updated = list(items)
        occupied = {_kind(marker) for marker in updated}
        conflicts = set(resolved.get("conflicts") or [])
        for entry in candidates:
            if not isinstance(entry, dict):
                continue
            kind = _kind(entry)
            interval = _range(entry, ep.duration_ms)
            if (kind not in KINDS or kind in occupied or kind in conflicts
                    or interval is None or entry.get("source") not in SOURCES
                    or entry.get("trusted") is not True):
                continue
            if any((min(interval[1], old["end_ms"]) -
                    max(interval[0], old["start_ms"]) > 1000) for old in updated):
                continue
            if len(updated) >= MAX_SEGMENTS:
                break
            updated.append({
                "segment_type": kind, "start_ms": interval[0],
                "end_ms": interval[1], "source": entry["source"],
                "trusted": True, "auto_seek": False,
            })
            occupied.add(kind)
        if len(updated) == len(items):
            return existing
        return dict(existing, segments=sorted(updated,
                    key=lambda x: (x["start_ms"], x["end_ms"])))
    except (ValueError, TypeError, KeyError, PermissionError, OSError):
        return existing
