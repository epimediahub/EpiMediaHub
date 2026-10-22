#!/usr/bin/env python3
"""One-shot guarded EpiScene playlist-only source update with fail-closed rollback.

Only for the precisely pinned 2026-10-21 production source fingerprints.
Pauses scheduled new work, waits for quiescence and playback clearance, backs
up SQLite and modules, validates Python syntax, swaps files atomically and
restarts compute/web. Never changes DB records or acceptance thresholds.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

APP=Path('/opt/epimediahub/provisioning')
LEARNING=Path('/opt/episcene-learning')
LEARN_FILE=LEARNING/'safe_release_rollout_v2.py'
# Fingerprint of the prior installed peer-learning helper (original official installer).
OLD_LEARN_SHA='6653aab53d22d5c2fa08a2163f42487bf7bd92b0a4658b6ef150156bf5fa49d2'
LEARN_REV='d63d66c81cf05410052ee7e76b209a4c1a666851'
LEARN_URL=('https://raw.githubusercontent.com/epimediahub/EpiMediaHub/'+LEARN_REV+
           '/tools/episcene-learning-v1/visual-peer-fix/safe_release_rollout_v2.py')
DATA=Path('/var/lib/epimediahub')
DB=DATA/'provisioning.db'
WORKER_LOCK=DATA/'skip-analysis.lock'
INSTALL_LOCK=DATA/'.episcene-playlist-only-install.lock'
PENDING=DATA/'episcene-visual-peer-reload-pending'
BACKUPS=DATA/'episcene-playlist-only-backups'
ANALYSIS='epimediahub-skip-analysis.service'
SHADOW='episcene-visual-shadow-capture.service'
LEARN_SERVICES=('episcene-safe-release-learning.service',
                'episcene-owner-learning-shadow.service',
                'episcene-learning-reference-40.service')
COMPUTE='epimediahub-analysis-worker.service'
WEB='epimediahub-provisioning.service'
ANALYSIS_TIMER='epimediahub-skip-analysis.timer'
OTHER_TIMERS=('episcene-safe-release-learning.timer',
              'episcene-owner-learning-shadow.timer',
              'episcene-learning-reference-40.timer')
PATCH_REV='be61608ddd848544c34fdc531f91e644c13c2f5c'
URL=('https://raw.githubusercontent.com/epimediahub/EpiMediaHub/'+PATCH_REV+
     '/tools/episcene-learning-v1/playlist-only/neutralize_priority.py')


def command(*args,timeout=80):
    result=subprocess.run(args,check=False,capture_output=True,text=True,timeout=timeout)
    if result.returncode!=0:
        raise RuntimeError('Command failed: '+ ' '.join(str(x) for x in args[:2]))
    return result.stdout


def active(unit):
    state=command('systemctl','show',unit,'-p','ActiveState','--value',timeout=10).strip()
    if state in ('active','activating','reloading','deactivating'):return True
    if state in ('inactive','failed'):return False
    raise RuntimeError('Unknown systemd unit/state: '+unit)


def playback():
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=15) as db:
        db.execute('PRAGMA query_only=ON')
        return int(db.execute('SELECT COUNT(*) FROM skip_presence WHERE expires_at>?',(int(time.time()),)).fetchone()[0])


def worker_running_rows():
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=15) as db:
        db.execute('PRAGMA query_only=ON')
        return db.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='running'").fetchone()[0]


def download_patcher(folder):
    destination=folder/'neutralize_priority.py'
    command('curl','-fsSL','--retry','2','--max-time','60',URL,'-o',str(destination),timeout=90)
    import importlib.util
    spec=importlib.util.spec_from_file_location('episcene_neutralize',destination)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def atomic_write(path,content,*,reference):
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.episcene-stage-',
                                     delete=False) as tmp:
        staging=Path(tmp.name)
        try:
            tmp.write(content)
            tmp.flush();os.fsync(tmp.fileno())
            meta=reference.stat()
            os.chown(staging,meta.st_uid,meta.st_gid)
            os.chmod(staging,meta.st_mode&0o7777)
            os.replace(staging,path)
        finally:
            if staging.exists():staging.unlink()


def backup_database(target):
    if DB.is_symlink() or not DB.is_file():
        raise RuntimeError('Unexpected DB path')
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=30) as current:
        with sqlite3.connect(target,timeout=30) as saved:
            current.backup(saved,pages=200)
            if saved.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                raise RuntimeError('DB snapshot verification failed')
    os.chmod(target,0o600)


def prepare(folder,neutralizer):
    edits=neutralizer.patch_known_files(APP,verify_sha=True)
    for name,contents in edits.items():
        compile(contents,str(APP/name),'exec')
        (folder/('patched-'+name)).write_bytes(contents)
    print('BASELINE OK: '+str(len(edits))+' exact-version Python modules; syntax verified',flush=True)
    if LEARNING.is_symlink() or not LEARNING.is_dir() or LEARN_FILE.is_symlink() or not LEARN_FILE.is_file():
        raise RuntimeError('Missing trusted learning installation')
    if hashlib.sha256(LEARN_FILE.read_bytes()).hexdigest()!=OLD_LEARN_SHA:
        raise RuntimeError('Learning helper was changed independently; no installation')
    peer=folder/'safe_release_rollout_v2.py'
    command('curl','-fsSL','--retry','2','--max-time','60',LEARN_URL,'-o',str(peer),timeout=90)
    compile(peer.read_bytes(),str(LEARN_FILE),'exec')
    print('LEARNING BASELINE OK: independent candidate selection upgrade staged',flush=True)
    return edits,peer.read_bytes()


def check_core():
    if os.geteuid()!=0:
        raise RuntimeError('Root required')
    for path in (APP,DATA):
        if path.is_symlink() or not path.is_dir():
            raise RuntimeError('Unexpected production directory')
    for path in (DB,WORKER_LOCK,INSTALL_LOCK,PENDING):
        if path.is_symlink():
            raise RuntimeError('Unexpected symlink '+path.name)
    if PENDING.exists():
        raise RuntimeError('A prior scene reload is pending; do not overlap releases')
    for service in (WEB,COMPUTE):
        if not active(service):
            raise RuntimeError('Expected active application service: '+service)
    for unit in (ANALYSIS_TIMER, 'episcene-visual-peer-reload.timer'):
        if not active(unit):
            raise RuntimeError('Expected active timer: '+unit)


def wait_quiet(timeout_seconds=540):
    deadline=time.monotonic()+timeout_seconds
    last_log=0
    while time.monotonic()<deadline:
        if playback():
            raise RuntimeError('Playback became active; postponing deployment safely')
        busy=active(ANALYSIS) or active(SHADOW) or any(active(unit) for unit in LEARN_SERVICES)
        if not busy:
            if not WORKER_LOCK.is_file():
                raise RuntimeError('Original analysis worker lock is missing')
            lock=WORKER_LOCK.open('rb')
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                if (not active(ANALYSIS) and not active(SHADOW)
                        and not any(active(unit) for unit in LEARN_SERVICES) and not playback()):
                    return lock
            except BlockingIOError:
                pass
            lock.close()
        if time.monotonic()-last_log>30:
            print('Warte auf sicheren Abschluss des laufenden Analyse-Batches ...',flush=True)
            last_log=time.monotonic()
        time.sleep(4)
    raise RuntimeError('Analysis did not reach a safe update boundary in 9 minutes')


def install(*,dry_run=False):
    if not dry_run:
        raise RuntimeError('Mixed-language 4K source still lacks fully integrated German-only dispatch gate; deployment blocked')
    check_core()
    if playback():
        raise RuntimeError('Viewer playback active; leave current work untouched')
    if INSTALL_LOCK.exists() and INSTALL_LOCK.is_symlink():
        raise RuntimeError('Unsafe installer lock')
    with INSTALL_LOCK.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix='episcene-stage-') as path:
            folder=Path(path)
            neutralizer=download_patcher(folder)
            edits,peer=prepare(folder,neutralizer)
            if dry_run:
                print('DRY RUN OK: no files, timers or DB records changed')
                return
            if BACKUPS.is_symlink():
                raise RuntimeError('Unexpected backup directory')
            BACKUPS.mkdir(mode=0o700,exist_ok=True)
            os.chmod(BACKUPS,0o700)
            archive=BACKUPS/('playlist-only-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+str(os.getpid()))
            archive.mkdir(mode=0o700)
            for name in edits:
                shutil.copy2(APP/name,archive/name)
            shutil.copy2(LEARN_FILE,archive/'safe_release_rollout_v2.py')
            backup_database(archive/'provisioning.sqlite3')
            print('BACKUP OK: module originals and SQLite consistent snapshot',flush=True)
            timer_states={unit:active(unit) for unit in (ANALYSIS_TIMER,)+OTHER_TIMERS}
            altered=[]
            worker_lock=None
            try:
                for timer,on in timer_states.items():
                    if on:command('systemctl','stop',timer)
                worker_lock=wait_quiet()
                # Fail if any production module changed between preflight and the swap.
                for name,expected in neutralizer.BASELINE.items():
                    if hashlib.sha256((APP/name).read_bytes()).hexdigest()!=expected:
                        raise RuntimeError('Module changed after preflight: '+name)
                if hashlib.sha256(LEARN_FILE.read_bytes()).hexdigest()!=OLD_LEARN_SHA:
                    raise RuntimeError('Learning helper changed after preflight')
                for name,content in edits.items():
                    atomic_write(APP/name,content,reference=archive/name)
                    altered.append(name)
                atomic_write(LEARN_FILE,peer,reference=archive/'safe_release_rollout_v2.py')
                altered.append('learning/safe_release_rollout_v2.py')
                for service in (COMPUTE,WEB):
                    command('systemctl','restart',service,timeout=90)
                    if not active(service):
                        raise RuntimeError('Service did not become healthy: '+service)
                print('INSTALL OK: language-ranking neutral in core and peer learning; services restarted',flush=True)
                print('Installer issued no direct database updates, approvals or playlist edits',flush=True)
            except BaseException:
                if altered:
                    print('ROLLBACK: restoring original modules',flush=True)
                    for name in altered:
                        if name=='learning/safe_release_rollout_v2.py':
                            atomic_write(LEARN_FILE,(archive/'safe_release_rollout_v2.py').read_bytes(),reference=archive/'safe_release_rollout_v2.py')
                        else:
                            atomic_write(APP/name,(archive/name).read_bytes(),reference=archive/name)
                    for service in (COMPUTE,WEB):
                        try:command('systemctl','restart',service,timeout=90)
                        except Exception:print('WARNING: rollback restart failed for '+service,flush=True)
                raise
            finally:
                if worker_lock is not None:
                    worker_lock.close()
                for timer,on in timer_states.items():
                    try:
                        if on:command('systemctl','start',timer)
                    except Exception:
                        print('ALERT: Could not restore timer '+timer,flush=True)
            print('BACKUP: '+str(archive),flush=True)


def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--apply',action='store_true')
    group.add_argument('--check',action='store_true')
    a=parser.parse_args()
    install(dry_run=a.check)


if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError,ValueError,sqlite3.Error,subprocess.SubprocessError) as err:
        print('SAFETY STOP: '+str(err),file=sys.stderr)
        raise SystemExit(2)
