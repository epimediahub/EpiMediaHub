#!/usr/bin/env python3
"""Metadata-only trusted IntroDB / TheIntroDB prefetch.

Indexes canonical IDs already held in the original EpiScene identity tables.
No IPTV requests, customer playlist scans or source database writes.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

from analysis_identity_balanced import catalog_batch as identity_catalog_batch, STATE
from bridge import Episode
from catalogue_sources import CatalogueSources, INTRODB_ATTRIBUTION
from runtime_integration import _cache_path
from trusted_external import resolve_external

PRODUCTION = Path("/var/lib/epimediahub/provisioning.db")
CACHE = Path("/var/lib/episcene-learning/trusted-sources.sqlite3")
CATALOGUE_CACHE_TTL = 7 * 86400
DEFAULT_BATCHES = 12
DEFAULT_SECONDS = 220


def catalog_batch(prod, cache, limit=40):
    """Backwards-compatible two-value helper for existing integrations."""
    rows, status, _ = identity_catalog_batch(prod, cache, limit)
    return rows, status


def sync(prod=PRODUCTION, cache=CACHE, *, limit=40, fetch=None,
         cache_ttl=21600, deadline=None, seen=None):
    rows, status, meta = identity_catalog_batch(prod, cache, limit)
    result = {
        "status": status, "analysed": 0, "trusted_segments": 0,
        "conflicting_segment_types": 0,
        "invalid_metadata_rows": 0,
        "markers_by_source": {"introdb": 0, "theintrodb": 0},
        "analysis_playlist_candidates": meta.get("per_playlist_candidates", {}),
        "identity_candidates_checked": meta["candidates"],
        "identity_conflicts_skipped": meta["conflicts"],
        "no_customer_playlists_scanned": True,
        "no_ip_streams_opened": True,
        "production_database_written": False,
    }
    if status != "ok":
        return result
    for row in rows:
        key = (row["playlist_id"], row["asset_key"])
        if seen is not None and key in seen:
            continue
        if deadline is not None and time.monotonic() >= deadline:
            result["status"] = "time_budget_reached"
            return result
        try:
            episode = Episode.from_dict(row)
            options = {"cache_ttl": cache_ttl}
            if fetch is not None:
                options["fetch"] = fetch
            resolved = resolve_external(episode, cache, **options)
            result["analysed"] += 1
            for marker in resolved["trusted_segments"]:
                result["trusted_segments"] += 1
                result["markers_by_source"][marker["source"]] += 1
            result["conflicting_segment_types"] += len(resolved["conflicts"])
        except (ValueError, TypeError, KeyError, sqlite3.Error, OSError):
            result["invalid_metadata_rows"] += 1
        if getattr(fetch, "rate_limited", False):
            result["status"] = "theintrodb_paused"
            return result
        if seen is not None:
            seen.add(key)

    # Persist independent playlist cursors only after the bounded batch.
    # On crash, cache hits may be replayed, but no episode can be skipped.
    last_by_playlist = meta.get("last_by_playlist") or {}
    if last_by_playlist:
        with closing(sqlite3.connect(_cache_path(cache), timeout=6)) as db:
            db.executescript(STATE)
            with db:
                db.executemany(
                    "INSERT INTO trusted_source_balanced_cursor VALUES(?,?) "
                    "ON CONFLICT(playlist_id) DO UPDATE SET asset_key=excluded.asset_key",
                    [(int(pid), key) for pid,key in last_by_playlist.items()])
                db.execute(
                    "INSERT INTO trusted_source_balanced_turn VALUES(1,?) "
                    "ON CONFLICT(singleton) DO UPDATE SET "
                    "next_playlist_id=excluded.next_playlist_id",
                    (meta["next_playlist_id"],))
    return result


def scan_catalogue(prod=PRODUCTION, cache=CACHE, *, limit=40,
                   batches=DEFAULT_BATCHES, seconds=DEFAULT_SECONDS, transport=None):
    """Continue the existing playlist cursors within one service run."""
    if batches < 1 or seconds <= 0:
        raise ValueError("batches and seconds must be positive")
    deadline = time.monotonic() + seconds
    if transport is None:
        transport = CatalogueSources(cache)
    totals, sources, playlists = Counter(), Counter(), Counter()
    seen = set()
    for batch in range(1, batches + 1):
        result = sync(prod, cache, limit=limit, fetch=transport,
                      cache_ttl=CATALOGUE_CACHE_TTL, deadline=deadline, seen=seen)
        totals.update({k: v for k, v in result.items() if type(v) is int})
        sources.update(result["markers_by_source"])
        playlists.update(result["analysis_playlist_candidates"])
        if result["status"] != "ok":
            break
    return dict(result, **totals, batches=batch, introdb_attribution=INTRODB_ATTRIBUTION,
                markers_by_source=dict(sources),
                analysis_playlist_candidates=dict(playlists))


def main():
    parser = argparse.ArgumentParser(description="EpiScene trusted source metadata prefetch")
    parser.add_argument("--catalog", default=str(PRODUCTION))
    parser.add_argument("--cache", default=str(CACHE))
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--batches", type=int, default=DEFAULT_BATCHES)
    parser.add_argument("--seconds", type=int, default=DEFAULT_SECONDS)
    args = parser.parse_args()
    print(json.dumps(scan_catalogue(args.catalog, args.cache, limit=args.limit,
                                    batches=args.batches, seconds=args.seconds),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
