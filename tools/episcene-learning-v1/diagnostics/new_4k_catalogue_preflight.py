#!/usr/bin/env python3
"""Read-only preflight after replacing the time-limited 4K ANALYSE credentials.

Determines whether episode jobs still point at a previous catalogue generation.
Does not query the IPTV provider, access playlist credentials, change jobs,
approve/release markers, restart workers or print episode/stream identifiers.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import json,sqlite3,time

DB=Path("/var/lib/epimediahub/provisioning.db")
PID=8
STATUSES=("queued","running","failed","done","review","partial",
          "no_match","no_reference","disabled")

def columns(con,table):
    return {r[1] for r in con.execute("PRAGMA table_info("+table+")")}

def exists(con,table):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None

def parsed(value):
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        return float(value)
    if not isinstance(value,str) or not value.strip():
        return None
    try:
        dt=datetime.fromisoformat(value.replace("Z","+00:00"))
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError,OverflowError):
        return None

def count_groups(con,where,params):
    return con.execute("SELECT COUNT(*) FROM ("+where+")",params).fetchone()[0]

def snapshot(con,now):
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    wanted={
      "skip_assets":{"asset_key","playlist_id","updated_at"},
      "skip_jobs":{"asset_key","status","updated_at"},
      "skip_analysis_playlists":{"id","archived"},
      "skip_analysis_sources":{"playlist_id","enabled"}
    }
    if not all(exists(con,t) and c<=columns(con,t) for t,c in wanted.items()):
        raise RuntimeError("STOP_UNKNOWN_PRODUCTION_SCHEMA")
    playlist=con.execute("""SELECT p.archived,s.enabled
        FROM skip_analysis_playlists p
        LEFT JOIN skip_analysis_sources s ON s.playlist_id=p.id
        WHERE p.id=?""",(PID,)).fetchone()
    if playlist is None:
        raise RuntimeError("STOP_ANALYSIS_PLAYLIST_8_MISSING")
    statuses=Counter()
    last_success=None
    failed_latest=None
    last_asset_update=None
    for row in con.execute("""SELECT j.status,COUNT(*) n,MAX(j.updated_at) latest_job
      FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
      WHERE a.playlist_id=? GROUP BY j.status""",(PID,)):
        statuses[row["status"]]=int(row["n"])
        when=parsed(row["latest_job"])
        if when is not None:
            if row["status"] in ("done","review","no_match","no_reference","partial"):
                last_success=max(last_success or 0,when)
            if row["status"]=="failed":failed_latest=max(failed_latest or 0,when)
    row=con.execute("SELECT MAX(updated_at) FROM skip_assets WHERE playlist_id=?",(PID,)).fetchone()
    last_asset_update=parsed(row[0]) if row else None
    out={
      "mode":"NEW_4K_CATALOGUE_PREFLIGHT",
      "playlist_id":PID,
      "analysis_enabled":bool(playlist["enabled"]==1 and playlist["archived"]==0),
      "job_status_totals":{k:statuses[k] for k in STATUSES if statuses[k]},
      "minutes_since_completed_or_review":int((now-last_success)/60) if last_success is not None else None,
      "minutes_since_last_failed":int((now-failed_latest)/60) if failed_latest is not None else None,
      "minutes_since_latest_asset_refresh":int((now-last_asset_update)/60) if last_asset_update is not None else None,
      "catalogue_generation_verification":"NOT_AVAILABLE",
      "safe_to_disable_old_jobs":False,
      "reason":"DO_NOT_DISABLE_UNTIL_NEW_CATALOGUE_PROVEN_COMPLETE"
    }
    if not exists(con,"skip_catalogue_episodes") or not {"asset_key","playlist_id","seen_generation"}<=columns(con,"skip_catalogue_episodes"):
        out["catalogue_generation_verification"]="NO_SUPPORTED_CATALOGUE_MAPPING"
        return out
    generations=con.execute("""SELECT seen_generation,COUNT(*) n FROM
        skip_catalogue_episodes WHERE playlist_id=?
        GROUP BY seen_generation ORDER BY seen_generation DESC LIMIT 8""",(PID,)).fetchall()
    nonempty=[r for r in generations if r["seen_generation"] not in (None,0,"", "0")]
    if not nonempty:
        out["catalogue_generation_verification"]="NO_NONZERO_CATALOGUE_GENERATION"
        return out
    # A generation identifier might be numeric or string; never assume lexical
    # ordering is chronological. A single generation cannot prove a rollover.
    kinds={type(r["seen_generation"]) for r in nonempty}
    if kinds != {int} and kinds != {str}:
        out["catalogue_generation_verification"]="UNSUPPORTED_GENERATION_TYPE"
        return out
    if kinds=={int}:
        latest=max(r["seen_generation"] for r in nonempty)
    else:
        # Opaque string generations have no sound monotonicity guarantee.
        out["catalogue_generation_verification"]="OPAQUE_GENERATION_ORDER"
        out["catalogue_generations_seen"]=len(nonempty)
        return out
    latest_count=next(int(r["n"]) for r in nonempty if r["seen_generation"]==latest)
    other_count=sum(int(r["n"]) for r in nonempty if r["seen_generation"]!=latest)
    out["catalogue_generation_verification"]="OBSERVED_NUMERIC_GENERATIONS_NOT_VERIFIED_COMPLETE"
    out["catalogue_generations_seen"]=len(nonempty)
    out["latest_generation_catalogue_episodes"]=latest_count
    out["previous_generations_catalogue_episodes"]=other_count

    # Aggregate catalogue mapping once. Avoid a nested full scan for every
    # queued episode when this database has no supporting catalogue index.
    rows=con.execute("""WITH mapped AS (
        SELECT asset_key,
          MAX(CASE WHEN seen_generation=? THEN 1 ELSE 0 END) latest,
          MAX(CASE WHEN seen_generation IS NOT NULL THEN 1 ELSE 0 END) known
        FROM skip_catalogue_episodes WHERE playlist_id=?
        GROUP BY asset_key
      )
      SELECT j.status,
        CASE WHEN m.latest=1 THEN 'LATEST'
        WHEN m.known=1 THEN 'OLDER_OR_ZERO'
        ELSE 'UNMAPPED' END AS generation_class,
        COUNT(*) n
      FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
      LEFT JOIN mapped m ON m.asset_key=a.asset_key
      WHERE a.playlist_id=? AND j.status IN ('queued','failed','review','partial')
      GROUP BY j.status,generation_class""",(latest,PID,PID)).fetchall()
    buckets={}
    for row in rows:
        target=buckets.setdefault(row["status"],{})
        target[row["generation_class"]]=int(row["n"])
    out["jobs_by_catalogue_generation"]=buckets
    out["safe_to_disable_old_jobs"]=False
    out["reason"]="GENERATION_COUNT_ALONE_NOT_PROOF_OF_LIVE_ACCOUNT_OR_COMPLETE_RESCAN"
    return out

def main():
    if not DB.is_file() or DB.is_symlink():raise RuntimeError("STOP_SOURCE_DB_MISSING")
    with sqlite3.connect(DB.resolve().as_uri()+"?mode=ro",uri=True,timeout=15) as con:
        print(json.dumps(snapshot(con,time.time()),indent=2,sort_keys=True))
    print("NO_CREDENTIALS_STREAM_URLS_SERIES_TITLES_OR_IDS_EXPORTED")
    print("DATABASE_UNCHANGED; NO_MEDIA_REQUESTS; NO_SERVICES_RESTARTED")

if __name__=="__main__":
    try: main()
    except (sqlite3.Error,OSError,RuntimeError) as exc:
        msg=str(exc)
        print(msg if isinstance(exc,RuntimeError) and msg.startswith("STOP_") else "STOP_READ_ONLY_CHECK")
        raise SystemExit(1)
