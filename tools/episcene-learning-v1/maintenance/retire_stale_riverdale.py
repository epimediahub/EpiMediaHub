#!/usr/bin/env python3
"""Retire only obsolete THE BEST Riverdale-series jobs, preserving all markers.

Requires a unique stored HTTP-405 Riverdale S7E6 anchor and a fresh, empty
get_series_info response for that exact historic series ID. Work is paused
at the scheduler lock and a verified full SQLite backup precedes one atomic
transaction. Other series, playlists, evidence and catalogue are untouched.
"""
from __future__ import annotations
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl, json, os, re, shutil, sqlite3, subprocess, sys, time
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path('/opt/epimediahub/provisioning')
DB=Path('/var/lib/epimediahub/provisioning.db')
LOCK=Path('/var/lib/epimediahub/skip-analysis.lock')
BACKUPS=Path('/var/backups/epimediahub/riverdale-stale-analysis')
TIMER='epimediahub-skip-analysis.timer'
SERVICE='epimediahub-skip-analysis.service'
STATUSES=('queued','failed','partial','review','no_match','no_reference')
NOTE='Deaktiviert: veraltete Riverdale-Serien-ID im THE-BEST-Analysekatalog'

def systemctl(*args):
    return subprocess.run(['systemctl',*args],capture_output=True,
                          text=True,timeout=15,check=False).returncode

def active(name):
    return systemctl('is-active','--quiet',name)==0

@contextmanager
def idle():
    if not LOCK.is_file() or LOCK.is_symlink():
        raise RuntimeError('STOP_ANALYSIS_LOCK_MISSING')
    prior=active(TIMER)
    if prior and systemctl('stop',TIMER):
        raise RuntimeError('STOP_CANNOT_PAUSE_TIMER')
    try:
        with LOCK.open('rb') as handle:
            deadline=time.monotonic()+900
            while True:
                acquired=False
                try:
                    fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    acquired=True
                except BlockingIOError:
                    pass
                if acquired and not active(SERVICE):
                    break
                if acquired:
                    fcntl.flock(handle,fcntl.LOCK_UN)
                if time.monotonic()>=deadline:
                    raise RuntimeError('STOP_ANALYSIS_BUSY')
                time.sleep(2)
            try: yield
            finally: fcntl.flock(handle,fcntl.LOCK_UN)
    finally:
        if prior:
            print('TIMER_RESTORED: active' if systemctl('start',TIMER)==0
                  else 'WARNING_TIMER_RESTORE_FAILED',flush=True)

def readonly():
    c=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=15)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    return c

def fields(con,table):
    return {r[1] for r in con.execute('PRAGMA table_info('+table+')')}

def plan(con):
    needed={
        'skip_assets':{'asset_key','playlist_id','season','episode','media_type','title'},
        'skip_catalogue_episodes':{'playlist_id','asset_key','series_id'},
        'skip_jobs':{'id','asset_key','status','detail','updated_at'}}
    for table,required in needed.items():
        if not required<=fields(con,table):
            raise RuntimeError('STOP_UNEXPECTED_DB_SCHEMA_'+table.upper())
    anchors=con.execute("""
      SELECT DISTINCT c.series_id FROM skip_jobs j
      JOIN skip_assets a ON a.asset_key=j.asset_key
      JOIN skip_catalogue_episodes c ON c.asset_key=a.asset_key
        AND c.playlist_id=a.playlist_id
      WHERE a.playlist_id=10 AND a.media_type='episode'
        AND a.season=7 AND a.episode=6
        AND lower(a.title) LIKE '%riverdale%'
        AND ((j.status='failed' AND j.detail LIKE '%HTTP 405%')
          OR (j.status='disabled' AND j.detail=?))
      LIMIT 4""",(NOTE,)).fetchall()
    if len(anchors)!=1:
        raise RuntimeError('STOP_OLD_RIVERDALE_SERIES_NOT_UNIQUE')
    sid=str(anchors[0][0])
    if not re.fullmatch(r'[1-9][0-9]{0,12}',sid):
        raise RuntimeError('STOP_INVALID_STALE_SERIES_ID')
    rows=con.execute("""
      SELECT DISTINCT j.id,j.status,a.asset_key,a.title
      FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
      JOIN skip_catalogue_episodes c ON c.asset_key=a.asset_key
        AND c.playlist_id=a.playlist_id
      WHERE a.playlist_id=10 AND a.media_type='episode'
        AND CAST(c.series_id AS TEXT)=?
      ORDER BY j.id LIMIT 222""",(sid,)).fetchall()
    if not rows or len(rows)>220:
        raise RuntimeError('STOP_UNEXPECTED_RIVERDALE_SERIES_SIZE')
    if any('riverdale' not in str(r['title'] or '').casefold() for r in rows):
        raise RuntimeError('STOP_STALE_ID_SHARED_WITH_OTHER_TITLE')
    if any(r['status']=='running' for r in rows):
        raise RuntimeError('STOP_SERIES_JOB_RUNNING')
    asset_keys={r['asset_key'] for r in rows}
    placeholders=','.join('?' for _ in asset_keys)
    # One asset must not simultaneously belong to another (possibly Italian)
    # series. An ambiguous catalogue mapping blocks the entire cleanup.
    ambiguous=con.execute("""
      SELECT 1 FROM skip_catalogue_episodes
      WHERE playlist_id=10 AND asset_key IN ("""+placeholders+""")
        AND CAST(series_id AS TEXT)<>? LIMIT 1""",(*sorted(asset_keys),sid)).fetchone()
    if ambiguous:
        raise RuntimeError('STOP_ASSET_MAPPED_TO_MULTIPLE_LANGUAGE_SERIES')
    ids=[int(r['id']) for r in rows if r['status'] in STATUSES]
    return sid,ids,dict(Counter(r['status'] for r in rows))

