#!/usr/bin/env python3
"""One private admin monitoring cycle, no secrets or customer data in reports.

Uses only read-only EpiScene lanes 8/10 until other telemetry adapters are
verified independently. The existing alert code queues undelivered FCM alerts
for retry; absence of telemetry never means healthy.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import time

from live_analysis_snapshot import DEFAULT,gather,safe_write
from monitor_cycle import run_once


def run(directory:Path,db_path:Path=DEFAULT,now:int|None=None):
    ts=int(time.time()) if now is None else int(now)
    if directory.is_symlink() or not directory.is_dir() or (
            directory.stat().st_mode & 0o077) or (
            directory.stat().st_uid!=os.geteuid()):
        raise PermissionError("Private admin directory required")
    if db_path.is_symlink() or not db_path.is_file():
        raise PermissionError("Production analysis DB missing or linked")
    with sqlite3.connect(db_path.resolve().as_uri()+"?mode=ro",uri=True,timeout=15) as db:
        snapshot=gather(db,ts)
    snapshot_path=directory/"analysis-metrics.json"
    safe_write(snapshot_path,snapshot)
    report=run_once(snapshot_path,directory,ts)
    report["telemetry_coverage"]=["analysis_lanes_8_10"]
    report["unavailable_telemetry_marked_healthy"]=False
    return report


if __name__=="__main__":
    datadir=Path(os.environ.get("EPIMEDIAHUB_DATA_DIR","/var/lib/epimediahub"))
    print(json.dumps(run(datadir/"admin-mobile"),sort_keys=True))
