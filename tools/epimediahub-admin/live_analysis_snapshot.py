#!/usr/bin/env python3
"""Read-only, fail-closed EpiScene progress adapter for the Admin alert daemon.

Only analysis lane IDs 8 and 10 and numeric job statistics leave the source
DB. No config_json, provider URLs, titles, source keys, log lines, secrets,
tokens, device identity, customer information or IPTV credentials are emitted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, time as clock, timezone
from zoneinfo import ZoneInfo
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import time

DEFAULT=Path("/var/lib/epimediahub/provisioning.db")
FINISHED=("done","review","no_match","partial","no_reference")


def epoch(value):
    if type(value) in (int,float):
        return int(value)
    if not isinstance(value,str) or not value.strip():
        return None
    try:
        parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
        if parsed.tzinfo is None:
            parsed=parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    except ValueError:
        return None


def gather(con,now_epoch:int):
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("BEGIN")
    expected={
        "skip_jobs":{"asset_key","status","updated_at"},
        "skip_assets":{"asset_key","playlist_id"},
        "skip_analysis_sources":{"playlist_id","enabled"},
        "skip_analysis_playlists":{"id","archived"},
    }
    for table,fields in expected.items():
        columns={r[1] for r in con.execute("PRAGMA table_info("+table+")")}
        if not fields<=columns:
            return {"sampled_at_epoch":now_epoch,"analysis_lanes":[]}
    lanes=[]
    for pid in (8,10):
        source=con.execute("""SELECT p.archived,s.enabled
          FROM skip_analysis_playlists p
          LEFT JOIN skip_analysis_sources s ON s.playlist_id=p.id
          WHERE p.id=?""",(pid,)).fetchone()
        if not source:
            continue
        paused=source["archived"]!=0 or source["enabled"]!=1
        waiting=con.execute("""SELECT COUNT(*)
          FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
          WHERE a.playlist_id=? AND j.status IN ('queued','running')""",(pid,)).fetchone()[0]
        last=con.execute("""SELECT MAX(j.updated_at)
          FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
          WHERE a.playlist_id=? AND j.status IN ('done','review','no_match','partial','no_reference')""",
          (pid,)).fetchone()[0]
        last_epoch=epoch(last)
        if last_epoch is None:
            # No meaningful, observed completion timestamp: omit rather
            # than treating uptime as successful analysis progress.
            continue
        # Future clock skew must not silently disable a stall alert.
        if last_epoch>now_epoch+300:
            continue
        lanes.append({"id":str(pid),"queued_jobs":int(waiting),
                      "last_progress_epoch":last_epoch,"paused":bool(paused)})
    result={"sampled_at_epoch":now_epoch,"analysis_lanes":lanes}
    playlist_cols={row[1] for row in con.execute(
        "PRAGMA table_info(skip_analysis_playlists)")}
    if "expires_at" in playlist_cols:
        expiries=[]
        for row in con.execute("""SELECT p.id,p.expires_at,p.archived,s.enabled
            FROM skip_analysis_playlists p
            JOIN skip_analysis_sources s ON s.playlist_id=p.id
            WHERE p.id IN (8,10)"""):
            expiry=row["expires_at"]
            # Zero means a permanent analysis source; never report expiry.
            if (row["archived"]==0 and row["enabled"]==1
                    and type(expiry) is int and expiry>0):
                expiries.append({"id":str(row["id"]),"expires_at_epoch":expiry})
        if expiries:
            result["playlists"]=expiries

    # EpiScene day D covers D-1 07:00 through D 07:00 Berlin.
    # Only a report generated today can create today's single daily alert.
    report_cols={row[1] for row in con.execute(
        "PRAGMA table_info(episcene_daily_reports)")}
    if {"day","generated_at"}<=report_cols:
        zone=ZoneInfo("Europe/Berlin")
        now_local=datetime.fromtimestamp(now_epoch,zone)
        day=now_local.date().isoformat()
        report=con.execute(
            "SELECT generated_at FROM episcene_daily_reports WHERE day=?",(day,)
        ).fetchone()
        if (report and now_local.time()>=clock(7)
                and type(report["generated_at"]) in (int,float)
                and 0<=now_epoch-report["generated_at"]<=24*3600):
            result["daily_report"]={
                "id":"episcene","generated_date_berlin":day,"ready":True}
    return result


def safe_write(out:Path,payload:dict):
    if out.is_symlink() or (out.exists() and out.stat().st_mode & 0o077):
        raise PermissionError("Unsafe existing metrics snapshot")
    parent=out.parent
    if parent.is_symlink() or not parent.is_dir() or parent.stat().st_mode & 0o077:
        raise PermissionError("Metrics snapshot destination must be private")
    fd,name=tempfile.mkstemp(prefix=".epi-admin-",suffix=".tmp",dir=parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            os.fchmod(f.fileno(),0o600)
            json.dump(payload,f,sort_keys=True,separators=(",",":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(name,out)
    finally:
        if os.path.exists(name):os.unlink(name)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,default=DEFAULT)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.source.is_symlink() or not args.source.is_file():
        raise SystemExit("Missing/linked production DB")
    with sqlite3.connect(args.source.resolve().as_uri()+"?mode=ro",uri=True,timeout=15) as db:
        payload=gather(db,int(time.time()))
    safe_write(args.output,payload)
    print(json.dumps({"mode":"SANITIZED_LANE_SNAPSHOT",
                      "analysis_lanes_included":len(payload["analysis_lanes"]),
                      "secret_values_printed":False,
                      "original_db_modified":False},sort_keys=True))


if __name__=="__main__":main()
