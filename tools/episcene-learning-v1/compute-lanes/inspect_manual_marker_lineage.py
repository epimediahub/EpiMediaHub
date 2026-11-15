#!/usr/bin/env python3
"""Read-only diagnosis of EpiScene's pending customer-playlist marker provenance.

Groups each still-pending app-submitted mark by what can actually be verified
using existing database ownership links and episode identity. Reports counts
ONLY. Does not import server modules, use provider credentials, modify rows,
or recommend automatic approval of historical unverified submissions.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sqlite3

DB = Path("/var/lib/epimediahub/provisioning.db")
EXPECTED = {
    "skip_records": ("id","asset_key","device_id","customer_id","source_key",
                     "media_type","season","episode","title","duration_ms",
                     "segment_type","source","status"),
    "skip_assets": ("asset_key","playlist_id","source_key","media_type","season",
                    "episode","title","duration_ms"),
    "devices": ("id","customer_id","enabled"),
    "customers": ("id","enabled"),
    "customer_playlists": ("id","customer_id"),
}
KINDS = frozenset(("intro","recap","outro"))
ANALYSIS_IDS = (8,10)


def read_only(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError("DATABASE_NOT_AVAILABLE")
    connection=sqlite3.connect(p.resolve().as_uri()+"?mode=ro",uri=True,timeout=10)
    connection.row_factory=sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    return connection


def require_columns(db):
    for table, names in EXPECTED.items():
        existing={r[1] for r in db.execute("PRAGMA table_info("+table+")")}
        if not set(names).issubset(existing):
            raise ValueError("EXPECTED_SCHEMA_UNAVAILABLE")


def audit(db, *, series=None):
    require_columns(db)
    # Filter on the server: do not return episode titles, playlist or customer IDs.
    matches= "AND r.title = ? COLLATE NOCASE" if series else ""
    params=(series,) if series else ()
    rows=db.execute("""
      SELECT r.asset_key,r.device_id,r.customer_id,r.source_key,
             r.media_type,r.season,r.episode,r.title,r.duration_ms,r.segment_type,
             a.playlist_id,a.source_key a_source,a.media_type a_type,
             a.season a_season,a.episode a_episode,a.title a_title,
             a.duration_ms a_duration,
             d.id d_exists,d.customer_id d_owner,d.enabled d_enabled,
             c.id c_exists,c.enabled c_enabled,
             p.id p_exists,p.customer_id p_owner
      FROM skip_records r
      LEFT JOIN skip_assets a ON a.asset_key=r.asset_key
      LEFT JOIN devices d ON d.id=r.device_id
      LEFT JOIN customers c ON c.id=r.customer_id
      LEFT JOIN customer_playlists p ON p.id=a.playlist_id
      WHERE r.source='device' AND r.status='pending'
    """+matches,params).fetchall()

    by=defaultdict(Counter)
    kinds=defaultdict(Counter)
    for r in rows:
        area=("analysis" if r["playlist_id"] in ANALYSIS_IDS else
              "other_registered" if r["playlist_id"] is not None else
              "unregistered_asset")
        count=by[area]
        count["total"]+=1
        if r["playlist_id"] is None:
            count["no_registered_asset"]+=1
        else:
            if r["p_exists"] is None:
                count["no_customer_playlist_row"]+=1
            if r["a_source"]!=r["source_key"]:
                count["source_key_mismatch"]+=1
            if r["a_type"]!=r["media_type"]:
                count["media_type_mismatch"]+=1
            if r["a_season"]!=r["season"] or r["a_episode"]!=r["episode"]:
                count["episode_identity_mismatch"]+=1
            if not(isinstance(r["title"],str) and isinstance(r["a_title"],str)
                   and r["title"].strip().casefold()==r["a_title"].strip().casefold()):
                count["title_mismatch"]+=1
            if not (type(r["duration_ms"]) is int and type(r["a_duration"]) is int
                    and abs(r["duration_ms"]-r["a_duration"])<=500):
                count["runtime_mismatch"]+=1
        if r["d_exists"] is None:
            count["missing_device"]+=1
        elif r["d_enabled"]!=1:
            count["disabled_device"]+=1
        if r["c_exists"] is None:
            count["missing_customer"]+=1
        elif r["c_enabled"]!=1:
            count["disabled_customer"]+=1
        if r["customer_id"] is None:
            count["no_record_customer"]+=1
        if r["d_exists"] is not None and r["d_owner"]!=r["customer_id"]:
            count["device_owner_disagrees_with_record"]+=1
        if r["p_exists"] is not None and r["p_owner"]!=r["customer_id"]:
            count["playlist_owner_disagrees_with_record"]+=1
        if r["d_exists"] is not None and r["p_exists"] is not None:
            if r["d_owner"]==r["p_owner"]:
                count["device_owner_matches_playlist_owner"]+=1
            else:
                count["device_owner_disagrees_with_playlist_owner"]+=1
        if (r["d_exists"] is not None and r["p_exists"] is not None
            and r["c_exists"] is not None and r["d_enabled"]==1
            and r["c_enabled"]==1
            and r["d_owner"]==r["p_owner"]==r["customer_id"]):
            count["current_ownership_fully_matches"]+=1
        if r["segment_type"] in KINDS:
            kinds[area][r["segment_type"]]+=1
        else:
            kinds[area]["other"]+=1

    return {
        "mode":"READ_ONLY_MANUAL_MARKER_LINEAGE",
        "scope":"specific_series" if series else "all_pending_manual_marks",
        "pending_count":len(rows),
        "by_asset_registration":{k:dict(v) for k,v in by.items()},
        "segment_types":{k:dict(v) for k,v in kinds.items()},
        "overlapping_reason_counts":True,
        "inference":"A mismatch is a safety block, not proof that a marker is malicious",
        "customer_identifiers_exported":False,
        "episode_titles_exported":False,
        "provider_requests":0,"database_writes":0,"worker_restarts":0,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--db",type=Path,default=DB)
    parser.add_argument("--series",choices=("The Lincoln Lawyer",),default=None)
    args=parser.parse_args()
    try:
        with read_only(args.db) as db:
            output=audit(db,series=args.series)
        print(json.dumps(output,sort_keys=True,ensure_ascii=False,indent=2))
    except (ValueError,sqlite3.Error,OSError):
        print(json.dumps({"status":"READ_ONLY_STOP","reason":"SCHEMA_OR_DB_UNAVAILABLE",
                          "database_writes":0}))
        raise SystemExit(2)


if __name__=="__main__":
    main()
