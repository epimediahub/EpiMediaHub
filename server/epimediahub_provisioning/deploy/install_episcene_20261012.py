#!/usr/bin/env python3
"""Guarded overlay for the exact EpiScene build recorded on 12 October.

This installer embeds its tested modules. It preserves live lane/account code,
backs up code and SQLite consistently, checks RPC versions and rolls code back
on failure. --check reads only; --apply never activates or renews access lines.
"""
from __future__ import annotations
import argparse
import ast
import base64
import fcntl
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import zlib

MODULES=('skip_scene_reliability.py','skip_variant_reuse.py','skip_tail_check.py','skip_source_preferences.py')
BEGIN='# EPI20261012 BEGIN'
END='# EPI20261012 END'
PINS={
 'skip_scene.py':'ba4554a21df6fdaf49f2b3c59b5b4d93c1b739180ef499164ad91a7bb4a67286',
 'skip_analysis_worker.py':'a307266dec7fcabab39c33552df6be940811bb8bea58fbe969671ed1340b7e5c',
 'skip_visual.py':'be2b8f3b6266ff5ab48ee76379943bb441423b8726385957957e922a18f9f2e0',
 'skip_automation.py':'9f9c590839f22e0f68e66356da2a7693193cceca96ca0943ff3c8a09fe124d9f',
 'skip_daily_reports.py':'7ebc0e704de49c44c32768e34092d7eac58052868e5b1e829aa3606ad165be1d',
 'skip_release.py':'1b6417d3aef26ae31b7e0f860afc1c4c4902488d8b4c3d0d2d70893b872db709',
}
HOOKS={
 'skip_scene.py':'import sys as _epi_sys\nfrom skip_scene_reliability import install_scene as _epi_install\n_epi_install(_epi_sys.modules[__name__])',
 'skip_analysis_worker.py':'import sys as _epi_sys\nfrom skip_scene_reliability import install_worker as _epi_install\n_epi_install(_epi_sys.modules[__name__])',
 'skip_automation.py':'import sys as _epi_sys\nfrom skip_scene_reliability import install_automation as _epi_install\n_epi_install(_epi_sys.modules[__name__])',
 'skip_daily_reports.py':'import sys as _epi_sys\nfrom skip_scene_reliability import install_reports as _epi_install\n_epi_install(_epi_sys.modules[__name__])',
 'skip_remote_worker.py':'import sys as _epi_sys\nfrom skip_tail_check import install_compute as _epi_install\n_epi_install(_epi_sys.modules[__name__])',
 'skip_remote_protocol.py':'COMPONENTS = COMPONENTS + '+repr(MODULES),
}
COMPUTE_FILES={'skip_scene.py','skip_automation.py','skip_remote_worker.py','skip_remote_protocol.py'}
TIMER='epimediahub-skip-analysis.timer'
ANALYSIS='epimediahub-skip-analysis.service'
COMPUTE_SERVICE='epimediahub-analysis-worker.service'
WEB='epimediahub-provisioning.service'

# Filled reproducibly by build_episcene_20261012.py from the four source modules.
PAYLOAD = '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'
PAYLOAD_SHA256 = 'b7e14cb1028bb254fb91d21447f2d06b689ed2431f005d66a279869e9b113ff2'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def payload():
    if not PAYLOAD:
        raise RuntimeError('Installer payload missing; run the repository builder')
    packed=base64.b64decode(PAYLOAD,validate=True)
    if sha(packed)!=PAYLOAD_SHA256:
        raise RuntimeError('Installer payload integrity failure')
    data=json.loads(zlib.decompress(packed))
    if set(data)!=set(MODULES):
        raise RuntimeError('Unexpected module payload')
    for name,body in data.items():
        ast.parse(body,filename=name)
    return data


def is_main(node):
    return (isinstance(node,ast.If) and isinstance(node.test,ast.Compare)
            and isinstance(node.test.left,ast.Name) and node.test.left.id=='__name__'
            and len(node.test.comparators)==1 and isinstance(node.test.comparators[0],ast.Constant)
            and node.test.comparators[0].value=='__main__')


