#!/usr/bin/env python3
"""One-shot guarded EpiScene audio-cache retention update.

--check: read-only live shape/worker verification and local regression tests.
--apply: in addition, consistent DB backup, idle analysis lock, atomic source
         update, safe worker reload, health/version check, automatic rollback.

No automatic marker approvals and no provider downloads/requeues are triggered.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

APP = Path('/opt/epimediahub/provisioning')
COMPUTE = Path('/opt/epimediahub/analysis')
SOURCE = APP / 'skip_automation.py'
REMOTE = COMPUTE / 'skip_automation.py'
VENV = APP / '.venv/bin/python'
DB = Path('/var/lib/epimediahub/provisioning.db')
LOCK = Path('/var/lib/epimediahub/skip-analysis.lock')
TIMER = 'epimediahub-skip-analysis.timer'
ANALYSIS = 'epimediahub-skip-analysis.service'
WORKER = 'epimediahub-analysis-worker.service'
WEB = 'epimediahub-provisioning.service'
BACKUPS = Path('/var/backups/epimediahub/episcene-cache-retention')
REPO = 'https://raw.githubusercontent.com/epimediahub/EpiMediaHub/'
# Pinned revision containing the exact audited patch and regression tests.
REV = 'aacd51c041173105930776d9bc8f66cfb4485be8'
SUBDIR = 'tools/episcene-learning-v1/cache-retention/'
FILES = ('audio_cache_patch.py', 'test_audio_cache_patch.py')

HEALTH_CODE = """
import json,sys
sys.path.insert(0,'/opt/epimediahub/provisioning')
import skip_remote_client as remote
from skip_remote_protocol import versions
r=remote.request('/health',timeout=4)
print(json.dumps({'ok':r.get('status')=='ok','local':versions(),
                  'remote':r.get('versions')}))
