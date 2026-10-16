#!/usr/bin/env python3
"""One bounded administrator alert cycle using a sanitized external metrics file.

This runner never scrapes passwords, rewrites the app/worker, reveals token data,
or marks incidents recovered on absent signals. The metrics adapter producing
the snapshot MUST be deployed separately and audited.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import time

from incident_store import IncidentStore
from mobile_registry import AdminMobileRegistry
from monitor_rules import evaluate
import fcm_sender

MAX_BYTES=128*1024
FIELDS={
    "analysis_lanes":{"id","last_progress_epoch","queued_jobs","paused"},
    "playlists":{"id","expires_at_epoch","consecutive_auth_failures"},
    "workers":{"id","expected_versions","actual_versions","consecutive_preflight_failures"},
    "services":{"id","consecutive_health_failures"},
    "builds":{"id","outcome"},
    "playback_windows":{"id","errors","sessions","distinct_affected_devices"},
}
ID=re.compile(r"^[a-zA-Z0-9_.:-]{1,64}$")


def read_snapshot(path: Path, now: int):
    if path.is_symlink() or not path.is_file():
        raise PermissionError("Metrics snapshot unavailable or is a symlink")
    info=path.stat()
    if info.st_mode & 0o077 or info.st_uid!=os.geteuid():
        raise PermissionError("Metrics snapshot must be private to service owner")
    if info.st_size>MAX_BYTES:
        raise ValueError("Metrics snapshot too large")
    snapshot=json.loads(path.read_bytes())
    if not isinstance(snapshot,dict):
        raise ValueError("Metrics snapshot must be an object")
    if set(snapshot)-set(FIELDS)-{"sampled_at_epoch","daily_report"}:
        raise ValueError("Unexpected metrics fields")
    sampled=snapshot.get("sampled_at_epoch")
    if type(sampled) is not int or not 0<=now-sampled<=120:
        raise ValueError("Stale or future metrics snapshot; no new alert")
    for kind, allowed in FIELDS.items():
        entries=snapshot.get(kind,[])
        if not isinstance(entries,list) or len(entries)>200:
            raise ValueError("Metrics list size invalid")
        for row in entries:
            if not isinstance(row,dict) or set(row)-allowed:
                raise ValueError("Unexpected nested metrics fields")
            if not isinstance(row.get("id"),str) or not ID.fullmatch(row["id"]):
                raise ValueError("Unexpected metric identifier")
            for field,value in row.items():
                if field=="id" or field=="outcome":
                    continue
                if field in ("expected_versions","actual_versions"):
                    if not isinstance(value,dict) or len(value)>20:
                        raise ValueError("Invalid version manifest")
                    if any(not isinstance(k,str) or not ID.fullmatch(k) or
                           not isinstance(v,str) or len(v)>48 or not ID.fullmatch(v)
                           for k,v in value.items()):
                        raise ValueError("Unsafe version manifest")
                elif field=="paused":
                    if type(value) is not bool:
                        raise ValueError("Unexpected paused flag")
                elif value is not None and (type(value) not in (int,float) or
                                              not -1e15<=value<=1e15):
                    raise ValueError("Unexpected numeric metrics value")
    report=snapshot.get("daily_report")
    if report is not None:
        if (not isinstance(report,dict)
            or set(report)-{"id","generated_date_berlin","ready"}
            or not isinstance(report.get("id","episcene"),str)
            or not ID.fullmatch(report.get("id","episcene"))
            or report.get("ready") not in (True,False)
            or not isinstance(report.get("generated_date_berlin"),str)
            or not re.fullmatch(r"20\d\d-\d\d-\d\d",
                                report["generated_date_berlin"])):
            raise ValueError("Unexpected daily report metadata")
    return snapshot


def run_once(snapshot_path: Path, data_dir: Path, now: int, deliver=None):
    snapshot=read_snapshot(snapshot_path,now)
    alerts=evaluate(snapshot,now)
    incidents=IncidentStore(data_dir/"incidents.sqlite3")
    newly_opened=incidents.observe(alerts,now)
    registry=AdminMobileRegistry(data_dir/"registrations.sqlite3")
    by_key={a.key:a for a in alerts}
    registry.enqueue([(key,by_key[key].kind,incidents.get(key)["first_seen_epoch"])
                      for key in newly_opened], now)
    notified=0
    failed=0
    sender=deliver if deliver is not None else fcm_sender.send
    if fcm_sender.enabled() or deliver is not None:
        for item in registry.pending():
            try:
                ok=sender(item["fcm_token"],item["kind"])
            except (Exception,):
                ok=False
            if ok:
                registry.sent(item["installation_id"],item["alert_key"],
                              item["generation_epoch"],now)
                notified+=1
            else:
                failed+=1
    return {
        "mode":"EPI_ADMIN_BOUNDED_CYCLE",
        "alerts_observed":len(alerts),
        "new_incident_generations":len(newly_opened),
        "push_sent":notified,
        "push_failed_pending_retry":failed,
        "registered_admin_installations":registry.active_count(),
        "credentials_printed":False,
        "customer_data_read":False,
        "automatic_restarts_or_license_changes":0,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--snapshot",type=Path,required=True)
    p.add_argument("--data-dir",type=Path,required=True)
    a=p.parse_args()
    if a.data_dir.is_symlink() or not a.data_dir.is_dir() or
        a.data_dir.stat().st_mode & 0o077:
        raise SystemExit("Private admin data directory required")
    print(json.dumps(run_once(a.snapshot,a.data_dir,int(time.time())),
                     sort_keys=True))


if __name__=="__main__":
    main()