def add_hook(text,name):
    ast.parse(text,filename=name)
    if BEGIN in text or END in text:
        raise RuntimeError('Overlay already present or changed: '+name)
    block=BEGIN+'\n'+HOOKS[name]+'\n'+END+'\n'
    mains=[n for n in ast.parse(text).body if is_main(n)]
    if len(mains)>1:
        raise RuntimeError('Multiple main entries: '+name)
    lines=text.splitlines(keepends=True)
    position=mains[0].lineno-1 if mains else len(lines)
    # Keep the original bytes on either side, allowing exact idempotent checks.
    if position==len(lines) and text and not text.endswith('\n'):
        raise RuntimeError('Unsupported missing final newline: '+name)
    result=''.join(lines[:position])+block+''.join(lines[position:])
    ast.parse(result,filename=name)
    return result


def strip_hook(text,name):
    block=BEGIN+'\n'+HOOKS[name]+'\n'+END+'\n'
    if text.count(BEGIN)!=1 or text.count(block)!=1:
        raise RuntimeError('Installed overlay differs: '+name)
    return text.replace(block,'',1)


def source_preferences(con):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='skip_analysis_playlists'").fetchone():
        raise RuntimeError('Independent analysis playlists table missing; stop before edits')
    rows=con.execute('SELECT id,name FROM skip_analysis_playlists').fetchall()
    preferences={}
    for pid,name in rows:
        normalized=''.join(c for c in name.casefold() if c.isalnum())
        if normalized in ('4kanalyse','4kiptv'):
            preferences[pid]='de'
        elif normalized in ('thebest','iptvthebest'):
            preferences[pid]='it'
    if not any(v=='de' for v in preferences.values()) or not any(v=='it' for v in preferences.values()):
        raise RuntimeError('4K ANALYSE/4K IPTV and THE BEST not both identified; stop before edits')
    return preferences


