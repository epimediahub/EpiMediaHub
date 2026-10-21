#!/usr/bin/env python3
"""Scheduled trusted IntroDB / TheIntroDB prefetch for two EpiScene analysis sources.

Requires canonical IMDb/TVDB metadata already present in local skip_assets.
This intentionally does not attempt to infer external IDs from series names or
open IPTV streams. All production DB reads use SQLite mode=ro.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from bridge import Episode
from trusted_external import resolve_external, SCHEMA
from runtime_integration import _cache_path

PRODUCTION = Path("/var/lib/epimediahub/provisioning.db")
CACHE = Path("/var/lib/episcene-learning/trusted-sources.sqlite3")
STATE = """
CREATE TABLE IF NOT EXISTS trusted_source_sync_cursor(
 singleton INTEGER PRIMARY KEY CHECK (singleton=1),
 playlist_id INTEGER NOT NULL, asset_key TEXT NOT NULL);
"""


def catalog_batch(prod, cache, limit=40):
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Limit must be 1–100")
    with sqlite3.connect(Path(prod).resolve().as_uri() + "?mode=ro",
                         uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        cols = {c["name"] for c in db.execute("PRAGMA table_info(skip_assets)")}
        base = {"asset_key","playlist_id","season","episode","duration_ms"}
        id_names = ("imdb_id","tvdb_id")
        if not base <= cols:
            return [], "missing_episode_columns"
        if not any(c in cols for c in id_names):
            return [], "missing_canonical_external_ids"
        with sqlite3.connect(_cache_path(cache), timeout=5) as state:
            state.executescript(STATE)
            last = state.execute("SELECT playlist_id,asset_key FROM trusted_source_sync_cursor "
                                 "WHERE singleton=1").fetchone()
        expr = lambda name: name if name in cols else "NULL AS "+name
        fields = ", ".join(["asset_key","playlist_id","season","episode",
                            "duration_ms",expr("imdb_id"),expr("tvdb_id")])
        clause = ("AND (playlist_id > ? OR (playlist_id=? AND asset_key>?))"
                  if last else "")
        params = (int(last[0]),int(last[0]),last[1],limit) if last else (limit,)
        sql = ("SELECT "+fields+" FROM skip_assets WHERE playlist_id IN (8,10) "
               "AND (imdb_id IS NOT NULL OR tvdb_id IS NOT NULL) "
               if all(c in cols for c in id_names) else
               "SELECT "+fields+" FROM skip_assets WHERE playlist_id IN (8,10) "
               "AND "+ ("imdb_id IS NOT NULL " if "imdb_id" in cols
                         else "tvdb_id IS NOT NULL "))
        sql += clause + " ORDER BY playlist_id,asset_key LIMIT ?"
        rows = db.execute(sql,params).fetchall()
        if not rows and last:
            # Restart the next round after finishing the scanned inventory.
            with sqlite3.connect(_cache_path(cache), timeout=5) as state:
                with state:
                    state.execute("DELETE FROM trusted_source_sync_cursor")
            rows = db.execute(sql.replace(clause,""), (limit,)).fetchall()
        return [dict(r) for r in rows], "ok"


def sync(prod=PRODUCTION, cache=CACHE, *, limit=40, fetch=None):
    rows, status = catalog_batch(prod, cache, limit)
    summary = {"status": status, "analysed": 0, "trusted_segments": 0,
               "conflicting_segment_types": 0,
               "no_customer_playlists_scanned": True,
               "no_ip_streams_opened": True, "production_database_written": False}
    if status != "ok":
        return summary
    for row in rows:
        try:
            item = Episode.from_dict({
                "playlist_id": row["playlist_id"],
                "asset_key": row["asset_key"],
                "season": row["season"], "episode": row["episode"],
                "duration_ms": row["duration_ms"],
                "imdb_id": row["imdb_id"] or "",
                "tvdb_id": row["tvdb_id"] or 0})
            if fetch is not None:
                result = resolve_external(item, cache, fetch=fetch)
            else:
                result = resolve_external(item, cache)
            summary["analysed"] += 1
            summary["trusted_segments"] += len(result["trusted_segments"])
            summary["conflicting_segment_types"] += len(result["conflicts"])
        except (ValueError, TypeError, sqlite3.Error, OSError):
            summary.setdefault("invalid_metadata_rows", 0)
            summary["invalid_metadata_rows"] += 1
        finally:
            with sqlite3.connect(_cache_path(cache), timeout=5) as state:
                state.executescript(STATE)
                with state:
                    state.execute(
                        "INSERT INTO trusted_source_sync_cursor VALUES(1,?,?) "
                        "ON CONFLICT(singleton) DO UPDATE SET "
                        "playlist_id=excluded.playlist_id,asset_key=excluded.asset_key",
                        (row["playlist_id"],row["asset_key"]))
    return summary


def main():
    parser = argparse.ArgumentParser(description="EpiScene external trusted source prefetch")
    parser.add_argument("--catalog", default=str(PRODUCTION))
    parser.add_argument("--cache", default=str(CACHE))
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()
    print(json.dumps(sync(args.catalog,args.cache,limit=args.limit),
                     ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
