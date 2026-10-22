#!/usr/bin/env python3
"""Fix missing SQLite 'kind' in EpiScene Knowledge First optional shortcut.

Asset-level skip_jobs rows do NOT contain a 'kind'. When the optional
knowledge-first decider gets one, it must decline the optimization, leaving
the original image/audio analyzer to run. No approval logic is changed.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time

ROOT=Path('/opt/epimediahub/provisioning')
TARGET=ROOT/'episcene_knowledge_first_runtime.py'
WORKER=ROOT/'skip_analysis_worker.py'
DATABASE=Path('/var/lib/epimediahub/provisioning.db')
LOCK=Path('/var/lib/epimediahub/skip-analysis.lock')
BACKUPS=Path('/var/backups/epimediahub/knowledge-first-kind-fix')
SERVICE='epimediahub-skip-analysis.service'
TIMER='epimediahub-skip-analysis.timer'
STAMP='# EPI_KF_MISSING_KIND_SAFE_V1'

def corrected(source):
    """Only alter the known line in decide(), refuse all unknown source shapes."""
    if STAMP in source:return None
    root=ast.parse(source)
    funcs=[n for n in root.body if isinstance(n,ast.FunctionDef) and n.name=='decide']
    wrappers=[n for n in ast.walk(root) if isinstance(n,ast.FunctionDef) and n.name=='wrapped']
    if len(funcs)!=1 or len(wrappers)!=1:
        raise ValueError('STOP_UNKNOWN_FUNCTION_SHAPE')
    targets=[]
    for n in ast.walk(funcs[0]):
        if not isinstance(n,ast.Assign) or len(n.targets)!=1 or not isinstance(n.targets[0],ast.Name):
            continue
        v=n.value
        if n.targets[0].id=='kind' and isinstance(v,ast.Subscript) and isinstance(v.value,ast.Name) and v.value.id=='job' and isinstance(v.slice,ast.Constant) and v.slice.value=='kind':
            targets.append(n)
    if len(targets)!=1:
        raise ValueError('STOP_EXPECTED_KIND_LOOKUP_NOT_FOUND')
    if not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
               and n.func.id=='decider' for n in ast.walk(wrappers[0])):
        raise ValueError('STOP_UNEXPECTED_WRAPPER')
    n=targets[0]
    lines=source.splitlines(keepends=True)
    if n.lineno!=n.end_lineno:
        raise ValueError('STOP_MULTILINE_LOOKUP')
    m=re.fullmatch(r"""(?P<i>[ ]+)kind\s*=\s*job\[['"]kind['"]\]\s*(?:\r?\n)?""",lines[n.lineno-1])
    if not m:
        raise ValueError('STOP_UNEXPECTED_KIND_ASSIGNMENT')
    indent=m.group('i')
    if len(indent)<4:
        raise ValueError('STOP_UNEXPECTED_INDENT')
    eol='\r\n' if lines[n.lineno-1].endswith('\r\n') else '\n'
    lines[n.lineno-1:n.lineno]=[
        indent+STAMP+eol,
        indent+'try:'+eol,
        indent+"    kind = job['kind']"+eol,
        indent+'except (KeyError, IndexError):'+eol,
        indent+'    return None'+eol]
    output=''.join(lines)
    compile(output,str(TARGET),'exec')
    return output

def run(*cmd,check=True):
    return subprocess.run(cmd,capture_output=True,text=True,check=check)

def active(unit):
    return run('systemctl','is-active','--quiet',unit,check=False).returncode==0

def safe(path,limit=100000):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>limit:
        raise ValueError('STOP_UNEXPECTED_FILE: '+path.name)

def schema_check():
    safe(DATABASE,limit=10**12)
    with sqlite3.connect(DATABASE.resolve().as_uri()+'?mode=ro',uri=True,timeout=5) as db:
        columns={row[1] for row in db.execute('PRAGMA table_info(skip_jobs)')}
    if not {'asset_key','status'}<=columns or 'kind' in columns:
        raise ValueError('STOP_SCHEMA_CHANGED')

def patch(*,check_only=False):
    if ROOT.is_symlink() or ROOT.is_dir() is False:
        raise ValueError('STOP_MISSING_DEPLOYMENT')
    safe(TARGET);safe(WORKER)
    if LOCK.is_symlink() or not LOCK.is_file():
        raise ValueError('STOP_MISSING_LOCK')
    schema_check()
    original=TARGET.read_text(encoding='utf-8')
    result=corrected(original)
    if result is None:
        print('ALREADY_INSTALLED: missing kind handled')
        return
    if check_only:
        print('PREFLIGHT_OK: missing kind has safe no-hint fallback')
        return
    if os.geteuid()!=0:
        raise ValueError('STOP_ROOT_REQUIRED')
    was_active=active(TIMER)
    if was_active:
        run('systemctl','stop',TIMER)
    try:
        with LOCK.open('a+b') as handle:
            start=time.monotonic()
            while True:
                try:
                    fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    locked=True
                except BlockingIOError:
                    locked=False
                if locked and not active(SERVICE):
                    break
                if locked:
                    fcntl.flock(handle,fcntl.LOCK_UN)
                if time.monotonic()-start>120:
                    raise ValueError('STOP_BUSY: worker still owns analysis lock, no change')
                time.sleep(2)
            if TARGET.read_text(encoding='utf-8')!=original or active(SERVICE):
                raise ValueError('STOP_WORKER_OR_SOURCE_CHANGED')
            backup_folder=BACKUPS/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+str(os.getpid()))
            backup_folder.mkdir(parents=True,mode=0o700,exist_ok=False)
            backup_folder.chmod(0o700)
            backup=backup_folder/TARGET.name
            shutil.copy2(TARGET,backup)
            backup.chmod(0o600)
            metadata=TARGET.stat()
            temp=None
            try:
                fd,temp=tempfile.mkstemp(prefix='.episcene-kind-',dir=ROOT)
                with os.fdopen(fd,'w',encoding='utf-8') as output:
                    output.write(result)
                    output.flush()
                    os.fsync(output.fileno())
                os.chown(temp,metadata.st_uid,metadata.st_gid)
                os.chmod(temp,metadata.st_mode&0o7777)
                os.replace(temp,TARGET)
                temp=None
                if TARGET.read_text(encoding='utf-8')!=result:
                    raise ValueError('STOP_FILE_VERIFY_FAILED')
            except Exception:
                shutil.copy2(backup,TARGET)
                raise
            finally:
                if temp and os.path.exists(temp):
                    os.unlink(temp)
            print('BACKUP_OK:',backup)
            print('INSTALL_OK: Knowledge First no longer crashes on missing kind')
            print('RELEASE_GATES_UNCHANGED; NO_DATABASE_CHANGES')
    finally:
        if was_active:
            run('systemctl','start',TIMER)
            print('TIMER_RESTORED: active')

def main():
    p=argparse.ArgumentParser()
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--check',action='store_true')
    group.add_argument('--apply',action='store_true')
    args=p.parse_args()
    patch(check_only=args.check)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,sqlite3.Error,subprocess.CalledProcessError,SyntaxError) as exc:
        print('SAFE_STOP:',type(exc).__name__,str(exc))
        raise SystemExit(1)
