#!/usr/bin/env python3
"""One-time, guarded EpiScene *scheduler request* for the 4K audio canary.

No worker imports, code patches, media access, job edits, approvals or restarts.
Only if the current scheduler SELECTs the exact queued canary after an
isolated SQLite-snapshot simulation, insert ONE time-limited request.
If any competing same-series request exists or the scheduler changed, STOP.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time

DB=Path('/var/lib/epimediahub/provisioning.db')
SOURCE=Path('/opt/epimediahub/provisioning/skip_schedule.py')
EXPECTED_SCHEDULER_SHA16='8dd4abe50f38f4da'
LEDGER='episcene_audio_cache_canary_v1'
REASON='audio_cache_recovery'
TTL_SECONDS=7200
PID=8

def fail(why):
    raise RuntimeError(why)

def fields(db,table):
    found=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
    if not found:fail('Missing table '+table)
    return {x[1] for x in db.execute('PRAGMA table_info('+table+')')}

def check_schema(db):
    for name,required in {
        LEDGER:{'asset_key','playlist_id'},
        'skip_jobs':{'asset_key','status','attempts','id'},
        'skip_assets':{'asset_key','playlist_id','source_key','season','episode','media_type'},
        'skip_analysis_sources':{'playlist_id','enabled'},
        'skip_analysis_playlists':{'id','archived'},
        'skip_auto_settings':{'playlist_id','enabled'},
        'skip_schedule_requests':{'playlist_id','source_key','season','episode','reference_asset','reason','requested_at','expires_at'}
    }.items():
        if not required<=fields(db,name):fail('Unrecognized schema: '+name)
    unique=False
    for row in db.execute("PRAGMA index_list('skip_schedule_requests')"):
        if row[2]:
            colnames=[v[2] for v in db.execute("PRAGMA index_info('"+row[1].replace("'","''")+"')")]
            if len(colnames)==2 and set(colnames)=={'playlist_id','source_key'}:
                unique=True
    if not unique:fail('No matching unique request key; will not touch live DB')

def code_selector():
    if not SOURCE.is_file() or SOURCE.is_symlink():
        fail('Scheduler file missing or symlink')
    src=SOURCE.read_bytes()
    sha=hashlib.sha256(src).hexdigest()[:16]
    if sha!=EXPECTED_SCHEDULER_SHA16:
        fail('Live scheduler changed since inspected SHA: '+sha)
    tree=ast.parse(src.decode('utf-8'),filename=str(SOURCE))
    names={}
    for name in ('select_job','requests'):
        match=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name]
        if len(match)!=1:fail('Expected one '+name+' function')
        names[name]=match[0]
        for node in ast.walk(match[0]):
            if isinstance(node,(ast.Import,ast.ImportFrom,ast.Global,ast.Nonlocal,
                                ast.AsyncFunctionDef,ast.With,ast.AsyncWith)):
                fail('Unsupported scheduler source side effect')
            if isinstance(node,ast.Call):
                x=node.func
                if isinstance(x,ast.Name) and x.id not in ('requests','language_stage','tuple','next','int'):
                    fail('Unexpected function in scheduler source')
                if isinstance(x,ast.Attribute) and x.attr not in ('execute','fetchone','fetchall','join','time'):
                    fail('Unexpected method in scheduler source')
            if isinstance(node,ast.Constant) and isinstance(node.value,str):
                if re.search(r'\b(INSERT|UPDATE|DELETE|REPLACE|ALTER|DROP|ATTACH|DETACH|VACUUM|PRAGMA)\b',
                             node.value,re.I):
                    fail('Unexpected SQL modification in scheduler code')
    mod=ast.Module(body=[names['requests'],names['select_job']],type_ignores=[])
    ast.fix_missing_locations(mod)
    env={'__builtins__':{'tuple':tuple,'next':next,'int':int},'time':time,
         'language_stage':lambda con:2}
    exec(compile(mod,'<episcene_scheduler_only>','exec'),env,env)
    return sha,env['requests'],env['select_job']

def canary(db):
    row=db.execute("""SELECT l.asset_key,a.source_key,a.season,a.episode,j.status,j.attempts
        FROM episcene_audio_cache_canary_v1 l
        JOIN skip_assets a ON a.asset_key=l.asset_key
        JOIN skip_jobs j ON j.asset_key=l.asset_key
        WHERE l.playlist_id=? AND a.playlist_id=? AND a.media_type='episode'
        ORDER BY l.queued_at""",(PID,PID)).fetchall()
    if len(row)!=1:fail('Expected exactly one recorded canary')
    r=row[0]
    if r['status']!='queued' or r['attempts'] is None or not 0<=r['attempts']<3:
        fail('Canary is not an eligible queued job')
    source=db.execute("SELECT enabled FROM skip_analysis_sources WHERE playlist_id=?",(PID,)).fetchone()
    auto=db.execute("SELECT enabled FROM skip_auto_settings WHERE playlist_id=?",(PID,)).fetchone()
    playlist=db.execute("SELECT archived FROM skip_analysis_playlists WHERE id=?",(PID,)).fetchone()
    if not source or source['enabled']!=1 or not auto or auto['enabled']!=1 or not playlist or playlist['archived']!=0:
        fail('Analysis source no longer enabled')
    current=db.execute("SELECT 1 FROM skip_schedule_requests WHERE playlist_id=? AND source_key=? LIMIT 1",
                       (PID,r['source_key'])).fetchone()
    if current:fail('Another request for this series exists; do not overwrite')
    return r

def insert_request(db,r,now):
    db.execute("""INSERT INTO skip_schedule_requests
        (playlist_id,source_key,season,episode,reference_asset,reason,requested_at,expires_at)
        VALUES(?,?,?,?,?,?,?,?)""",
        (PID,r['source_key'],r['season'],r['episode'],'',REASON,now,now+TTL_SECONDS))

def validate_selected(db,requests,select_job,asset):
    requested=requests(db,2)
    if not requested:
        fail('Scheduler does not recognize any stage-2 request')
    # A peer request for the same series may be present but cannot be allowed
    # to override manual/reference requests or higher-ranked priority groups.
    if requested[0]['reason']!=REASON:
        fail('An existing higher-priority schedule request must not be displaced')
    selected,where=select_job(db,PID,stage=2,parallel=True)
    if selected is None or selected['asset_key']!=asset:
        fail('Real request queue does not select exact German canary')
    return where

def main():
    parser=argparse.ArgumentParser()
    g=parser.add_mutually_exclusive_group()
    g.add_argument('--plan',action='store_true')
    g.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not DB.is_file() or DB.is_symlink():fail('Original database missing or symlink')
    sha,requester,selector=code_selector()
    if shutil.disk_usage('/tmp').free<DB.stat().st_size*2:
        fail('Not enough free space to make safe SQLite simulation snapshot')
    with tempfile.TemporaryDirectory(prefix='episcene-recovery-request-') as folder:
        snapshot=Path(folder)/'snapshot.db'
        src=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=60)
        dst=sqlite3.connect(str(snapshot),timeout=60)
        try:
            src.execute('PRAGMA query_only=ON')
            src.backup(dst,pages=2048,sleep=.05)
        finally:
            src.close();dst.close()
        sim=sqlite3.connect(snapshot,timeout=30)
        sim.row_factory=sqlite3.Row
        try:
            sim.execute('BEGIN IMMEDIATE')
            check_schema(sim)
            row=canary(sim)
            now=int(time.time())
            insert_request(sim,row,now)
            stage=validate_selected(sim,requester,selector,row['asset_key'])
            sim.rollback()
        finally:
            sim.close()
        print('SIMULATION_OK: German canary selected with existing request mechanism')
        print('SCHEDULER_SHA16:',sha)
        print('REQUEST_REASON:',REASON)
        print('REQUEST_TTL_HOURS:',TTL_SECONDS//3600)
        if not args.apply:
            print('PLAN_ONLY: production not modified')
            return
        # Short live transaction. No edits other than ONE request in its
        # existing request table. Recheck queue state and collisions.
        live=sqlite3.connect(DB,timeout=25)
        live.row_factory=sqlite3.Row
        try:
            live.execute('BEGIN IMMEDIATE')
            check_schema(live)
            live_row=canary(live)
            if live_row['asset_key']!=row['asset_key']:
                fail('Canary identity changed during simulation')
            insert_request(live,live_row,int(time.time()))
            validate_selected(live,requester,selector,live_row['asset_key'])
            live.commit()
            print('REQUEST_COMMITTED: one time-limited 4K ANALYSE series request')
            print('NO JOB RESET; NO MARKER APPROVAL; NO WORKER RESTART')
            print('Normal worker/scheduler will decide when next processing occurs')
        except Exception:
            live.rollback()
            raise
        finally:
            live.close()

if __name__=='__main__':
    try:main()
    except (RuntimeError,sqlite3.Error,OSError,ValueError,SyntaxError) as e:
        print('REQUEST_STOP:',type(e).__name__,str(e)[:180])
        raise SystemExit(1)
