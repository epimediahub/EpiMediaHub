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
PAYLOAD_SHA256 = 'ff1744fbe27f6d8001e0e75e902c24da52684aba32c760ea2fd04045686d9d62'


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
    for name in sorted(set(HOOKS)|{'skip_visual.py','skip_release.py'}):
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
            try:
                parsed=ast.parse(base,filename=name)
            except SyntaxError:
                raise RuntimeError('Invalid active Python syntax: '+str(path)) from None
            functions={n.name for n in parsed.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
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
