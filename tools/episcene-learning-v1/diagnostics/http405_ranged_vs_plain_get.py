#!/usr/bin/env python3
"""One bounded, sequential comparison of ranged and plain GET for THE BEST.

Runs only against one recently failed *independent analysis* asset on the
analysis host. Uses production's pinned-IP, redirect-restricted proxy.
Pauses the analysis timer and respects its exclusive service lock.
NEVER exports URL, host, login, title, stream ID or exception detail.
No production DB writes, no marker changes, no FFmpeg, no customer streams.
"""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

APP=Path('/opt/epimediahub/analysis')
DB=Path('/var/lib/epimediahub/provisioning.db')
LOCK=Path('/var/lib/epimediahub/skip-analysis.lock')
TIMER='epimediahub-skip-analysis.timer'
SERVICE='epimediahub-skip-analysis.service'

def unit(*args):
    return subprocess.run(['systemctl',*args],check=False,
                          capture_output=True,text=True,timeout=12).returncode

def active(name):
    return unit('is-active','--quiet',name)==0

@contextmanager
def idle():
    if LOCK.is_symlink() or not LOCK.is_file():
        raise RuntimeError('STOP_ANALYSIS_LOCK_MISSING')
    timer_on=active(TIMER)
    if timer_on and unit('stop',TIMER)!=0:
        raise RuntimeError('STOP_TIMER_PAUSE_FAILED')
    try:
        with LOCK.open('rb') as handle:
            deadline=time.monotonic()+90
            while True:
                acquired=False
                try:
                    fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    acquired=True
                except BlockingIOError: pass
                if acquired and not active(SERVICE):break
                if acquired: fcntl.flock(handle,fcntl.LOCK_UN)
                if time.monotonic()>=deadline:
                    raise RuntimeError('STOP_WORKER_BUSY')
                time.sleep(2)
            try:yield
            finally:fcntl.flock(handle,fcntl.LOCK_UN)
    finally:
        if timer_on:
            print('TIMER_RESTORED' if unit('start',TIMER)==0
                  else 'WARNING_TIMER_RESTORE_FAILED')

def sample(db):
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    required={
        'skip_assets':{'asset_key','playlist_id','media_type','stream_id','extension'},
        'skip_jobs':{'asset_key','status','detail','updated_at'},
        'skip_analysis_playlists':{'id','archived','config_json'},
        'skip_analysis_sources':{'playlist_id','enabled'},
    }
    for table,columns in required.items():
        found={r[1] for r in db.execute('PRAGMA table_info('+table+')')}
        if not columns.issubset(found):
            raise RuntimeError('STOP_UNEXPECTED_DATABASE_SCHEMA')
    cutoff=(datetime.now(timezone.utc)-timedelta(hours=6)).isoformat(
        timespec='seconds')
    matches=db.execute("""
        SELECT a.* FROM skip_jobs j
        JOIN skip_assets a ON a.asset_key=j.asset_key
        JOIN skip_analysis_playlists p ON p.id=a.playlist_id
        JOIN skip_analysis_sources s ON s.playlist_id=p.id
        WHERE a.playlist_id=10 AND a.media_type='episode'
          AND p.archived=0 AND s.enabled=1
          AND j.status='failed' AND j.detail LIKE '%HTTP 405%'
          AND j.updated_at>=?
        ORDER BY j.updated_at DESC LIMIT 5
    """,(cutoff,)).fetchall()
    for asset in matches:
        if (re.fullmatch(r'[0-9]{1,12}',str(asset['stream_id'])) and
                asset['extension'] in ('mp4','mkv','m4v','avi','ts','mpeg','mpg')):
            playlist=db.execute('SELECT * FROM skip_analysis_playlists WHERE id=10').fetchone()
            return playlist,asset
    raise RuntimeError('STOP_NO_RECENT_ANALYSIS_405_ASSET')

def classify(exception):
    # Keep error details private, including any URL hidden in exception messages.
    code=str(exception) if type(exception).__name__=='ProviderFailure' else ''
    if re.fullmatch(r'provider_http_[1-5][0-9]{2}',code):
        return 'HTTP_'+code[-3:]
    if code in ('provider_timeout','provider_dns','provider_tls','provider_connection',
                'analysis_input_limit','unsafe_source'):
        return code.upper()
    return 'INCONCLUSIVE_'+type(exception).__name__.upper()

def probe(module,source,range_header):
    headers={'Range':'bytes=0-0'} if range_header else {}
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    value='INCONCLUSIVE'
    try:
        with module._provider_proxy_local(source,lambda:False) as relay:
            try:
                request=urllib.request.Request(relay,method='GET',headers=headers)
                with opener.open(request,timeout=8) as response:
                    code=response.status
                    # Close immediately after one byte; never download the file.
                    value='HTTP_'+str(code) if type(code) is int and 100<=code<=599 else 'INCONCLUSIVE_STATUS'
                    response.read(1)
            except urllib.error.HTTPError as exc:
                value='PROXY_HTTP_'+str(exc.code)
                exc.close()
    except Exception as exc:
        value=classify(exc)
    return value

def main():
    if APP.is_symlink() or not APP.is_dir() or DB.is_symlink() or not DB.is_file():
        raise RuntimeError('STOP_EXPECTED_INSTALLATION_MISSING')
    sys.path.insert(0,str(APP))
    import skip_analysis as analysis
    with idle():
        with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=10) as con:
            playlist,asset=sample(con)
            source=analysis.source_url(playlist,asset)
            if analysis.provider_asset_key(source,'episode')!=asset['asset_key']:
                raise RuntimeError('STOP_ASSET_IDENTITY_MISMATCH')
        ranged=probe(analysis,source,True)
        plain=probe(analysis,source,False)
    print('THE_BEST_SAME_EPISODE_GET_RANGE:',ranged)
    print('THE_BEST_SAME_EPISODE_GET_NO_RANGE:',plain)
    print('NO_DATABASE_OR_MARKER_CHANGES')
    if ranged=='HTTP_405' and plain in ('HTTP_200','HTTP_206'):
        print('RESULT: RANGE_INCOMPATIBILITY_CONFIRMED')
    elif ranged=='HTTP_405' and plain=='HTTP_405':
        print('RESULT: NOT_JUST_RANGE_METHOD_BLOCKED')
    else:
        print('RESULT: INCONCLUSIVE_OR_TRANSIENT_ACCESS')

if __name__=='__main__':
    try:main()
    except Exception as error:
        # Never print the exception text (may contain credentials or source).
        reason=str(error) if isinstance(error,RuntimeError) and str(error).startswith('STOP_') else 'UNEXPECTED_'+type(error).__name__
        print('SAFE_STOP:',reason)
        raise SystemExit(1)