def plan(controller,compute,bodies):
    originals,desired={},{}
    required={'skip_scene.py':{'analyze','capture','_cache','_save','_compare','_cached_rows','_state','migrate','release_ready','refresh_neighbours','_snapshot','_window','enabled'},
              'skip_analysis_worker.py':{'process_one','_process_one','process_batch'},
              'skip_automation.py':{'analyze','analysis_phase'},
              'skip_remote_worker.py':{'validate','execute'},
              'skip_daily_reports.py':{'build_report'}}
    for name in set(HOOKS)|{'skip_visual.py','skip_release.py'}:
        paths=[compute/name] if name=='skip_remote_worker.py' else [controller/name]
        if name!='skip_remote_worker.py' and (name in COMPUTE_FILES or name in ('skip_visual.py','skip_release.py')):
            paths.append(compute/name)
        for path in paths:
            data=path.read_bytes()
            text=data.decode('utf8')
            originals[path]=data
            already=BEGIN in text
            base=strip_hook(text,name) if already and name in HOOKS else text
            if name in PINS and sha(base.encode())!=PINS[name]:
                raise RuntimeError('Active file differs from verified 12 October build: '+str(path))
            functions={n.name for n in ast.parse(base).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
            if not required.get(name,set())<=functions:
                raise RuntimeError('Unexpected live function layout: '+str(path))
            desired[path]=(base if name not in HOOKS else add_hook(base,name)).encode()
        if len(paths)==2 and originals[paths[0]]!=originals[paths[1]]:
            raise RuntimeError('Controller/compute files differ: '+name)
    for root in (controller,compute):
        for name,body in bodies.items():
            path=root/name
            originals[path]=path.read_bytes() if path.exists() else None
            if originals[path] is not None and originals[path]!=body.encode():
                raise RuntimeError('Existing overlay module differs: '+str(path))
            desired[path]=body.encode()
    # Validate the source-language scheduler interface without replacing it.
    tree=ast.parse((controller/'skip_schedule.py').read_text())
    signatures={n.name:tuple(a.arg for a in n.args.args) for n in tree.body if isinstance(n,ast.FunctionDef)}
    if signatures.get('select_job')!=('con','playlist_id','excluded') or not {'current_playlist','ready','playlists','remember','language_stage'}<=set(signatures):
        raise RuntimeError('Unexpected live scheduler interface; export live sources before continuing')
    return originals,desired


def run(*args,timeout=60):
    return subprocess.run(args,check=True,text=True,capture_output=True,timeout=timeout)


def active(unit):
    return run('systemctl','show',unit,'-p','ActiveState','--value').stdout.strip() in ('active','activating','reloading')


def health(controller):
    code="import sys;sys.path.insert(0,sys.argv[1]);from skip_remote_client import health;h=health();assert h.get('status')=='ok';print('worker_health=ok; versions=matched')"
    result=run(str(controller/'.venv/bin/python'),'-c',code,str(controller),timeout=30)
    if 'worker_health=ok; versions=matched' not in result.stdout:
        raise RuntimeError('Worker health confirmation missing')


def atomic(path,data,reference):
    st=(path if path.exists() else reference).stat()
    fd,temp=tempfile.mkstemp(prefix='.episcene-20261012-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chmod(temp,st.st_mode&0o777)
        os.chown(temp,st.st_uid,st.st_gid)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check',action='store_true')
    mode.add_argument('--apply',action='store_true')
    parser.add_argument('--controller',type=Path,default=Path('/opt/epimediahub/provisioning'))
    parser.add_argument('--compute',type=Path,default=Path('/opt/epimediahub/analysis'))
    parser.add_argument('--database',type=Path,default=Path('/var/lib/epimediahub/provisioning.db'))
    args=parser.parse_args(argv)
    if os.geteuid()!=0:
        raise RuntimeError('Run as root on the combined EpiScene controller/compute host')
    bodies=payload()
    originals,desired=plan(args.controller,args.compute,bodies)
    con=sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        preferences=source_preferences(con)
        # Existing human records, customer playlists and access flags are only
        # read here. No app import or schema migration occurs in --check.
        integrity=con.execute('PRAGMA quick_check').fetchone()[0]
        if integrity!='ok':
            raise RuntimeError('Database quick_check failed')
    finally:
        con.close()
    health(args.controller)
    for path in desired:
        if not (path.parent/'.venv/bin/python').is_file():
            raise RuntimeError('Missing deployed venv: '+str(path.parent))
    if shutil.disk_usage(args.compute).free<1024**3:
        raise RuntimeError('Less than 1 GiB free; stop before edits')
    print('CHECK OK: active hashes, preserved live wrappers, private RPC and analysis source identities verified',flush=True)
    print('Source preferences: '+json.dumps(preferences,sort_keys=True),flush=True)
    if args.check:
        print('Read-only: no files, services, access flags or database rows changed',flush=True)
        return 0
    if all(originals[p]==data for p,data in desired.items()):
        print('Overlay already installed; RPC healthy. No repeat installation.',flush=True)
        return 0
    lock=(args.controller/'.episcene-20261012-install.lock').open('a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError('Another EpiScene 12 October installation is running')
    try:
        return apply(args,originals,desired,preferences)
    finally:
        lock.close()


def apply(args,originals,desired,preferences):
    units=(TIMER,ANALYSIS,COMPUTE_SERVICE,WEB)
    states={u:active(u) for u in units}
    if not states[COMPUTE_SERVICE]:
        raise RuntimeError('Compute service inactive; no changes')
    backup_root=args.compute/'backups'
    backup_root.mkdir(mode=0o700,exist_ok=True)
    backup=Path(tempfile.mkdtemp(prefix='episcene-20261012-',dir=backup_root))
    os.chmod(backup,0o700)
    for path,data in originals.items():
        if data is not None:
            shutil.copy2(path,backup/(('controller-' if path.parent==args.controller else 'compute-')+path.name))
    print('Backup: '+str(backup),flush=True)
    pref_before=None
    written=set()
    try:
        run('systemctl','stop',TIMER)
        run('systemctl','stop',ANALYSIS)
        run('systemctl','stop',COMPUTE_SERVICE)
        for path,data in originals.items():
            current=path.read_bytes() if path.exists() else None
            if current!=data:
                raise RuntimeError('Code changed since preflight; stopped before any code edits: '+str(path))
        # Do not restore this whole DB on a code rollback: dashboard users can
        # create human markers concurrently. This is a consistent backup only.
        with sqlite3.connect(args.database) as dbcon, sqlite3.connect(backup/'provisioning.db') as saved:
            dbcon.backup(saved)
        os.chmod(backup/'provisioning.db',0o600)
        for path,data in desired.items():
            if originals[path]!=data:
                atomic(path,data,path.parent/'skip_scene.py')
                written.add(path)
        for root in (args.controller,args.compute):
            run(str(root/'.venv/bin/python'),'-m','py_compile',*[str(p) for p in desired if p.parent==root])
        run('systemctl','start',COMPUTE_SERVICE)
        for attempt in range(12):
            try:
                health(args.controller)
                break
            except (RuntimeError,subprocess.SubprocessError):
                if attempt==11:
                    raise
                time.sleep(1)
        # Configure priorities only after compatible modules and RPC are live.
        sys.path.insert(0,str(args.controller))
        from skip_source_preferences import migrate
        with sqlite3.connect(args.database) as dbcon:
            migrate(dbcon)
            pref_before=dict(dbcon.execute('SELECT playlist_id,language FROM skip_source_preferences'))
            dbcon.executemany('INSERT OR REPLACE INTO skip_source_preferences VALUES(?,?)',preferences.items())
        if states[WEB]:
            run('systemctl','restart',WEB)
            if not active(WEB):
                raise RuntimeError('Provisioning service did not recover')
        manifest=dict(applied_at=datetime.now(timezone.utc).isoformat(),module_hashes={str(p):sha(data) for p,data in desired.items()},source_preferences=preferences,backup=str(backup))
        (backup/'installation.json').write_text(json.dumps(manifest,indent=2)+'\n')
        if states[TIMER]:
            run('systemctl','start',TIMER)
        if states[ANALYSIS]:
            run('systemctl','start','--no-block',ANALYSIS)
    except BaseException:
        for path in written:
            data=originals[path]
            if data is None:
                path.unlink(missing_ok=True)
            else:
                atomic(path,data,path.parent/'skip_scene.py')
        if pref_before is not None:
            with sqlite3.connect(args.database) as dbcon:
                for pid in preferences:
                    dbcon.execute('DELETE FROM skip_source_preferences WHERE playlist_id=?',(pid,))
                dbcon.executemany('INSERT OR REPLACE INTO skip_source_preferences VALUES(?,?)',pref_before.items())
        for unit in (COMPUTE_SERVICE,WEB):
            if states[unit]:
                subprocess.run(['systemctl','restart',unit],check=False,timeout=60)
        if states[TIMER]:
            subprocess.run(['systemctl','start',TIMER],check=False,timeout=60)
        if states[ANALYSIS]:
            subprocess.run(['systemctl','start','--no-block',ANALYSIS],check=False,timeout=60)
        print('Installation failed; original code restored. Backup: '+str(backup),file=sys.stderr,flush=True)
        raise
    print('INSTALL OK: overlay synchronized, RPC healthy, original service states restored',flush=True)
    print('4K: Deutsch zuerst. THE BEST: Italienisch zuerst. Zugangsschalter und manuelle Zeitmarken unverändert.',flush=True)
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError,ValueError,OSError,sqlite3.Error,subprocess.SubprocessError) as error:
        # Do not print subprocess stdout/stderr: live service logs may contain
        # credentials. Fixed error summaries and exit status are sufficient.
        print('STOP: '+str(error),file=sys.stderr,flush=True)
        raise SystemExit(1)
