#!/usr/bin/env python3
"""Read-only THE BEST Xtream current-series lookup for Riverdale S07E06.

Queries only the dedicated analysis credentials (playlist 10), without
opening video, changing jobs, replacing IDs, or disclosing credentials.
Title matches are only discovery candidates, NOT verified episode/cut identity.
"""
from __future__ import annotations
import fcntl
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager

DB=Path('/var/lib/epimediahub/provisioning.db')
APP=Path('/opt/epimediahub/provisioning')
LOCK=Path('/var/lib/epimediahub/skip-analysis.lock')
TIMER='epimediahub-skip-analysis.timer'
SERVICE='epimediahub-skip-analysis.service'
MAX_BODY=6*1024*1024

def systemctl(*args):
    return subprocess.run(['systemctl',*args],capture_output=True,text=True,
                          timeout=15,check=False).returncode

def is_active(name):
    return systemctl('is-active','--quiet',name)==0

@contextmanager
def exclusive_idle():
    if LOCK.is_symlink() or not LOCK.is_file():
        raise RuntimeError('STOP_ANALYSIS_LOCK_MISSING')
    timer_active=is_active(TIMER)
    if timer_active and systemctl('stop',TIMER)!=0:
        raise RuntimeError('STOP_TIMER_PAUSE_FAILED')
    try:
        with LOCK.open('rb') as handle:
            deadline=time.monotonic()+180
            while True:
                acquired=False
                try:
                    fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    acquired=True
                except BlockingIOError:
                    pass
                if acquired and not is_active(SERVICE):
                    break
                if acquired:
                    fcntl.flock(handle,fcntl.LOCK_UN)
                if time.monotonic()>deadline:
                    raise RuntimeError('STOP_ANALYSIS_BUSY_NO_API_REQUEST')
                time.sleep(2)
            try:
                yield
            finally:
                fcntl.flock(handle,fcntl.LOCK_UN)
    finally:
        if timer_active:
            print('TIMER_RESTORED' if systemctl('start',TIMER)==0
                  else 'WARNING_TIMER_RESTORE_FAILED')

@contextmanager
def read_only_db():
    if DB.is_symlink() or not DB.is_file():
        raise RuntimeError('STOP_ANALYSIS_DB_MISSING')
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=10) as db:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        yield db

def local_episode(db):
    return db.execute("""SELECT a.* FROM skip_assets a JOIN skip_jobs j
      ON a.asset_key=j.asset_key
      WHERE a.playlist_id=10 AND a.media_type='episode'
        AND lower(trim(a.title)) LIKE '%riverdale%'
        AND a.season=7 AND a.episode=6
        AND j.status='failed' AND j.detail LIKE '%HTTP 405%'
      ORDER BY j.updated_at DESC LIMIT 1""").fetchone()

def known_series(db,asset):
    rows=db.execute("""SELECT DISTINCT series_id FROM skip_catalogue_episodes
        WHERE playlist_id=10 AND asset_key=? LIMIT 3""",(asset['asset_key'],)).fetchall()
    if len(rows)!=1 or not re.fullmatch(r'[1-9][0-9]{0,12}',str(rows[0][0])):
        raise RuntimeError('STOP_NO_UNIQUE_STORED_SERIES_ID')
    return str(rows[0][0])

def series_name_matches(label):
    """Conservative name-only discovery; requires episode metadata confirmation."""
    if not isinstance(label,str) or len(label)>160:
        return False
    text=label.strip().casefold()
    text=re.sub(r'^\s*(?:\[|\()\s*(?:de|ger|it|ita|en|eng)\s*(?:\]|\))\s*[-|:]?\s*','',text)
    text=re.sub(r'^\s*(?:de|ger|it|ita|en|eng)\s*[:|]\s*','',text)
    text=re.sub(r'\s*\(\s*2017\s*\)\s*$','',text)
    return text.strip()=='riverdale'

def candidate_series(value):
    """Exact title discovery only, with bounded candidate count and no auto-ID change."""
    if isinstance(value,dict):
        value=value.get('series')
    if not isinstance(value,list):
        return [],'CATALOGUE_NOT_LIST'
    all_matches=[]
    for item in value:
        if not isinstance(item,dict) or not series_name_matches(item.get('name')):
            continue
        sid=item.get('series_id')
        if re.fullmatch(r'[1-9][0-9]{0,12}',str(sid)):
            all_matches.append(str(sid))
    unique=sorted(set(all_matches))
    if len(unique)>5:
        return [],'TOO_MANY_IDENTICAL_NAME_CANDIDATES'
    return unique,'OK'