"""


def run(*args, timeout=40, check=True, cwd=None):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    if check and p.returncode:
        raise RuntimeError('Command failed: '+str(args[0])+' '+str(args[1:3]))
    return p


def active(name):
    p=run('systemctl','is-active','--quiet',name,check=False,timeout=10)
    return p.returncode == 0


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def ensure_file(path, max_size=2000000):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>max_size:
        raise RuntimeError('Unexpected or missing deployment file: '+str(path))


def versions():
    p=run(str(VENV),'-I','-B','-c',HEALTH_CODE,cwd=str(APP),timeout=16)
    try:
        obj=json.loads(p.stdout.strip())
    except (ValueError,TypeError):
        raise RuntimeError('Worker health returned unexpected output') from None
    if (not isinstance(obj,dict) or obj.get('ok') is not True
            or not isinstance(obj.get('local'),dict)
            or not isinstance(obj.get('remote'),dict)):
        raise RuntimeError('Worker health/version schema unavailable')
    return obj['local'],obj['remote']


def download(workdir):
    for filename in FILES:
        target=workdir/filename
        with urlopen(REPO+REV+'/'+SUBDIR+filename,timeout=25) as response:
            data=response.read(250000)
        if len(data)>200000 or not data:
            raise RuntimeError('Unexpected downloaded file size: '+filename)
        target.write_bytes(data)
        compile(data, filename, 'exec')
    p=run(sys.executable,'-B','-m','unittest','-q','test_audio_cache_patch.py',
          cwd=str(workdir),timeout=90)
    print('UNIT_TESTS_OK: '+str(len([line for line in p.stderr.splitlines()
                                   if line.strip().startswith('Ran ')]) or 1)+' suite',flush=True)


def load_patch(workdir):
    spec=importlib.util.spec_from_file_location('audio_cache_patch',workdir/'audio_cache_patch.py')
    if not spec or not spec.loader:
        raise RuntimeError('Patch module unavailable')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def eligible_environment():
    if os.geteuid()!=0:
        raise RuntimeError('STOP: root required')
    for path in (SOURCE,DB,LOCK):
        ensure_file(path, max_size=10000000000 if path==DB else 2000000)
    # Virtualenvs commonly expose bin/python as a legitimate interpreter symlink.
    if not VENV.is_file() or not os.access(VENV,os.X_OK):
        raise RuntimeError('Missing executable provisioning venv')
    if COMPUTE.is_symlink() or not COMPUTE.is_dir():
        raise RuntimeError('Compute module directory unavailable')
    if REMOTE.is_symlink():
        raise RuntimeError('Compute module path is symlink')
    if not all(active(x) for x in (WORKER,WEB)):
        raise RuntimeError('A required worker or web service is inactive')


def presence_count():
    src=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=20)
    try:
        src.execute('PRAGMA query_only=ON')
        return src.execute(
            'SELECT COUNT(*) FROM skip_presence WHERE expires_at>?',
            (int(time.time()),)).fetchone()[0]
    finally:
        src.close()


def backup_db(dest):
    old=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=90)
    new=sqlite3.connect(str(dest),timeout=90)
    try:
        old.execute('PRAGMA query_only=ON')
        old.backup(new,pages=2048,sleep=.1)
        if new.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise RuntimeError('Database backup failed integrity check')
    finally:
        old.close()
        new.close()
    os.chmod(dest,0o600)


def copy_atomic(destination, content):
    ensure_file(destination)
    before=destination.read_bytes()
    original=destination.stat()
    fd,name=tempfile.mkstemp(prefix='.episcene-cache-',dir=str(destination.parent))
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(name,original.st_uid,original.st_gid)
        os.chmod(name,stat.S_IMODE(original.st_mode))
        if digest(destination.read_bytes())!=digest(before):
            raise RuntimeError('Concurrent deployment file modification')
        os.replace(name,destination)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def apply(module,original,updated,local_versions,remote_versions,changed):
    if not changed:
        print('ALREADY_FIXED: no changes or service restart required')
        return
    if presence_count():
        raise RuntimeError('SAFE_DEFERRED: active playback; do not restart services')
    if not LOCK.is_file():
        raise RuntimeError('Missing analysis worker lock')
    initial_timer=active(TIMER)
    if initial_timer:
        run('systemctl','stop',TIMER)
    try:
        with LOCK.open('a+b') as guard:
            try:
                fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('SAFE_DEFERRED: running analysis batch')
            if active(ANALYSIS) or presence_count():
                raise RuntimeError('SAFE_DEFERRED: analysis or playback active')
            ensure_file(SOURCE)
            if SOURCE.read_bytes()!=original:
                raise RuntimeError('Source changed after preflight')
            # Optional worker-local copy: only synchronize if it was exactly
            # the same version as the controller before this deployment.
            copy_remote=REMOTE.exists()
            if copy_remote:
                ensure_file(REMOTE)
                if REMOTE.read_bytes()!=original:
                    raise RuntimeError('Unknown compute skip_automation.py version')
            now_versions=versions()
            if now_versions!=(local_versions,remote_versions):
                raise RuntimeError('Worker versions changed since preflight')
            required_bytes=DB.stat().st_size*3
            if shutil.disk_usage(BACKUPS.parent if BACKUPS.parent.exists() else DB.parent).free<required_bytes:
                raise RuntimeError('Insufficient disk space for a safe SQLite backup')
            if BACKUPS.is_symlink():
                raise RuntimeError('Unsafe backup directory')
            BACKUPS.mkdir(parents=True,exist_ok=True,mode=0o700)
            folder=BACKUPS/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+str(os.getpid()))
            folder.mkdir(mode=0o700)
            (folder/'controller.before.py').write_bytes(original)
            (folder/'controller.before.py').chmod(0o600)
            if copy_remote:
                (folder/'compute.before.py').write_bytes(REMOTE.read_bytes())
                (folder/'compute.before.py').chmod(0o600)
            backup_db(folder/'provisioning.snapshot.sqlite3')
            print('BACKUP_OK: source copies and SQLite snapshot saved',flush=True)
            # Viewers can appear while the consistent backup is being created.
            # Never restart web/compute if a new playback lease appeared.
            if active(ANALYSIS) or presence_count():
                raise RuntimeError('SAFE_DEFERRED: new playback or analysis during backup')
            # Files are atomically installed while analysis is paused and
            # the source worker lock is held.
            installed=False
            try:
                if copy_remote:
                    copy_atomic(REMOTE,updated)
                copy_atomic(SOURCE,updated)
                installed=True
                for path in ((REMOTE,) if copy_remote else ())+(SOURCE,):
                    if digest(path.read_bytes())!=digest(updated):
                        raise RuntimeError('Post-deploy source hash mismatch')
                for svc in (WORKER,WEB):
                    run('systemctl','restart',svc,timeout=90)
                    if not active(svc):
                        raise RuntimeError('Restart health failed for '+svc)
                new_local,new_remote=versions()
                if new_local!=new_remote:
                    differing=sorted(k for k in new_local.keys() | new_remote.keys()
                                     if new_local.get(k)!=new_remote.get(k))
                    raise RuntimeError('Worker versions differ after change: '+str(differing))
                print('CACHE_RETENTION_INSTALLED_OK',flush=True)
                print('WORKER_VERSION_MATCH_OK',flush=True)
                print('CURRENT_SHA256: '+digest(updated)[:16],flush=True)
                print('No markers released or jobs requeued',flush=True)
            except Exception:
                print('ROLLBACK: restoring source modules and restarting services',flush=True)
                if SOURCE.exists() and not SOURCE.is_symlink():
                    copy_atomic(SOURCE,original)
                if copy_remote and REMOTE.exists() and not REMOTE.is_symlink():
                    copy_atomic(REMOTE,(folder/'compute.before.py').read_bytes())
                for svc in (WORKER,WEB):
                    try:
                        run('systemctl','restart',svc,timeout=90)
                    except Exception:
                        print('ROLLBACK SERVICE WARNING: '+svc,flush=True)
                raise
    finally:
        if initial_timer:
            run('systemctl','start',TIMER)
            print('ANALYSIS_TIMER_RESTORED',flush=True)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--check',action='store_true')
    ap.add_argument('--apply',action='store_true')
    args=ap.parse_args()
    if args.check and args.apply:
        ap.error('Use either --check or --apply')
    if not args.check and not args.apply:
        args.check=True
    eligible_environment()
    with tempfile.TemporaryDirectory(prefix='episcene-retention-') as tmp:
        workdir=Path(tmp)
        download(workdir)
        module=load_patch(workdir)
        original=SOURCE.read_bytes()
        updated,changed=module.patch(original.decode('utf-8'))
        updated=updated.encode('utf-8')
        remote_copy_matches=None
        if REMOTE.exists():
            ensure_file(REMOTE)
            remote_copy_matches=(REMOTE.read_bytes()==original)
        local,remote=versions()
        if local!=remote:
            differing=sorted(k for k in local.keys() | remote.keys()
                              if local.get(k)!=remote.get(k))
            raise RuntimeError('PREEXISTING_WORKER_VERSION_MISMATCH: '+str(differing))
        print('SOURCE_SHA256_BEFORE: '+digest(original)[:16],flush=True)
        print('PATCH_STATUS: '+('READY' if changed else 'ALREADY_INSTALLED'),flush=True)
        print('WORKER_VERSION_MATCH_BEFORE: true',flush=True)
        print('REMOTE_COPY_PRESENT: '+str(REMOTE.exists()).lower(),flush=True)
        print('REMOTE_COPY_MATCHES_CONTROLLER_BEFORE: '+str(remote_copy_matches).lower(),flush=True)
        print('DB_SIZE_GIB: '+str(round(DB.stat().st_size/1024**3,2)),flush=True)
        if args.check:
            print('CHECK_ONLY: no files, database, workers, or marker approvals changed')
        else:
            apply(module,original,updated,local,remote,changed)


if __name__=='__main__':
    try:
        main()
    except Exception as e:
        # Error reasons contain neither customer identifiers nor IPTV URLs.
        print('CACHE_RETENTION_STOP: '+str(e),flush=True)
        raise SystemExit(1)
