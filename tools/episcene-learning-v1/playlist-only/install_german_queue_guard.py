#!/usr/bin/env python3
"""Guarded 4K DE-only queue deployment for mixed-language Xtream source ID 8.

This is a narrow, reversible queue-scope release. No client playlist changes,
no marker approvals, and no changes to Python production modules. It uses
provider category+episode linkage AND independently compares the exact asset
set with the previously verified legacy rank-0 set. All discrepancies stop
before mutation. Existing queued foreign/unknown 4K jobs become language_hold;
SQLite triggers prevent automated requeueing from defeating the guard.
THE BEST (ID 10) is not edited.

It is NOT a fix for visual evidence, analyzer timeouts or auto approvals.
"""
from __future__ import annotations
import argparse
import fcntl
import os
import shutil
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

ROOT=Path('/opt/epimediahub/provisioning')
DATA=Path('/var/lib/epimediahub')
DB=DATA/'provisioning.db'
BACKUPS=DATA/'episcene-4k-scope-backups'
LOCK=DATA/'.episcene-4k-scope-install.lock'
WORKER_LOCK=DATA/'skip-analysis.lock'
TIMER='epimediahub-skip-analysis.timer'
ANALYSIS='epimediahub-skip-analysis.service'
DE=re.compile(r'(?i)(?:^|[^a-z0-9])(?:de|deu|deutsch(?:e)?|german)(?:$|[^a-z0-9])')
NON_DE=re.compile(r'(?i)(?:^|[^a-z0-9])(?:it|ita|ital(?:iano|iana|ian)?|tr|turk(?:ish|ce)?|en|english|fr|french|ar|arab(?:ic)?|es|spanish|gr|greek)(?:$|[^a-z0-9])')
PREFIX='episcene_scope_4k_'
HOLD='language_hold'


def systemctl(action,unit):
    proc=subprocess.run(['systemctl',action,unit],capture_output=True,text=True,timeout=30)
    if proc.returncode:
        raise RuntimeError('systemctl '+action+' failed for '+unit)
    return proc.stdout.strip()


def active(unit):
    proc=subprocess.run(['systemctl','show',unit,'-p','ActiveState','--value'],
                        capture_output=True,text=True,timeout=8)
    if proc.returncode:
        raise RuntimeError('Cannot inspect '+unit)
    state=proc.stdout.strip()
    if state in ('active','activating','reloading','deactivating'):
        return True
    if state in ('inactive','failed'):
        return False
    raise RuntimeError('Unexpected '+unit+' state')


def category_class(name):
    if not isinstance(name,str):
        return 'unknown'
    german=bool(DE.search(name))
    other=bool(NON_DE.search(name))
    return 'de' if german and not other else 'mixed' if german else 'other'


def german_series(categories,series):
    if not isinstance(categories,list) or not isinstance(series,list) or len(categories)>30000 or len(series)>240000:
        raise RuntimeError('Invalid Xtream response size/type')
    mapping={}
    conflicted=set()
    for row in categories:
        if not isinstance(row,dict) or row.get('category_id') is None:continue
        cid=str(row['category_id'])
        cls=category_class(row.get('category_name'))
        if cid in mapping and mapping[cid]!=cls:
            conflicted.add(cid)
        mapping[cid]=cls
    allowed=set()
    seen={}
    changed=set()
    for row in series:
        if not isinstance(row,dict) or row.get('series_id') is None:continue
        sid=str(row['series_id'])
        if not sid.isdecimal() or len(sid)>20:
            continue
        cids=row.get('category_id')
        if isinstance(cids,(tuple,list)):
            decisions=[str(c) in mapping and str(c) not in conflicted and mapping[str(c)]=='de' for c in cids]
            accept=bool(decisions) and all(decisions)
        else:
            key=str(cids)
            accept=key in mapping and key not in conflicted and mapping[key]=='de'
        if sid in seen and seen[sid]!=accept:
            changed.add(sid)
        seen[sid]=accept
    for sid,ok in seen.items():
        if ok and sid not in changed:
            allowed.add(sid)
    return allowed,{'categories':len(categories),'series':len(series),
                     'de_series':len(allowed),'conflicting_series':len(changed)}


def assets_for_series(db,series_ids):
    if not series_ids:
        raise RuntimeError('No unambiguous German series')
    out=set()
    series_ids=sorted(series_ids)
    for ix in range(0,len(series_ids),300):
        ids=series_ids[ix:ix+300]
        rows=db.execute(
            'SELECT DISTINCT e.asset_key FROM skip_catalogue_episodes e '
            'JOIN skip_assets a ON a.asset_key=e.asset_key '
            'WHERE e.playlist_id=8 AND a.playlist_id=8 AND a.media_type=\'episode\' '
            'AND e.series_id IN ('+','.join('?' for _ in ids)+')',ids)
        out.update(k for (k,) in rows)
    return out


