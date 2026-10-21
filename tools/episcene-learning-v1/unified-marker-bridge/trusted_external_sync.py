#!/usr/bin/env python3
"""Metadata-only trusted IntroDB / TheIntroDB prefetch.

Indexes canonical IDs already held in the original EpiScene identity tables.
No IPTV requests, customer playlist scans or source database writes.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from analysis_identity import catalog_batch as identity_catalog_batch, STATE
from bridge import Episode
from runtime_integration import _cache_path
from trusted_external import resolve_external

PRODUCTION = Path("/var/lib/epimediahub/provisioning.db")
CACHE = Path("/var/lib/episcene-learning/trusted-sources.sqlite3")


def catalog_batch(prod, cache, limit=40):
    """Backwards-compatible two-value helper for existing integrations."""
    rows, status, _ = identity_catalog_batch(prod, cache, limit)
    return rows, status


def sync(prod=PRODUCTION, cache=CACHE, *, limit=40, fetch=None):
    rows, status, meta = identity_catalog_batch(prod, cache, limit)
    result = {
        "status": status, "analysed": 0, "trusted_segments": 0,
        "conflicting_segment_types": 0,
        "identity_candidates_checked": meta["candidates"],
        "identity_conflicts_skipped": meta["conflicts"],
        "no_customer_playlists_scanned": True,
        "no_ip_streams_opened": True,
        "production_database_written": False,
    }
    if status != "ok":
        return result
    for row in rows:
        try:
            episode = Episode.from_dict(row)
            resolved = (resolve_external(episode, cache, fetch=fetch)
                        if fetch is not None else resolve_external(episode, cache))
            result["analysed"] += 1
            result["trusted_segments"] += len(resolved["trusted_segments"])
            result["conflicting_segment_types"] += len(resolved["conflicts"])
        except (ValueError, TypeError, sqlite3.Error, OSError):
            result["invalid_metadata_rows"] = result.get("invalid_metadata_rows", 0)+1

    # Update cursor only after the entire chunk. Crashes reprocess a chunk
    # harmlessly via cache. Also advance when records have conflicting IDs.
    last = meta.get("last")
    if last is not None:
        with sqlite3.connect(_cache_path(cache), timeout=6) as db:
            db.executescript(STATE)
            with db:
                db.execute(
                    "INSERT INTO trusted_source_sync_cursor VALUES(1,?,?) "
                    "ON CONFLICT(singleton) DO UPDATE SET "
                    "playlist_id=excluded.playlist_id,asset_key=excluded.asset_key",
                    (last["playlist_id"], last["asset_key"]))
    return result


def main():
    parser = argparse.ArgumentParser(description="EpiScene trusted source metadata prefetch")
    parser.add_argument("--catalog", default=str(PRODUCTION))
    parser.add_argument("--cache", default=str(CACHE))
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()
    print(json.dumps(sync(args.catalog, args.cache, limit=args.limit),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
