"""Balanced read-only episode metadata catalog for BOTH analysis playlists.

A single legacy cursor ordered by playlist_id can work through all entries
of 4K ANALYSE (8) before ever reaching THE BEST (10). This catalog maintains
independent per-playlist cursors and alternates odd-slot priority.

No IPTV streams, customer inventory, title-matching, or production writes.
Only the separate root-protected trusted source cache stores cursor progress.
"""
from __future__ import annotations

from collections import Counter
import sqlite3
from pathlib import Path

from analysis_identity import (
    _asset_identity, _columns, _selection_sql, _source_list,
    BASE_REQUIRED,
)
from runtime_integration import _cache_path

PLAYLISTS=(8,10)
STATE = """
CREATE TABLE IF NOT EXISTS trusted_source_balanced_cursor(
 playlist_id INTEGER PRIMARY KEY CHECK(playlist_id IN (8,10)),
 asset_key TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trusted_source_balanced_turn(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 next_playlist_id INTEGER NOT NULL CHECK(next_playlist_id IN (8,10)));
"""
MAX_LIMIT=100


def _ordered_keys(db, where, playlist_id, last, amount, already):
    """Return at most amount unseen keys, wrapping within this playlist only."""
    if amount <= 0:
        return []
    result=[]
    seen=set(already)
    # A scan after last and then prefix scan never transfers provider lanes.
    for condition, values in (
        (" AND asset_key>?",(last,)) if last else ("",()),
        (" AND asset_key<=?",(last,)) if last else ("",()),
    ):
        if len(result) >= amount:
            break
        sql=("SELECT playlist_id,asset_key FROM ("+where+") "
             "WHERE playlist_id=?"+condition+
             " ORDER BY asset_key LIMIT ?")
        # At most 2 * the entire bounded batch, never an unbounded read.
        rows=db.execute(sql,(playlist_id,*values,
                             amount+len(seen))).fetchall()
        for row in rows:
            key=row["asset_key"]
            if key not in seen:
                seen.add(key)
                result.append(row)
                if len(result) >= amount:
                    break
    return result


def catalog_batch(prod, cache, limit=40):
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise ValueError("limit must be 1 to 100")
    p=Path(prod)
    empty={"candidates":0,"conflicts":0,"last_by_playlist":{},
           "next_playlist_id":8,"per_playlist_candidates":{}}
    if p.is_symlink() or not p.is_file():
        return [],"production_db_unavailable",empty
    with sqlite3.connect(p.resolve().as_uri()+"?mode=ro",uri=True,timeout=6) as db:
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        columns=_columns(db,"skip_assets")
        if not BASE_REQUIRED <= columns:
            return [],"missing_episode_columns",empty
        sources=_source_list(db,columns)
        if not sources:
            return [],"missing_canonical_external_ids",empty
        where=_selection_sql(sources)
        with sqlite3.connect(_cache_path(cache),timeout=6) as private:
            private.executescript(STATE)
            current={int(pid):key for pid,key in private.execute(
                "SELECT playlist_id,asset_key FROM trusted_source_balanced_cursor")}
            turn=private.execute(
                "SELECT next_playlist_id FROM trusted_source_balanced_turn WHERE singleton=1"
            ).fetchone()
            next_id=int(turn[0]) if turn is not None and turn[0] in PLAYLISTS else 8
            # Preserve existing scan progress for its prior playlist. The
            # other playlist always gets its own first scan immediately.
            if not current:
                legacy=private.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='trusted_source_sync_cursor'").fetchone()
                if legacy:
                    prev=private.execute(
                        "SELECT playlist_id,asset_key FROM trusted_source_sync_cursor "
                        "WHERE singleton=1").fetchone()
                    if prev and prev[0] in PLAYLISTS:
                        current[int(prev[0])]=prev[1]
                        next_id=10 if int(prev[0])==8 else 8
        order=(next_id, 10 if next_id==8 else 8)
        per={8:limit//2,10:limit//2}
        if limit%2:
            per[order[0]]+=1
        selected=[]
        seen={8:set(),10:set()}
        for pid in order:
            chunk=_ordered_keys(db,where,pid,current.get(pid,""),
                                per[pid],seen[pid])
            selected.extend(chunk)
            seen[pid].update(row["asset_key"] for row in chunk)
        # If one playlist has few/no metadata-linked entries, use the
        # remaining budget on the other without permitting duplicates.
        remaining=limit-len(selected)
        for pid in order:
            if remaining==0:
                break
            prior=selected[-1]["asset_key"] if selected and selected[-1]["playlist_id"]==pid else current.get(pid,"")
            chunk=_ordered_keys(db,where,pid,prior,remaining,seen[pid])
            selected.extend(chunk)
            seen[pid].update(row["asset_key"] for row in chunk)
            remaining=limit-len(selected)
        output=[]
        conflicts=0
        last={}
        counts=Counter()
        for key in selected:
            pid,asset_key=key["playlist_id"],key["asset_key"]
            counts[pid]+=1
            last[pid]=asset_key
            assets=db.execute(
                "SELECT * FROM skip_assets WHERE playlist_id=? AND asset_key=? LIMIT 2",
                (pid,asset_key)).fetchall()
            if len(assets)!=1:
                conflicts+=1
                continue
            item,reason=_asset_identity(db,assets[0],sources)
            if reason!="ok" or item is None:
                conflicts+=1
                continue
            output.append(item)
        meta={"candidates":len(selected),"conflicts":conflicts,
              "last_by_playlist":last,
              "next_playlist_id":order[1],
              "per_playlist_candidates":{str(p):counts[p] for p in PLAYLISTS}}
        return output, ("ok" if selected else "no_episodes_with_identifiers"),meta