def verify_database(db,scope,*,minimum=100):
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    needed={'skip_assets','skip_jobs','skip_catalogue_episodes',
            'skip_language_priority','skip_analysis_playlists','skip_analysis_sources'}
    if needed-tables:
        raise RuntimeError('Missing required EpiScene tables')
    if db.execute("SELECT COUNT(*) FROM skip_analysis_playlists WHERE id=8 AND archived=0").fetchone()[0]!=1:
        raise RuntimeError('4K independent analysis source disabled')
    if db.execute('SELECT COUNT(*) FROM skip_analysis_sources WHERE playlist_id=8 AND enabled=1').fetchone()[0]!=1:
        raise RuntimeError('4K analysis source not enabled')
    ranked={row[0] for row in db.execute("""
        SELECT a.asset_key FROM skip_assets a JOIN skip_language_priority l
        ON l.asset_key=a.asset_key
        WHERE a.playlist_id=8 AND a.media_type='episode' AND l.priority=0
    """)}
    only_old=len(ranked-scope)
    only_new=len(scope-ranked)
    if only_old or only_new or len(scope)<minimum:
        raise RuntimeError('Category-vs-priority asset mismatch: old_only='+str(only_old)+
                           ',new_only='+str(only_new)+'. No changes made.')
    return {'category_mapped_episodes':len(scope),
            'rank0_episodes':len(ranked),
            'old_only':only_old,'new_only':only_new,
            'queued_other_before':db.execute("""
                SELECT COUNT(*) FROM skip_jobs j JOIN skip_assets a USING(asset_key)
                WHERE a.playlist_id=8 AND j.status='queued'
            """).fetchone()[0]-sum(1 for x in db.execute("""
                SELECT j.asset_key FROM skip_jobs j JOIN skip_assets a USING(asset_key)
                WHERE a.playlist_id=8 AND j.status='queued'
            """) if x[0] in scope)}


def source_catalogue(db):
    # Import existing EpiScene authenticated provider client. Never log the
    # provider URL, credentials or any raw provider data.
    sys.path.insert(0,str(ROOT))
    from skip_automation import provider_api
    db.row_factory=sqlite3.Row
    row=db.execute('SELECT * FROM skip_analysis_playlists WHERE id=8 AND archived=0').fetchone()
    if row is None:
        raise RuntimeError('Independent 4K source does not exist')
    playlist=dict(row)
    categories=provider_api(playlist,'get_series_categories',lambda:False)
    series=provider_api(playlist,'get_series',lambda:False,_limit=24000000)
    return german_series(categories,series)


def make_backup():
    if BACKUPS.is_symlink() or DB.is_symlink():
        raise RuntimeError('Unexpected backup or database symlink')
    BACKUPS.mkdir(mode=0o700,exist_ok=True)
    os.chmod(BACKUPS,0o700)
    free=shutil.disk_usage(BACKUPS).free
    needed=int(DB.stat().st_size*1.5)+256*1024*1024
    if free<needed:
        raise RuntimeError('Insufficient free space for verified SQLite backup')
    dest=BACKUPS/('pre-4k-scope-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+str(os.getpid())+'.sqlite3')
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=40) as old:
        with sqlite3.connect(dest,timeout=40) as snapshot:
            old.backup(snapshot,pages=300)
            if snapshot.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                raise RuntimeError('DB backup integrity check failed')
    os.chmod(dest,0o600)
    return dest


