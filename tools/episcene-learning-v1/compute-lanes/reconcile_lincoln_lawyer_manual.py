#!/usr/bin/env python3
"""Private, read-only EpiScene episode/marker reconciliation.

Counts only. Does not output series titles, stream URLs, provider tokens,
customer/device IDs, playlist IDs, media asset keys or raw marker times.
No DB writes, downloads, worker restarts, or unverified approvals.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from pathlib import Path
import json
import sqlite3

DB = Path("/var/lib/epimediahub/provisioning.db")
TABLES = {
    "skip_records": {"asset_key","source","status","media_type","season","episode",
                     "title","segment_type","device_id","customer_id","duration_ms",
                     "source_key"},
    "skip_assets": {"asset_key","playlist_id","season","episode","title","duration_ms","source_key"},
    "devices": {"id","customer_id","enabled"},
    "customers": {"id","enabled"},
    "customer_playlists": {"id","customer_id"}
}
VALID_STATUSES = {"pending","approved","rejected","superseded"}
VALID_KINDS = {"intro","recap","outro"}
SERIES = "the lincoln lawyer"


def open_readonly(path=DB):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("SOURCE_UNAVAILABLE")
    con=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=10)
    con.execute("PRAGMA query_only=ON")
    con.row_factory=sqlite3.Row
    return con


def check_schema(con):
    for table, required in TABLES.items():
        cols={r["name"] for r in con.execute("PRAGMA table_info("+table+")")}
        if not required <= cols:
            raise ValueError("SOURCE_SCHEMA_UNEXPECTED")


def loc(row):
    if row["playlist_id"] in (8,10):
        return "analysis"
    if row["playlist_id"] is None:
        return "unregistered_asset"
    return "other_registered"


def status(value):
    return value if value in VALID_STATUSES else "other"


def kind(value):
    return value if value in VALID_KINDS else "other"


def analyze(con):
    check_schema(con)
    con.execute("BEGIN")
    # Controlled series exact plus "Lincoln ... Lawyer" name variants.
    # Selection uses the marker's submitted series title (not a possibly
    # incorrectly mapped asset title); no series names are returned.
    rows=con.execute("""
       SELECT r.status,r.season,r.episode,r.segment_type,r.duration_ms,
              r.customer_id,r.source_key, a.playlist_id,a.duration_ms AS a_duration,
              a.source_key AS a_source,a.season AS a_season,a.episode AS a_episode,
              d.customer_id AS device_owner,d.enabled AS device_enabled,
              c.enabled AS customer_enabled,p.customer_id AS playlist_owner
       FROM skip_records r
       LEFT JOIN skip_assets a ON a.asset_key=r.asset_key
       LEFT JOIN devices d ON d.id=r.device_id
       LEFT JOIN customers c ON c.id=r.customer_id
       LEFT JOIN customer_playlists p ON p.id=a.playlist_id
       WHERE r.source='device' AND r.media_type='episode'
         AND (LOWER(TRIM(r.title))=?
              OR (LOWER(r.title) LIKE '%lincoln%' AND LOWER(r.title) LIKE '%lawyer%'))
    """,(SERIES,)).fetchall()
    all_rows=defaultdict(Counter)
    season4=defaultdict(Counter)
    episodes=defaultdict(lambda:defaultdict(Counter))
    total=0
    for r in rows:
        s=r["season"]
        if type(s) is not int or s < 0 or s > 99:
            continue
        total+=1
        area=loc(r)
        st=status(r["status"])
        label=kind(r["segment_type"])
        all_rows[str(s)][st]+=1
        if s == 4:
            season4[area][st]+=1
            if type(r["episode"]) is int and 1 <= r["episode"] <= 100:
                episode_no=str(r["episode"])
                episodes[episode_no][area][f"{st}_{label}"]+=1
            else:
                episode_no=None
            if st=="pending":
                b=season4[area]
                if r["playlist_id"] is None:
                    b["pending_unregistered_media"]+=1
                else:
                    if r["device_owner"]!=r["customer_id"] or r["device_enabled"]!=1 or r["customer_enabled"]!=1:
                        b["pending_device_authorization_issue"]+=1
                    if r["playlist_owner"]!=r["customer_id"]:
                        b["pending_playlist_owner_mismatch"]+=1
                    if type(r["duration_ms"]) is not int or type(r["a_duration"]) is not int or abs(r["duration_ms"]-r["a_duration"]) > 500:
                        b["pending_runtime_mismatch"]+=1
                    if r["source_key"]!=r["a_source"] or r["season"]!=r["a_season"] or r["episode"]!=r["a_episode"]:
                        b["pending_episode_source_mismatch"]+=1
    return {
        "mode": "EPISCENE_VERIFIED_CUSTOMER_SERIES_RECONCILIATION",
        "matching_title_records": total,
        "by_season_status": {k:dict(v) for k,v in sorted(all_rows.items(),key=lambda x:int(x[0]))},
        "season4_by_location": {k:dict(v) for k,v in season4.items()},
        "season4_episodes": {
            n:{scope:dict(counts) for scope,counts in scopes.items()}
            for n,scopes in sorted(episodes.items(),key=lambda x:int(x[0]))},
        "limitations": (
          "Searches recorded device marks whose submitted title contains "
          "both Lincoln and Lawyer; differently localized titles not counted. "
          "Already removed records not counted. This does not validate provider streams."
        ),
        "no_customer_or_provider_identifiers_exported": True,
        "database_writes":0,
        "workers_restarted":0,
        "provider_requests":0,
    }


def main():
    try:
        with open_readonly() as con:
            result=analyze(con)
        print(json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False))
    except (ValueError,sqlite3.Error,OSError):
        print(json.dumps({"status":"STOP_READ_ONLY","reason":"DATABASE_SCHEMA_OR_ACCESS",
                          "database_writes":0}))
        raise SystemExit(2)


if __name__=="__main__":
    main()
