#!/usr/bin/env python3
"""Defer EpiScene worker reload until neither playback nor a job is active."""
from __future__ import annotations
import os
from pathlib import Path
import sqlite3
import subprocess
import time

DB=Path('/var/lib/epimediahub/provisioning.db')
PENDING=Path('/var/lib/epimediahub/episcene-visual-peer-reload-pending')
SERVICES=('epimediahub-analysis-worker.service','epimediahub-provisioning.service')
OPTIONAL_ANALYZER='epimediahub-skip-analysis.service'


def idle(con):
    now=int(time.time())
    if con.execute("SELECT 1 FROM skip_presence WHERE expires_at>? LIMIT 1",(now,)).fetchone():
        return False
    # Legacy jobs may remain labelled 'running' after a crash. Treat only
    # recent update timestamps as evidence of current running activity.
    from datetime import datetime, timezone
    for row in con.execute("SELECT updated_at FROM skip_jobs WHERE status='running' LIMIT 10"):
        try:
            value=str(row[0]).replace('Z','+00:00')
            stamp=datetime.fromisoformat(value)
            if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
            if now-stamp.timestamp()<1200:
                return False
        except (ValueError, TypeError):
            return False
    return True


def main():
    if not PENDING.exists():
        print('NO_RELOAD_PENDING')
        return
    if PENDING.is_symlink() or not DB.is_file() or DB.is_symlink():
        raise SystemExit('STOP: unexpected database/reload file')
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=8) as db:
        db.execute('PRAGMA query_only=ON')
        if not idle(db):
            print('RELOAD_DEFERRED: running analyzer or viewer; timer will retry')
            return
    for service in SERVICES:
        active=subprocess.run(['systemctl','is-active','--quiet',service],check=False,
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8)
        if active.returncode != 0:
            raise SystemExit('RELOAD_DEFERRED: service '+service+' not active')
    stage=subprocess.run(['systemctl','show',OPTIONAL_ANALYZER,'--property=ActiveState','--value'],
                         text=True,capture_output=True,timeout=8,check=False)
    stage_state=stage.stdout.strip()
    if stage_state not in ('active','inactive'):
        raise SystemExit('RELOAD_DEFERRED: analysis scheduler state '+stage_state[:32])
    # Optional analysis service may be inactive between timer runs. Restart
    # only an already active service: do not start a provider scan on deploy.
    units=(SERVICES[0],)+( (OPTIONAL_ANALYZER,) if stage_state=='active' else () )+(SERVICES[1],)
    for service in units:
        subprocess.run(['systemctl','restart',service],check=True,timeout=75)
        if subprocess.run(['systemctl','is-active','--quiet',service],
                          timeout=8).returncode!=0:
            raise SystemExit('RELOAD_DEFERRED: failed health check of '+service)
    PENDING.unlink()
    print('SCENE_RELOAD_OK: new independent analysis visual logic is active')


if __name__=='__main__':
    main()