def apply_guard(db,scope,*,minimum=100):
    db.execute('BEGIN IMMEDIATE')
    try:
        # Recheck against a locked, current DB snapshot after the worker has
        # drained: the catalogue may have changed while waiting.
        verify_database(db,scope,minimum=minimum)
        best_before=dict(db.execute("""
            SELECT j.status,COUNT(*) FROM skip_jobs j JOIN skip_assets a USING(asset_key)
            WHERE a.playlist_id=10 GROUP BY j.status
        """))
        objects={name for (name,) in db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'episcene_scope_4k_%'")}
        if objects:
            raise RuntimeError('EpiScene 4K scope objects already exist, refusing duplicate install')
        db.execute('CREATE TABLE episcene_scope_4k_allowed(asset_key TEXT PRIMARY KEY)')
        db.execute('CREATE TABLE episcene_scope_4k_held(asset_key TEXT PRIMARY KEY,previous_status TEXT NOT NULL)')
        db.executemany('INSERT INTO episcene_scope_4k_allowed(asset_key) VALUES(?)',((key,) for key in scope))
        # Ledger records only queued jobs; completed and in-progress work is untouched.
        db.execute("""
            INSERT INTO episcene_scope_4k_held(asset_key,previous_status)
            SELECT j.asset_key,j.status FROM skip_jobs j JOIN skip_assets a USING(asset_key)
            WHERE a.playlist_id=8 AND j.status='queued' AND NOT EXISTS
              (SELECT 1 FROM episcene_scope_4k_allowed v WHERE v.asset_key=j.asset_key)
        """)
        db.execute("""
            UPDATE skip_jobs SET status='language_hold'
            WHERE status='queued' AND asset_key IN
              (SELECT j.asset_key FROM skip_jobs j JOIN skip_assets a USING(asset_key)
               WHERE a.playlist_id=8 AND NOT EXISTS
                 (SELECT 1 FROM episcene_scope_4k_allowed v WHERE v.asset_key=j.asset_key))
        """)
        # All code paths, including analysis learning/requeue, are caught.
        db.execute("""
            CREATE TRIGGER episcene_scope_4k_insert AFTER INSERT ON skip_jobs
            WHEN NEW.status='queued' AND EXISTS(
                SELECT 1 FROM skip_assets a WHERE a.asset_key=NEW.asset_key AND a.playlist_id=8)
              AND NOT EXISTS(SELECT 1 FROM episcene_scope_4k_allowed v WHERE v.asset_key=NEW.asset_key)
            BEGIN
                INSERT OR IGNORE INTO episcene_scope_4k_held(asset_key,previous_status)
                VALUES(NEW.asset_key,'queued');
                UPDATE skip_jobs SET status='language_hold' WHERE asset_key=NEW.asset_key;
            END
        """)
        db.execute("""
            CREATE TRIGGER episcene_scope_4k_requeue AFTER UPDATE OF status ON skip_jobs
            WHEN NEW.status='queued' AND EXISTS(
                SELECT 1 FROM skip_assets a WHERE a.asset_key=NEW.asset_key AND a.playlist_id=8)
              AND NOT EXISTS(SELECT 1 FROM episcene_scope_4k_allowed v WHERE v.asset_key=NEW.asset_key)
            BEGIN
                INSERT OR IGNORE INTO episcene_scope_4k_held(asset_key,previous_status)
                VALUES(NEW.asset_key,'queued');
                UPDATE skip_jobs SET status='language_hold' WHERE asset_key=NEW.asset_key;
            END
        """)
        db.execute("""
            CREATE TRIGGER episcene_scope_4k_asset_move AFTER UPDATE OF playlist_id ON skip_assets
            WHEN NEW.playlist_id=8 AND NOT EXISTS(
                SELECT 1 FROM episcene_scope_4k_allowed v WHERE v.asset_key=NEW.asset_key)
            BEGIN
                INSERT OR IGNORE INTO episcene_scope_4k_held(asset_key,previous_status)
                SELECT j.asset_key,'queued' FROM skip_jobs j
                WHERE j.asset_key=NEW.asset_key AND j.status='queued';
                UPDATE skip_jobs SET status='language_hold'
                WHERE asset_key=NEW.asset_key AND status='queued';
            END
        """)
        db.execute("""
            CREATE TRIGGER episcene_scope_4k_asset_insert AFTER INSERT ON skip_assets
            WHEN NEW.playlist_id=8 AND NOT EXISTS(
                SELECT 1 FROM episcene_scope_4k_allowed v WHERE v.asset_key=NEW.asset_key)
            BEGIN
                INSERT OR IGNORE INTO episcene_scope_4k_held(asset_key,previous_status)
                SELECT j.asset_key,'queued' FROM skip_jobs j
                WHERE j.asset_key=NEW.asset_key AND j.status='queued';
                UPDATE skip_jobs SET status='language_hold'
                WHERE asset_key=NEW.asset_key AND status='queued';
            END
        """)
        left=db.execute("""
           SELECT COUNT(*) FROM skip_jobs j JOIN skip_assets a USING(asset_key)
           WHERE a.playlist_id=8 AND j.status='queued'
             AND NOT EXISTS(SELECT 1 FROM episcene_scope_4k_allowed v WHERE v.asset_key=j.asset_key)
        """).fetchone()[0]
        if left:
            raise RuntimeError('Post-install queued foreign count '+str(left))
        held=db.execute('SELECT COUNT(*) FROM episcene_scope_4k_held').fetchone()[0]
        best_after=dict(db.execute("""
            SELECT j.status,COUNT(*) FROM skip_jobs j JOIN skip_assets a USING(asset_key)
            WHERE a.playlist_id=10 GROUP BY j.status
        """))
        if best_before!=best_after:
            raise RuntimeError('THE BEST was unexpectedly modified')
        db.commit()
        return held
    except BaseException:
        db.rollback()
        raise


def rollback_guard(db):
    db.execute('BEGIN IMMEDIATE')
    try:
        present={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'episcene_scope_4k_%'")}
        required={'episcene_scope_4k_allowed','episcene_scope_4k_held',
                  'episcene_scope_4k_insert','episcene_scope_4k_requeue',
                  'episcene_scope_4k_asset_move','episcene_scope_4k_asset_insert'}
        if not required<=present:
            raise RuntimeError('Incomplete EpiScene guard; refusing partial rollback')
        for name in sorted(required):
            if name.endswith(('_insert','_requeue','_asset_move')):
                db.execute('DROP TRIGGER '+name)
        db.execute("""
            UPDATE skip_jobs SET status='queued'
            WHERE status='language_hold' AND asset_key IN
              (SELECT asset_key FROM episcene_scope_4k_held WHERE previous_status='queued')
        """)
        restored=db.execute('SELECT changes()').fetchone()[0]
        db.execute('DROP TABLE episcene_scope_4k_held')
        db.execute('DROP TABLE episcene_scope_4k_allowed')
        db.commit()
        return restored
    except BaseException:
        db.rollback()
        raise


def guarded_maintenance(task,scope=None):
    if os.geteuid()!=0:
        raise RuntimeError('Run as root')
    if DB.is_symlink() or not DB.is_file() or LOCK.is_symlink() or WORKER_LOCK.is_symlink():
        raise RuntimeError('Unexpected production path')
    if not active(TIMER):
        raise RuntimeError('Analysis timer is not active')
    if (DATA/'episcene-visual-peer-reload-pending').exists():
        raise RuntimeError('Scene reload pending; do not overlap maintenance')
    with LOCK.open('a') as runlock:
        fcntl.flock(runlock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        backup=make_backup()
        print('DB BACKUP VERIFIED: '+str(backup),flush=True)
        stopped=False
        try:
            systemctl('stop',TIMER)
            stopped=True
            deadline=time.monotonic()+540
            lock=None
            while time.monotonic()<deadline:
                if not active(ANALYSIS) and WORKER_LOCK.is_file():
                    lock=WORKER_LOCK.open('rb')
                    try:
                        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                        if not active(ANALYSIS):
                            break
                    except BlockingIOError:
                        pass
                    lock.close()
                    lock=None
                time.sleep(3)
            if lock is None:
                raise RuntimeError('Active analysis did not reach safe boundary in 9 min')
            try:
                with sqlite3.connect(DB,timeout=30) as db:
                    db.execute('PRAGMA busy_timeout=30000')
                    if task=='install':
                        held=apply_guard(db,scope)
                        print('GUARD ACTIVE. Held non-DE/unknown queued 4K jobs: '+str(held),flush=True)
                    else:
                        restored=rollback_guard(db)
                        print('GUARD ROLLED BACK. Restored queued jobs: '+str(restored),flush=True)
            finally:
                lock.close()
        finally:
            if stopped:
                systemctl('start',TIMER)
        if not active(TIMER):
            raise RuntimeError('Analysis timer not active after maintenance')
    print('THE BEST not changed; EpiScene marker records not changed.')


def main():
    p=argparse.ArgumentParser()
    modes=p.add_mutually_exclusive_group(required=True)
    modes.add_argument('--check',action='store_true')
    modes.add_argument('--apply',action='store_true')
    modes.add_argument('--rollback',action='store_true')
    args=p.parse_args()
    if args.rollback:
        guarded_maintenance('rollback')
        return
    if DB.is_symlink() or not DB.is_file():
        raise RuntimeError('Source DB unavailable')
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=25) as db:
        db.execute('PRAGMA query_only=ON')
        allowed_series,details=source_catalogue(db)
        scope=assets_for_series(db,allowed_series)
        evidence=verify_database(db,scope)
        print('PROVIDER SERIES: '+str(details),flush=True)
        print('4K SCOPE CHECK: '+str(evidence),flush=True)
    if args.check:
        print('PRECHECK OK – no changes made.')
        return
    guarded_maintenance('install',scope)


if __name__=='__main__':
    try:
        main()
    except (RuntimeError,OSError,sqlite3.Error,subprocess.SubprocessError,TypeError,ValueError) as error:
        print('SAFETY STOP: '+str(error),file=sys.stderr)
        raise SystemExit(2)