def verify_absent(config,series_id,analysis):
    base=config['xtream_server'].rstrip('/')
    if urllib.parse.urlsplit(base).path not in ('','/'):
        raise RuntimeError('STOP_UNEXPECTED_SERVER_ROOT')
    params=urllib.parse.urlencode({
        'username':config['xtream_username'],
        'password':config['xtream_password'],
        'action':'get_series_info','series_id':series_id})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with analysis._provider_proxy_local(base+'/player_api.php?'+params,
                                            lambda:False) as relay:
            with opener.open(urllib.request.Request(relay,method='GET'),timeout=12) as response:
                if response.status!=200:
                    raise RuntimeError('STOP_PROVIDER_METADATA_NOT_200')
                raw=response.read(65537)
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,OSError):
        raise RuntimeError('STOP_PROVIDER_METADATA_UNAVAILABLE') from None
    if len(raw)>65536:
        raise RuntimeError('STOP_PROVIDER_METADATA_TOO_LARGE')
    try: value=json.loads(raw)
    except (ValueError,UnicodeError):
        raise RuntimeError('STOP_PROVIDER_METADATA_NOT_JSON') from None
    return value==[]

def backup():
    if DB.is_symlink() or not DB.is_file() or BACKUPS.is_symlink():
        raise RuntimeError('STOP_UNSAFE_DB_OR_BACKUP_PATH')
    BACKUPS.mkdir(parents=True,exist_ok=True,mode=0o700)
    BACKUPS.chmod(0o700)
    if shutil.disk_usage(BACKUPS).free<2*DB.stat().st_size+64*1024*1024:
        raise RuntimeError('STOP_NOT_ENOUGH_BACKUP_SPACE')
    name=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+str(os.getpid())+'.sqlite3'
    path=BACKUPS/name
    if path.exists() or path.is_symlink():
        raise RuntimeError('STOP_BACKUP_NAME_ALREADY_USED')
    try:
        with readonly() as source:
            with sqlite3.connect(path) as target:
                source.backup(target,pages=128,sleep=0.05)
                if target.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                    raise RuntimeError('STOP_BACKUP_INTEGRITY')
        path.chmod(0o600)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path

def apply(con,series_id,preselected):
    con.execute('PRAGMA busy_timeout=10000')
    con.execute('BEGIN IMMEDIATE')
    try:
        actual,ids,_=plan(con)
        if actual!=series_id or ids!=preselected:
            raise RuntimeError('STOP_TARGET_CHANGED')
        if ids:
            placeholders=','.join('?' for _ in ids)
            changed=con.execute("""
              UPDATE skip_jobs SET status='disabled',detail=?,updated_at=?
              WHERE id IN ("""+placeholders+""")
                AND status IN ('queued','failed','partial','review',
                               'no_match','no_reference')""",
              (NOTE,datetime.now(timezone.utc).isoformat(timespec='seconds'),*ids)).rowcount
            if changed!=len(ids):
                raise RuntimeError('STOP_UNEXPECTED_CHANGED_ROW_COUNT')
        con.commit()
        return len(ids)
    except Exception:
        con.rollback()
        raise

def main():
    if os.geteuid()!=0 or ROOT.is_symlink() or not ROOT.is_dir() or DB.is_symlink() or not DB.is_file():
        raise RuntimeError('STOP_EXPECTED_ROOT_ANALYSIS_INSTALL_MISSING')
    sys.path.insert(0,str(ROOT))
    import skip_analysis as analysis
    from skip_analysis_accounts import using
    with idle():
        with readonly() as con:
            sid,ids,states=plan(con)
            print('OLD_RIVERDALE_STATES:',json.dumps(states,sort_keys=True),flush=True)
            print('JOBS_TO_DISABLE:',len(ids),flush=True)
        if not ids:
            print('ALREADY_CLEAN: old Riverdale jobs are outside the active queue')
            return
        with using(readonly):
            with readonly() as con:
                line=con.execute('SELECT * FROM skip_analysis_playlists WHERE id=10 AND archived=0').fetchone()
                if line is None:
                    raise RuntimeError('STOP_ANALYSIS_LINE_UNAVAILABLE')
                config=analysis.configured_source(line)
            if not verify_absent(config,sid,analysis):
                raise RuntimeError('STOP_OLD_RIVERDALE_SERIES_IS_STILL_ACTIVE')
        print('OLD_SERIES_CONFIRMED_ABSENT',flush=True)
        saved=backup()
        print('BACKUP_OK:',saved,flush=True)
        with sqlite3.connect(DB,timeout=15) as con:
            con.row_factory=sqlite3.Row
            changed=apply(con,sid,ids)
        print('CLEANUP_OK:',changed,'old Riverdale jobs disabled')
        print('ITALIAN_SERIES_AND_4K_UNCHANGED')
        print('MARKERS_CATALOGUE_AND_VISUAL_CACHE_UNCHANGED')

if __name__=='__main__':
    try: main()
    except Exception as error:
        safe=(str(error) if isinstance(error,RuntimeError) and
              str(error).startswith('STOP_') else 'STOP_UNEXPECTED_'+type(error).__name__)
        print('SAFE_STOP:',safe)
        raise SystemExit(1)
