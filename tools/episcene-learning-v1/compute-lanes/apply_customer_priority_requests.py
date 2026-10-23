#!/usr/bin/env python3
"""Bounded EpiScene Smart Priority from verified customer markers.

Only schedules jobs that already exist on independently authorized analysis
playlists 8/10. Never copies marker timings, accesses provider streams, alters
analysis jobs, or starts any worker. Strict installed scheduler/worker digest
gate: if versions drift, STOP without writes.

--check = read-only, --apply = insert up to two expiring, non-destructive
priority requests per analysis playlist. Existing reference/user priorities
are NOT replaced. Scheduler already consumes skip_schedule_requests.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

DB=Path("/var/lib/epimediahub/provisioning.db")
SCHEDULER=Path("/opt/epimediahub/provisioning/skip_schedule.py")
WORKER=Path("/opt/epimediahub/provisioning/skip_analysis_worker.py")
EXPECTED_SHA={
 "scheduler":"5dffbcad78c666a74a6d5af668fdd565e6d89f094b2c2ecebee6e561ebc408a4",
 "analysis_worker":"e062daaedce4150114fa5b2b154f82adc2a37e3a1b7a3b50b10f237361fdca26",
}
KINDS=("intro","recap","outro")
TARGETS=(8,10)
MAX_FORWARD=4
PER_PLAYLIST=2
DAYS=14
MAX_FEEDBACK=2000
SCHEMA={
 "skip_customer_marker_provenance":{"record_id","customer_id","playlist_id","account_key","asset_key","source_key","media_type","season","episode","duration_ms"},
 "skip_customer_asset_claims":{"customer_id","playlist_id","account_key","asset_key","source_key","media_type","season","episode","duration_ms","stream_id","extension"},
 "skip_records":{"id","asset_key","source_key","media_type","title","season","episode","duration_ms","segment_type","start_ms","end_ms","disabled","status","source","device_id","customer_id","reviewed_at"},
 "skip_jobs":{"id","asset_key","status","attempts"},
 "skip_assets":{"asset_key","playlist_id","title","season","episode","media_type","source_key"},
 "skip_analysis_sources":{"playlist_id","enabled"},
 "skip_analysis_playlists":{"id","archived"},
 "skip_schedule_requests":{"playlist_id","source_key","season","episode","reference_asset","reason","requested_at","expires_at"},
 "devices":{"id","customer_id","enabled"},
 "customers":{"id","enabled"},
 "customer_playlists":{"id","customer_id"}
}
class Stop(Exception):pass

def versions(paths=None):
    paths=paths or {"scheduler":SCHEDULER,"analysis_worker":WORKER}
    out={}
    for name,path in paths.items():
        if path.is_symlink() or not path.is_file():
            raise Stop("MISSING_OR_UNTRUSTED_WORKER")
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        out[name]="match" if digest==EXPECTED_SHA[name] else "DRIFT"
    if any(x!="match" for x in out.values()):
        raise Stop("WORKER_VERSION_DRIFT")
    return out

def validate_schema(con):
    for table,fields in SCHEMA.items():
        found={r[1] for r in con.execute("PRAGMA table_info("+table+")")}
        if not fields<=found:
            raise Stop("SCHEMA_MISMATCH:"+table)

def normalize(title):
    return " ".join((title or "").casefold().split()) if isinstance(title,str) else ""

def good_date(text,now):
    if not isinstance(text,str):return False
    try:
        dt=datetime.fromisoformat(text.replace("Z","+00:00"))
        return bool(dt.tzinfo and now-timedelta(days=DAYS)<=dt.astimezone(timezone.utc)<=now+timedelta(minutes=5))
    except (ValueError,OverflowError):return False

def plan(con,now=None):
    now=now or datetime.now(timezone.utc)
    validate_schema(con)
    rows=con.execute("""
      SELECT r.id,r.title,r.season,r.episode,r.reviewed_at
        FROM skip_customer_marker_provenance cp
        JOIN skip_records r ON r.id=cp.record_id
        JOIN skip_customer_asset_claims a
          ON a.customer_id=cp.customer_id AND a.playlist_id=cp.playlist_id
         AND a.account_key=cp.account_key AND a.asset_key=cp.asset_key
         AND a.source_key=cp.source_key AND a.media_type=cp.media_type
         AND a.season=cp.season AND a.episode=cp.episode
         AND a.duration_ms=cp.duration_ms
        JOIN devices d ON d.id=r.device_id AND d.customer_id=r.customer_id AND d.enabled=1
        JOIN customers c ON c.id=r.customer_id AND c.enabled=1
        JOIN customer_playlists p ON p.id=cp.playlist_id AND p.customer_id=r.customer_id
       WHERE r.source='device' AND r.status='approved' AND r.disabled=0
         AND cp.customer_id=r.customer_id AND cp.asset_key=r.asset_key
         AND cp.source_key=r.source_key AND cp.media_type=r.media_type
         AND cp.season=r.season AND cp.episode=r.episode
         AND cp.duration_ms=r.duration_ms AND r.media_type='episode'
         AND r.segment_type IN ('intro','recap','outro')
         AND r.start_ms>=0 AND r.end_ms<=r.duration_ms
         AND r.end_ms-r.start_ms>=5000
         AND a.extension IN ('mp4','mkv','m4v','avi','ts','mpeg','mpg')
         AND a.stream_id GLOB '[0-9]*' AND LENGTH(a.stream_id) BETWEEN 1 AND 12
       ORDER BY r.reviewed_at DESC,r.id DESC LIMIT ?
    """,(MAX_FEEDBACK+1,)).fetchall()
    if len(rows)>MAX_FEEDBACK:raise Stop("TOO_MANY_CUSTOMER_LABELS")
    show_season={}
    eligible=0
    for r in rows:
        title=normalize(r["title"])
        if not 1<=len(title)<=180 or type(r["season"]) is not int or not 1<=r["season"]<=100 or type(r["episode"]) is not int or not 1<=r["episode"]<=10000 or not good_date(r["reviewed_at"],now):
            continue
        eligible+=1
        key=(title,r["season"])
        show_season[key]=max(show_season.get(key,0),r["episode"])
    proposals=[]
    for (title,season),latest in show_season.items():
        for playlist in TARGETS:
            candidates=con.execute("""
                SELECT j.id,a.playlist_id,a.source_key,a.title,a.episode
                FROM skip_jobs j
                JOIN skip_assets a ON a.asset_key=j.asset_key
                JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
                JOIN skip_analysis_playlists p ON p.id=a.playlist_id AND p.archived=0
                WHERE a.playlist_id=? AND a.media_type='episode'
                  AND a.season=? AND a.episode>? AND a.episode<=?
                  AND j.status='queued' AND j.attempts<3
                ORDER BY a.episode,j.id LIMIT 60
            """,(playlist,season,latest,latest+MAX_FORWARD)).fetchall()
            for candidate in candidates:
                if normalize(candidate["title"])!=title:
                    continue
                proposals.append({"playlist_id":playlist,"source_key":candidate["source_key"],
                                  "season":season,"episode":candidate["episode"],
                                  "distance":candidate["episode"]-latest,
                                  "job_id":candidate["id"]})
    chosen=[]
    counts=defaultdict(int)
    sources=set()
    for c in sorted(proposals,key=lambda x:(x["distance"],x["playlist_id"],x["job_id"])):
        key=(c["playlist_id"],c["source_key"])
        if key in sources or counts[c["playlist_id"]]>=PER_PLAYLIST:
            continue
        counts[c["playlist_id"]]+=1
        sources.add(key)
        chosen.append(c)
    return chosen,{"verified_recent_customer_labels":eligible,
                   "matching_series_seasons":len(show_season),
                   "priority_requests_proposed":len(chosen),
                   "proposed_by_analysis_playlist":{str(k):counts[k] for k in TARGETS}}

def run(apply=False,database=DB,paths=None,now=None):
    versions_match=versions(paths)
    if database.is_symlink() or not database.is_file():
        raise Stop("PRODUCTION_DATABASE_UNAVAILABLE")
    uri=database.resolve().as_uri()+"?mode=ro"
    with sqlite3.connect(uri,uri=True,timeout=10) as con:
        con.row_factory=sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")
        chosen,detail=plan(con,now)
    result={"mode":"EPISCENE_VERIFIED_CUSTOMER_PRIORITY","check":"PASS",
            "versions":versions_match,**detail,
            "analysis_jobs_modified":0,"provider_connections":0,
            "worker_restarts":0,"marker_times_copied":0}
    if not apply:
        return dict(result,applied=False,changes_made=0)
    if not chosen:
        return dict(result,applied=True,changes_made=0)
    stamp=int((now or datetime.now(timezone.utc)).timestamp())
    inserted=0
    with sqlite3.connect(database,timeout=15,isolation_level=None) as con:
        con.row_factory=sqlite3.Row
        con.execute("PRAGMA busy_timeout=15000")
        con.execute("BEGIN IMMEDIATE")
        try:
            validate_schema(con)
            # Do not modify an active manually selected series/reference.
            for c in chosen:
                still_queued=con.execute("""
                  SELECT 1 FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
                  JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
                  JOIN skip_analysis_playlists p ON p.id=a.playlist_id AND p.archived=0
                  WHERE j.id=? AND j.status='queued' AND j.attempts<3
                  AND a.playlist_id=? AND a.source_key=? AND a.season=? AND a.episode=?
                  LIMIT 1
                """,(c["job_id"],c["playlist_id"],c["source_key"],c["season"],c["episode"])).fetchone()
                if not still_queued:continue
                existing=con.execute("SELECT reason,expires_at FROM skip_schedule_requests WHERE playlist_id=? AND source_key=?",
                                     (c["playlist_id"],c["source_key"])).fetchone()
                if existing and existing["expires_at"]>stamp:continue
                con.execute("""INSERT INTO skip_schedule_requests(
                     playlist_id,source_key,season,episode,reference_asset,
                     reason,requested_at,expires_at)
                   VALUES(?,?,?,?,'','customer_verified',?,?)
                   ON CONFLICT(playlist_id,source_key) DO UPDATE SET
                     season=excluded.season,episode=excluded.episode,
                     reference_asset='',reason='customer_verified',
                     requested_at=excluded.requested_at,
                     expires_at=excluded.expires_at
                   WHERE skip_schedule_requests.expires_at<=?""",
                   (c["playlist_id"],c["source_key"],c["season"],c["episode"],
                    stamp,stamp+7*86400,stamp))
                inserted+=int(con.execute("SELECT changes()").fetchone()[0])
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    return dict(result,applied=True,changes_made=inserted)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check",action="store_true")
    g.add_argument("--apply",action="store_true")
    o=p.parse_args()
    try:
        report=run(apply=o.apply)
        print(json.dumps(report,sort_keys=True,indent=2))
    except (Stop,sqlite3.Error,OSError,ValueError) as ex:
        print(json.dumps({"status":"STOP_NO_NEW_REQUESTS","reason":str(ex) if isinstance(ex,Stop) else "SQLITE_OR_IO","provider_connections":0}))
        sys.exit(2)
