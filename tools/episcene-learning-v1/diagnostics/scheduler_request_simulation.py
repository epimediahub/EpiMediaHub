#!/usr/bin/env python3
"""EpiScene scheduler recovery preflight: execute ONLY select_job() on read-only DB.

Compare the current series-focus choice with a hypothetical *existing*
request_series-style request for the queued audio recovery canary. This
does NOT create the request, queue jobs, alter priorities, or import the
production module. Does not inspect provider URLs or print asset identities.
"""
from __future__ import annotations
import ast
from pathlib import Path
import hashlib
import inspect
import re
import sqlite3
import shutil
import tempfile

APP=Path('/opt/epimediahub/provisioning/skip_schedule.py')
DB=Path('/var/lib/epimediahub/provisioning.db')
LEDGER='episcene_audio_cache_canary_v1'


def load_selector():
    if APP.is_symlink() or not APP.is_file():
        raise RuntimeError('Scheduler source missing or symlink')
    raw=APP.read_bytes()
    tree=ast.parse(raw.decode('utf-8'), filename=str(APP))
    matches=[n for n in tree.body
             if isinstance(n,ast.FunctionDef) and n.name=='select_job']
    if len(matches)!=1:
        raise RuntimeError('Expected one top-level select_job, found '+str(len(matches)))
    fn=matches[0]
    # Refuse to execute unfamiliar/mutating code, including nested imports
    # and calls to arbitrary Python functionality.
    for node in ast.walk(fn):
        if isinstance(node,(ast.Import,ast.ImportFrom,ast.Global,ast.Nonlocal)):
            raise RuntimeError('Selector has unsupported import/global state')
        if isinstance(node,ast.Call):
            f=node.func
            if isinstance(f,ast.Name) and f.id not in ('tuple','next','range','requests','language_stage'):
                raise RuntimeError('Unsupported selector call '+f.id)
            if isinstance(f,ast.Attribute) and f.attr not in ('execute','fetchone','join'):
                raise RuntimeError('Unsupported selector attribute call '+f.attr)
        if isinstance(node,ast.Constant) and isinstance(node.value,str):
            if re.search(r'\b(INSERT|UPDATE|DELETE|REPLACE|ALTER|DROP|ATTACH|DETACH|VACUUM|PRAGMA)\b',
                         node.value,re.I):
                raise RuntimeError('Unexpected SQL or side effect in select_job')
    if not {'stage','parallel','playlist_id'} <= {a.arg for a in fn.args.args+fn.args.kwonlyargs}:
        raise RuntimeError('Unknown select_job signature')
    if not any(isinstance(n,ast.Name) and n.id=='requests' for n in ast.walk(fn)):
        raise RuntimeError('Scheduler lacks expected request override')
    return fn, hashlib.sha256(raw).hexdigest()[:16],tree


def simulation_fn(fn, requests_function):
    # Compile only this selected function, without module-level effects.
    solo=ast.Module(body=[fn],type_ignores=[])
    ast.fix_missing_locations(solo)
    ns={'__builtins__':{'tuple':tuple,'next':next,'range':range},
        'requests':requests_function,'language_stage':lambda con:2}
    exec(compile(solo, '<select_job_readonly_simulation>', 'exec'),ns,ns)
    return ns['select_job']


def table_exists(c,t):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone() is not None


def main():
    fn,sha,tree=load_selector()
    if not DB.is_file() or DB.is_symlink():
        raise RuntimeError('Production DB missing or symlink')
    if shutil.disk_usage('/tmp').free < DB.stat().st_size * 2:
        raise RuntimeError('Not enough space for read-only simulation snapshot')
    with tempfile.TemporaryDirectory(prefix='episcene-scheduler-simulation-',dir='/tmp') as folder:
        snapshot=Path(folder)/'snapshot.db'
        original=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=40)
        copy=sqlite3.connect(str(snapshot),timeout=40)
        try:
            original.execute('PRAGMA query_only=ON')
            original.backup(copy,pages=2048,sleep=0.05)
        finally:
            original.close()
            copy.close()
        c=sqlite3.connect(snapshot.resolve().as_uri()+'?mode=ro',uri=True,timeout=25)
        try:
            c.row_factory=sqlite3.Row
            c.execute('PRAGMA query_only=ON')
            c.execute('BEGIN')
            for t in (LEDGER,'skip_assets','skip_jobs','skip_schedule_focus','skip_parallel_focus',
                      'skip_language_priority','skip_catalogue_priority'):
                if not table_exists(c,t):
                    raise RuntimeError('Required scheduler table absent: '+t)
            print('EPISCENE SCHEDULER REQUEST SIMULATION / NUR LESEN')
            print('Live scheduler SHA256:',sha)
            print('Uses real select_job source and SQLite queries, but simulated requests only.')
            print('Does NOT evaluate production requests, provider access, or actual worker selection.')
            base=simulation_fn(fn,lambda _con,_stage: [])
            for pid,name in ((8,'4K ANALYSE'),(10,'THE BEST')):
                print('\\n'+name)
                row=c.execute("""SELECT l.asset_key,a.source_key,a.season,j.status,j.attempts
                           FROM episcene_audio_cache_canary_v1 l
                           JOIN skip_assets a ON a.asset_key=l.asset_key
                           LEFT JOIN skip_jobs j ON j.asset_key=l.asset_key
                           WHERE l.playlist_id=? ORDER BY l.queued_at DESC LIMIT 1""",(pid,)).fetchone()
                if row is None:
                    print('  status: no canary ledger')
                    continue
                print('  canary_queued:',row['status']=='queued')
                if row['status']!='queued' or row['attempts'] is None or row['attempts']>=3:
                    print('  status: ineligible for request simulation; no changes')
                    continue
                # Simulate the existing high-priority request path, WITHOUT
                # writing to the production request table.
                request={'playlist_id':pid,'source_key':row['source_key'],
                         'season':row['season'],'reference_asset':row['asset_key'],
                         'reason':'audio_cache_recovery'}
                override=simulation_fn(fn,lambda _con,_stage:[request])
                try:
                    baseline,_=base(c,pid,stage=2,parallel=True)
                    preferred,_=override(c,pid,stage=2,parallel=True)
                except sqlite3.Error as e:
                    raise RuntimeError('Scheduler query failed in read-only simulation: '+str(e))
                print('  focus_free_initial_selection_is_canary:',
                      baseline is not None and baseline['asset_key']==row['asset_key'])
                print('  synthetic_request_selects_exact_canary:',
                      preferred is not None and preferred['asset_key']==row['asset_key'])
                print('  request_selects_some_job:',preferred is not None)
            matching=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='request_series']
            print('\\nrequest_series_function_present:',len(matching)==1)
            if len(matching)==1:
                print('request_series_argument_names:',
                      ','.join(a.arg for a in matching[0].args.args))
            print('READ_ONLY: NO REQUEST CREATED; NO JOB CHANGED; NO WORKER RESTARTED')
        finally:
            c.close()


if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError,sqlite3.Error,SyntaxError) as e:
        print('SIMULATION_STOP:',type(e).__name__,str(e)[:200])
        raise SystemExit(1)