def episode_comparison(value,local):
    sections=value.get('episodes') if isinstance(value,dict) else None
    if not isinstance(sections,dict):
        return {'status':'NO_EPISODE_MAP'}
    matches=[]
    for season,items in sections.items():
        if not isinstance(items,list):
            continue
        for item in items[:300]:
            if not isinstance(item,dict):
                continue
            try:
                season_no=int(item.get('season',season))
                episode_no=int(item.get('episode_num',item.get('episode',-1)))
            except (ValueError,TypeError):
                continue
            if season_no==7 and episode_no==6:
                matches.append(item)
    formats=sorted(set(
        str(item.get('container_extension','')).lower().lstrip('.')
        for item in matches
        if str(item.get('container_extension','')).lower().lstrip('.') in (
            'mp4','mkv','m4v','ts','avi','mpeg','mpg')
    ))
    match_id=any(str(item.get('id'))==str(local['stream_id']) for item in matches)
    return dict(status='EPISODE_COMPARISON',
                season7_episode6_count=len(matches),
                original_stream_id_still_listed=match_id,
                current_formats=formats)

def get_json(analysis,url):
    """Fixed proxy, no content logs, limited response size and request time."""
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with analysis._provider_proxy_local(url,lambda:False) as proxy:
            with opener.open(
                urllib.request.Request(proxy,method='GET',
                    headers={'Accept':'application/json'}),timeout=12) as response:
                if response.status!=200:
                    return 'HTTP_'+str(response.status),None
                raw=response.read(MAX_BODY+1)
    except urllib.error.HTTPError as err:
        status=err.code
        err.close()
        return 'PROXY_HTTP_'+str(status),None
    except Exception as err:
        return 'NETWORK_OR_PROVIDER_'+type(err).__name__,None
    if len(raw)>MAX_BODY:
        return 'RESPONSE_EXCEEDS_6MB',None
    try:
        return 'OK',json.loads(raw)
    except (UnicodeError,ValueError):
        return 'NON_JSON_RESPONSE',None

def main():
    if not APP.is_dir() or APP.is_symlink():
        raise RuntimeError('STOP_MISSING_PROVISIONING')
    sys.path.insert(0,str(APP))
    import skip_analysis as analysis
    from skip_analysis_accounts import using
    with exclusive_idle():
        with using(read_only_db):
            with read_only_db() as db:
                asset=local_episode(db)
                if asset is None:
                    raise RuntimeError('STOP_RIVERDALE_FAILURE_NOT_FOUND')
                original_series_id=known_series(db,asset)
                row=db.execute('SELECT * FROM skip_analysis_playlists WHERE id=10 AND archived=0').fetchone()
                if row is None:
                    raise RuntimeError('STOP_ANALYSIS_LINE_UNAVAILABLE')
                conf=analysis.configured_source(row)
            base=conf['xtream_server'].rstrip('/')+'/player_api.php?'
            auth={'username':conf['xtream_username'],'password':conf['xtream_password']}
            catalogue_url=base+urllib.parse.urlencode({**auth,'action':'get_series'})
            status,data=get_json(analysis,catalogue_url)
            print('THE_BEST_GET_SERIES_STATUS:',status)
            if status!='OK':
                return
            ids,state=candidate_series(data)
            print('RIVERDALE_DISCOVERY:',state)
            print('CURRENT_RIVERDALE_SERIES_COUNT:',len(ids))
            print('STORED_RIVERDALE_SERIES_STILL_LISTED:',original_series_id in ids)
            for index,sid in enumerate(ids):
                url=base+urllib.parse.urlencode({**auth,'action':'get_series_info','series_id':sid})
                info_status,info=get_json(analysis,url)
                print('CANDIDATE_'+str(index+1)+'_INFO_STATUS:',
                      'OBJECT' if info_status=='OK' and isinstance(info,dict)
                      else 'EMPTY_ARRAY' if info_status=='OK' and info==[]
                      else info_status)
                if info_status=='OK' and isinstance(info,dict):
                    comparison=episode_comparison(info,asset)
                    print('CANDIDATE_'+str(index+1)+'_EPISODE:',
                          json.dumps(comparison,sort_keys=True))
    print('NO_VIDEO_STREAM_OPENED; NO_DATABASE_OR_MARKER_CHANGES')

if __name__=='__main__':
    try:
        main()
    except Exception as e:
        # Never disclose raw exceptions: remote URL may include login.
        print('SAFE_STOP:',
              str(e) if isinstance(e,RuntimeError) and str(e).startswith('STOP_')
              else 'UNEXPECTED_'+type(e).__name__)
        raise SystemExit(1)
