#!/usr/bin/env python3
"""Read-only, redacted EpiScene inactivity diagnosis. No raw logs, secrets or provider calls."""
from __future__ import annotations
from collections import Counter
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import subprocess

DB=Path("/var/lib/epimediahub/provisioning.db")
UNITS={
 "analysis_runner":"epimediahub-skip-analysis.service",
 "analysis_timer":"epimediahub-skip-analysis.timer",
 "analysis_coordinator":"epimediahub-analysis-worker.service",
 "api":"epimediahub-provisioning.service",
}
EVENTS={
 "worker_not_configured":r"episcene_preflight=worker_not_configured",
 "remote_unreachable_or_version_mismatch":r"episcene_preflight=worker_unreachable_or_version_mismatch",
 "run_status":r"skip_analysis_status=",
 "parallel_lane_reported":r"episcene_parallel_playlist_ids=",
 "provider_timeout":r"provider_timeout",
 "provider_connection_failure":r"provider_connection|provider_dns|provider_tls",
 "database_locked":r"database is locked|SQLITE_BUSY",
 "out_of_memory":r"out.of.memory|oom.kill|memory limit exceeded",
 "service_timeout":r"start operation timed out|timed out. terminating",
}

def systemd(unit, mode="show"):
    if unit not in UNITS.values(): raise ValueError("UNKNOWN_UNIT")
    args=(["systemctl","show","--no-pager",
      "-p","LoadState","-p","ActiveState","-p","SubState",
      "-p","Result","-p","ExecMainStatus","-p","NRestarts",
      "-p","MainPID","--",unit] if mode=="show"
      else ["systemctl","is-enabled","--",unit])
    try:
        p=subprocess.run(args,timeout=6,capture_output=True,text=True,check=False)
    except (OSError,subprocess.TimeoutExpired):
        return {"state":"unknown"}
    if mode=="enabled":
        val=p.stdout.strip()
        return val if val in ("enabled","disabled","static","masked","linked","indirect") else "unknown"
    values={}
    for line in p.stdout.splitlines():
        if "=" not in line:continue
        key,val=line.split("=",1)
        if key in ("LoadState","ActiveState","SubState","Result"):
            values[key]=val if re.fullmatch(r"[a-z_-]{2,35}",val or "") else "unknown"
        elif key in ("ExecMainStatus","NRestarts"):
            values[key]=int(val) if val.isdecimal() else None
        elif key=="MainPID":
            values["main_process_alive"]=val.isdecimal() and int(val)>0
    return values or {"state":"unknown"}

def job_state(path=DB):
    path=Path(path)
    if path.is_symlink() or not path.is_file():return {"state":"unavailable"}
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=8)) as db:
            db.execute("PRAGMA query_only=ON")
            columns={}
            for t in ("skip_jobs","skip_assets","skip_analysis_sources","skip_analysis_playlists"):
                columns[t]={r[1] for r in db.execute("PRAGMA table_info("+t+")")}
            if not {"asset_key","status","attempts","updated_at"}<=columns["skip_jobs"] or not {"asset_key","playlist_id"}<=columns["skip_assets"]:
                return {"state":"schema_mismatch"}
            db.execute("BEGIN")
            result={str(i):{"statuses":{},"eligible_queued":0,"updated_30m":0,
                            "updated_6h":0,"running_older_than_30m":0} for i in (8,10)}
            safe={"queued","running","done","failed","partial","review",
                  "no_match","no_reference","disabled","archived"}
            for pid,status,n,eligible,recent,long,stale in db.execute("""
                 SELECT a.playlist_id,j.status,COUNT(*),
                   SUM(CASE WHEN j.status='queued' AND j.attempts<3 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN datetime(j.updated_at)>=datetime('now','-30 minutes') THEN 1 ELSE 0 END),
                   SUM(CASE WHEN datetime(j.updated_at)>=datetime('now','-6 hours') THEN 1 ELSE 0 END),
                   SUM(CASE WHEN j.status='running' AND datetime(j.updated_at)<datetime('now','-30 minutes') THEN 1 ELSE 0 END)
                 FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
                 WHERE a.playlist_id IN (8,10) GROUP BY a.playlist_id,j.status"""):
                v=result[str(pid)]
                k=status if status in safe else "other"
                v["statuses"][k]=v["statuses"].get(k,0)+int(n)
                v["eligible_queued"]+=int(eligible or 0)
                v["updated_30m"]+=int(recent or 0)
                v["updated_6h"]+=int(long or 0)
                v["running_older_than_30m"]+=int(stale or 0)
            enabled={}
            if {"playlist_id","enabled"}<=columns["skip_analysis_sources"]:
                enabled={str(pid):bool(status) for pid,status in
                         db.execute("SELECT playlist_id,enabled FROM skip_analysis_sources WHERE playlist_id IN (8,10)")}
            archived={}
            if {"id","archived"}<=columns["skip_analysis_playlists"]:
                archived={str(pid):bool(status) for pid,status in
                          db.execute("SELECT id,archived FROM skip_analysis_playlists WHERE id IN (8,10)")}
            return {"state":"ok","by_playlist":result,
                    "analysis_source_enabled":enabled,"playlist_archived":archived}
    except (sqlite3.Error,OSError,ValueError):
        return {"state":"db_unavailable"}

def log_signals(unit):
    if unit not in UNITS.values():raise ValueError("UNKNOWN_UNIT")
    try:
        p=subprocess.run(["journalctl","-q","--no-pager","-o","cat",
                 "-u",unit,"--since","-30 minutes","--lines=250"],
                 timeout=10,capture_output=True,text=True,check=False)
    except (OSError,subprocess.TimeoutExpired):
        return {"state":"unavailable"}
    if p.returncode:return {"state":"unavailable"}
    counts=Counter()
    for line in p.stdout.splitlines()[:250]:
        for key,pattern in EVENTS.items():
            if re.search(pattern,line,re.IGNORECASE):counts[key]+=1
    return {"state":"ok","recognized_event_counts":dict(counts),"raw_logs_exported":False}

def main():
    states={name:systemd(unit) for name,unit in UNITS.items()}
    states["analysis_timer"]["enabled"]=systemd(UNITS["analysis_timer"],"enabled")
    jobs=job_state()
    logs={key:log_signals(UNITS[key]) for key in ("analysis_runner","analysis_coordinator")}
    hints=[]
    if states["analysis_runner"].get("ActiveState") not in ("active","activating") and states["analysis_timer"].get("ActiveState")!="active":
        hints.append("NO_ACTIVE_ANALYSIS_RUNNER_OR_TIMER")
    if jobs.get("state")=="ok":
        data=jobs["by_playlist"]
        if all(data[str(i)]["updated_30m"]==0 for i in (8,10)):
            hints.append("NO_JOB_UPDATES_LAST_30_MINUTES")
        if all(data[str(i)]["eligible_queued"]==0 for i in (8,10)):
            hints.append("NO_ELIGIBLE_QUEUED_JOBS")
    if any(x["recognized_event_counts"].get("remote_unreachable_or_version_mismatch",0)
           for x in logs.values() if x.get("state")=="ok"):
        hints.append("REMOTE_WORKER_PREFLIGHT_FAILED")
    print(json.dumps({"mode":"EPISCENE_IDLE_ROOT_CAUSE_READ_ONLY",
       "services":states,"analysis_jobs":jobs,"log_signals":logs,
       "hints_not_proven_causes":hints,"raw_log_lines_exported":False,
       "provider_connections":0,"production_writes":0,"service_restarts":0},
       indent=2,sort_keys=True))

if __name__=="__main__":
    main()
