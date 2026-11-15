#!/usr/bin/env python3
"""Read-only EpiScene smart-priority suggestions from scoped customer markers.

Authentic, approved device labels from any customer playlist may make queued
episodes on the TWO existing analysis playlists higher-priority. No provider
stream is opened, no customer marker timestamp is copied to another cut, and
no scheduler/worker/queue state is changed. A separate reviewed scheduler
integration and worker-version gate are mandatory for production prioritization.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

PRODUCTION = Path("/var/lib/epimediahub/provisioning.db")
ANALYSIS_IDS = (8, 10)
MAX_PER_PLAYLIST = 2
MAX_FORWARD = 4
TRUSTED_SEGMENTS = ("intro", "recap", "outro")
NEEDED = {
    "skip_customer_marker_provenance": {
        "record_id","customer_id","playlist_id","account_key","asset_key",
        "source_key","media_type","season","episode","duration_ms"},
    "skip_customer_asset_claims": {
        "customer_id","playlist_id","account_key","asset_key","source_key",
        "media_type","season","episode","duration_ms","stream_id","extension"},
    "skip_records": {
        "id","asset_key","source_key","media_type","title","season","episode",
        "duration_ms","segment_type","start_ms","end_ms","disabled","status",
        "source","device_id","customer_id","reviewed_at"},
    "devices":{"id","customer_id","enabled"},
    "customers":{"id","enabled"},
    "customer_playlists":{"id","customer_id"},
    "skip_assets":{"asset_key","playlist_id","title","season","episode","media_type"},
    "skip_jobs":{"id","asset_key","status"},
}


def norm(value):
    return " ".join(str(value or "").casefold().split())


def parsed_date(raw):
    try:
        value=datetime.fromisoformat(raw.replace("Z","+00:00"))
        return value.astimezone(timezone.utc) if value.tzinfo else None
    except (TypeError,ValueError,AttributeError,OverflowError):
        return None


def read_only(path=PRODUCTION):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Database unavailable")
    con=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=8)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("BEGIN")
    return con


def check_tables(con):
    for table,fields in NEEDED.items():
        present={r["name"] for r in con.execute("PRAGMA table_info("+table+")")}
        if not fields<=present:
            raise RuntimeError("Missing required scoped-feedback schema: "+table)


def propose(con, *,now=None,days=14):
    check_tables(con)
    if not 1<=days<=30:
        raise ValueError("unsafe feedback window")
    now=now or datetime.now(timezone.utc)
    cutoff=now-timedelta(days=days)
    verified=con.execute("""
      SELECT r.title,r.season,r.episode,r.segment_type,r.reviewed_at
      FROM skip_customer_marker_provenance cp
      JOIN skip_records r ON r.id=cp.record_id
      JOIN skip_customer_asset_claims a
        ON a.customer_id=cp.customer_id AND a.playlist_id=cp.playlist_id
       AND a.asset_key=cp.asset_key AND a.account_key=cp.account_key
       AND a.source_key=cp.source_key AND a.media_type=cp.media_type
       AND a.season=cp.season AND a.episode=cp.episode
       AND a.duration_ms=cp.duration_ms
      JOIN devices d ON d.id=r.device_id AND d.customer_id=r.customer_id
                    AND d.enabled=1
      JOIN customers c ON c.id=r.customer_id AND c.enabled=1
      JOIN customer_playlists p ON p.id=cp.playlist_id
                               AND p.customer_id=r.customer_id
      WHERE r.status='approved' AND r.source='device' AND r.disabled=0
        AND cp.customer_id=r.customer_id
        AND cp.asset_key=r.asset_key AND cp.source_key=r.source_key
        AND cp.media_type=r.media_type
        AND cp.season=r.season AND cp.episode=r.episode
        AND cp.duration_ms=r.duration_ms
        AND r.media_type='episode'
        AND r.segment_type IN ('intro','recap','outro')
        AND r.start_ms>=0 AND r.end_ms<=r.duration_ms
        AND r.end_ms-r.start_ms>=5000
        AND a.stream_id GLOB '[0-9]*' AND LENGTH(a.stream_id) BETWEEN 1 AND 12
        AND a.extension IN ('mp4','mkv','m4v','avi','ts','mpeg','mpg')
      ORDER BY r.reviewed_at DESC,r.id DESC LIMIT 2000
    """).fetchall()
    by_show=defaultdict(set)
    verified_count=0
    for r in verified:
        reviewed=parsed_date(r["reviewed_at"])
        if reviewed is None or not cutoff<=reviewed<=now+timedelta(minutes=5):
            continue
        if type(r["season"]) is not int or not 1<=r["season"]<=100:
            continue
        if type(r["episode"]) is not int or not 1<=r["episode"]<=10000:
            continue
        title=norm(r["title"])
        if not title or len(title)>180:
            continue
        by_show[(title,r["season"])].add(r["episode"])
        verified_count+=1
    suggestions=[]
    for (title,season),episodes in by_show.items():
        latest=max(episodes)
        for playlist_id in ANALYSIS_IDS:
            for row in con.execute("""
                SELECT j.id,a.episode,a.title
                  FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
                 WHERE j.status='queued' AND a.playlist_id=? AND
                       a.media_type='episode' AND a.season=? AND
                       a.episode>? AND a.episode<=?
                 ORDER BY a.episode,j.id LIMIT 60
            """,(playlist_id,season,latest,latest+MAX_FORWARD)):
                if norm(row["title"])!=title:
                    continue
                suggestions.append({
                    "job_id":int(row["id"]),"playlist_id":playlist_id,
                    "distance":int(row["episode"])-latest,
                    "episode":int(row["episode"])})
    result=[]
    taken={8:0,10:0}
    for candidate in sorted(suggestions,key=lambda c:(c["distance"],c["playlist_id"],c["job_id"])):
        if candidate["playlist_id"] not in taken or taken[candidate["playlist_id"]]>=MAX_PER_PLAYLIST:
            continue
        if candidate["job_id"] in {c["job_id"] for c in result}:
            continue
        result.append(candidate)
        taken[candidate["playlist_id"]]+=1
    return {
        "mode":"READ_ONLY_SCOPED_CUSTOMER_SMART_PRIORITY",
        "eligible_scoped_approved_markers":verified_count,
        "distinct_series_seasons":len(by_show),
        "candidate_jobs":result,
        "provider_connections":0,"queue_mutations":0,"worker_restarts":0,
        "marker_times_transferred_across_cuts":False,
        "production_scheduler_hook_enabled":False,
    }


if __name__=="__main__":
    try:
        with read_only() as db:
            value=propose(db)
        print(json.dumps(value,sort_keys=True,indent=2))
    except (RuntimeError,sqlite3.Error,ValueError):
        print(json.dumps({"status":"READ_ONLY_STOP","provider_connections":0,
                          "queue_mutations":0}))
        raise SystemExit(2)
