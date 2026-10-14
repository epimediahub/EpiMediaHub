#!/usr/bin/env python3
"""Finish the already-installed EpiScene scene reload at a safe job boundary.

The previous gate required EVERY analysis job to be inactive before reloading,
but EpiScene's periodic scheduler immediately starts another one. Instead:
  - Never disturb active user playback.
  - Temporarily pause ONLY the new-job timer (leave an executing job running).
  - Wait until the active bounded batch finishes, using its systemd state plus
    its existing advisory worker lock as independent safety evidence.
  - Restart compute and web when quiescent; resume the timer afterwards.
  - Leave the pending flag until all restarts and health checks complete.
Output is only aggregate counts and service state, never customer data.
"""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import sqlite3
import subprocess
import time

DATA=Path('/var/lib/epimediahub')
DB=DATA/'provisioning.db'
PENDING=DATA/'episcene-visual-peer-reload-pending'
PAUSED=DATA/'episcene-visual-peer-analysis-timer-paused'
MUTEX=DATA/'.episcene-visual-peer-reload.lock'
WORKER_LOCK=DATA/'skip-analysis.lock'
ANALYSIS_TIMER='epimediahub-skip-analysis.timer'
ANALYSIS='epimediahub-skip-analysis.service'
COMPUTE='epimediahub-analysis-worker.service'
WEB='epimediahub-provisioning.service'
SHADOW='episcene-visual-shadow-capture.service'


def call(*args,timeout=30,check=False):
    return subprocess.run(args,check=check,timeout=timeout,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,text=True)


def is_active(unit):
    result=call('systemctl','is-active','--quiet',unit,timeout=8)
    if result.returncode==0:
        return True
    result=call('systemctl','show',unit,'-p','ActiveState','--value',timeout=8)
    if result.returncode!=0:
        raise RuntimeError('Cannot determine status of '+unit)
    if result.stdout.strip() in ('inactive','failed'):
        return False
    if result.stdout.strip() in ('activating','deactivating','reloading'):
        return True
    raise RuntimeError('Unexpected service state for '+unit)


def presence():
    if DB.is_symlink() or not DB.is_file():
        raise RuntimeError('Expected EpiScene SQLite database unavailable')
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=12) as db:
        db.execute('PRAGMA query_only=ON')
        # A current playback lease may also be renewed while an episode runs.
        return db.execute('SELECT COUNT(*) FROM skip_presence WHERE expires_at>?',(int(time.time()),)).fetchone()[0]


def job_rows_running():
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=12) as db:
        db.execute('PRAGMA query_only=ON')
        return db.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='running'").fetchone()[0]


def file_guard(path):
    if path.is_symlink():
        raise RuntimeError('Unexpected symlink on '+path.name)


def snapshot():
    return dict(playback_leases=presence(),
                database_running_rows=job_rows_running(),
                analysis_batch_active=is_active(ANALYSIS),
                analysis_timer_active=is_active(ANALYSIS_TIMER),
                shadow_visual_capture_active=is_active(SHADOW),
                compute_active=is_active(COMPUTE),
                web_active=is_active(WEB),
                reload_pending=PENDING.exists(),
                timer_paused_by_reload=PAUSED.exists())


def log_status(mode,reason):
    info=snapshot()
    # Neither customer names nor playlist/provider IDs are printed.
    print(mode+': '+reason+'; '+', '.join(k+'='+str(v).lower() for k,v in info.items()),flush=True)


def finish():
    file_guard(PENDING)
    file_guard(PAUSED)
    file_guard(MUTEX)
    file_guard(WORKER_LOCK)
    if not PENDING.exists():
        # Fail closed if a previous process died between completing a
        # restart and clearing our maintenance marker.
        if PAUSED.exists():
            call('systemctl','start',ANALYSIS_TIMER,timeout=30,check=True)
            PAUSED.unlink()
        print('NO_RELOAD_PENDING',flush=True)
        return
    if not is_active(COMPUTE) or not is_active(WEB):
        log_status('RELOAD_DEFERRED','required_compute_or_web_not_active')
        return
    if presence():
        log_status('RELOAD_DEFERRED','active_viewer_or_playback_lease')
        return

    # Quiesce the producer rather than waiting forever for coincidental idle
    # between batches. Stop the timer only; do NOT stop/kill the current job.
    if is_active(ANALYSIS_TIMER):
        call('systemctl','stop',ANALYSIS_TIMER,timeout=30,check=True)
        if is_active(ANALYSIS_TIMER):
            raise RuntimeError('Could not pause new analysis jobs')
        if not PAUSED.exists():
            with PAUSED.open('x') as f:
                f.write('timer_paused_by_episcene_visual_peer_reload\n')
            os.chmod(PAUSED,0o600)
    elif not PAUSED.exists():
        # Analysis timer was intentionally disabled before our task.
        # Do not silently enable it during the subsequent restart.
        pass

    if is_active(ANALYSIS):
        log_status('RELOAD_DEFERRED','waiting_for_current_analysis_batch_to_finish')
        return
    if is_active(SHADOW):
        log_status('RELOAD_DEFERRED','waiting_for_visual_capture_to_finish')
        return
    if presence():
        log_status('RELOAD_DEFERRED','new_playback_lease_since_timer_pause')
        return

    # The worker holds this lock through its entire batch, even if systemd
    # is racing to update the unit state. Holding our lock prevents a new
    # periodic or manually spawned worker from acquiring it during restart.
    with WORKER_LOCK.open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            log_status('RELOAD_DEFERRED','worker_lock_still_held')
            return
        if is_active(ANALYSIS) or presence() or is_active(SHADOW):
            log_status('RELOAD_DEFERRED','new_work_or_playback_since_last_check')
            return
        # Never restart an active job. Only these long-lived Python servers
        # need to import the new scene code. The analysis batch is inactive.
        for unit in (COMPUTE,WEB):
            call('systemctl','restart',unit,timeout=75,check=True)
            if not is_active(unit):
                raise RuntimeError('Health check failed for '+unit)
    # The patched source was already on disk; restart is now complete.
    # Restore job scheduling only when this task explicitly paused it.
    if PAUSED.exists():
        call('systemctl','start',ANALYSIS_TIMER,timeout=30,check=True)
        if not is_active(ANALYSIS_TIMER):
            raise RuntimeError('Failed to resume analysis timer')
        PAUSED.unlink()
    PENDING.unlink()
    print('SCENE_RELOAD_OK: compute/web refreshed; analyzer timer safely restored',flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--status',action='store_true',help='read-only blocker details')
    args=parser.parse_args()
    if args.status:
        log_status('RELOAD_STATUS','read_only')
        return
    if os.geteuid()!=0:
        raise RuntimeError('Root required to restart the EpiScene services')
    file_guard(MUTEX)
    with MUTEX.open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('RELOAD_DEFERRED: another reload is running',flush=True)
            return
        finish()


if __name__=='__main__':
    try:
        main()
    except (RuntimeError,OSError,sqlite3.Error,subprocess.SubprocessError) as error:
        print('RELOAD_BLOCKED: '+str(error),flush=True)
        raise SystemExit(1)
