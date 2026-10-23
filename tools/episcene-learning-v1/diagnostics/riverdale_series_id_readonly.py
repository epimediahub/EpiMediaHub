#!/usr/bin/env python3
"""Compare Riverdale S07E06 failed analysis ID with the Xtream series catalogue.

Only dedicated analysis playlist 10. No media stream, customer access,
production writes or provider URLs/credentials in the output.
"""
from __future__ import annotations
from collections import Counter
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
import sys
import urllib.parse
import urllib.request
import urllib.error

ROOT=Path('/opt/epimediahub/provisioning')
DB=Path('/var/lib/epimediahub/provisioning.db')
MAX_REPLY=1500000

def cols(db,name):
    if name not in ('skip_catalogue_episodes','skip_catalogue_episode','skip_catalogue_series','skip_auto_series'):
        return set()
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone():
        return set()
    return {r[1] for r in db.execute('PRAGMA table_info('+name+')')}

def read_only():
    db=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db

def chosen_episode(db):
    return db.execute("""SELECT a.* FROM skip_assets a JOIN skip_jobs j
      ON j.asset_key=a.asset_key WHERE a.playlist_id=10
      AND a.media_type='episode' AND a.season=7 AND a.episode=6
      AND lower(trim(a.title)) LIKE '%riverdale%'
      AND j.status='failed' AND j.detail LIKE '%HTTP 405%'
      ORDER BY j.updated_at DESC LIMIT 1""").fetchone()

def candidate_series_ids(db,episode):
    """Exact original catalogue ownership: asset_key + playlist_id.

    The original catalogue table's ID is a SERIES ID; the player episode's
    stream_id belongs to skip_assets, not to skip_catalogue_episodes.
    Fail closed for absent or conflicting catalogue links.
    """
    table='skip_catalogue_episodes'
    required={'playlist_id','asset_key','series_id'}
    columns=cols(db,table)
    if not required.issubset(columns):
        return [],['skip_catalogue_episodes:unavailable_exact_asset_link']
    rows=db.execute("""
        SELECT DISTINCT c.series_id FROM skip_catalogue_episodes c
        WHERE c.playlist_id=? AND c.asset_key=?
        LIMIT 8
    """,(episode['playlist_id'],episode['asset_key'])).fetchall()
    if not rows:
        return [],['skip_catalogue_episodes:asset_link_absent']
    valid=set()
    if len(rows)>1:
        return [],['skip_catalogue_episodes:conflicting_asset_links']
    for (value,) in rows:
        if not re.fullmatch(r'[1-9][0-9]{0,12}',str(value)):
            return [],['skip_catalogue_episodes:invalid_series_id']
        valid.add(str(value))
    return sorted(valid),['skip_catalogue_episodes:exact_asset_key_link']

def control_series_ids(db, riverdale_id):
    """Two independently catalogued series for an API endpoint control test."""
    need={'playlist_id','series_id','asset_key','seen_generation'}
    if not need.issubset(cols(db,'skip_catalogue_episodes')):
        return []
    rows=db.execute("""
      SELECT c.series_id
      FROM skip_catalogue_episodes c
      JOIN skip_assets a ON a.asset_key=c.asset_key AND a.playlist_id=c.playlist_id
      WHERE c.playlist_id=10 AND c.series_id<>? AND a.media_type='episode'
      GROUP BY c.series_id
      HAVING COUNT(*) BETWEEN 2 AND 100
      ORDER BY MAX(c.seen_generation) DESC, COUNT(*) DESC
      LIMIT 2
    """,(riverdale_id,)).fetchall()
    return [str(r[0]) for r in rows
            if re.fullmatch(r'[1-9][0-9]{0,12}',str(r[0]))]

def api_fetch(analysis,url):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with analysis._provider_proxy_local(url,lambda:False) as relay:
            with opener.open(urllib.request.Request(
                    relay,headers={'Accept':'application/json'},method='GET'),timeout=12) as reply:
                if reply.status!=200:
                    return 'HTTP_'+str(reply.status),None
                data=reply.read(MAX_REPLY+1)
    except urllib.error.HTTPError as exc:
        code=exc.code
        exc.close()
        return 'LOCAL_HTTP_'+str(code),None
    except Exception as exc:
        # Never return exception text containing a possibly private URL.
        return 'PROVIDER_OR_NETWORK_'+type(exc).__name__,None
    if len(data)>MAX_REPLY:
        return 'OVERSIZED_RESPONSE',None
    try:
        value=json.loads(data)
    except (ValueError,UnicodeError):
        return 'NON_JSON_RESPONSE',None
    if isinstance(value,dict):
        return 'OK',value
    # Report only a categorical response shape: no raw provider content.
    if isinstance(value,list):
        return ('XTREAM_EMPTY_ARRAY' if not value else 'XTREAM_NONEMPTY_ARRAY'),None
    if value is None:
        return 'XTREAM_JSON_NULL',None
    if type(value) is bool:
        return ('XTREAM_JSON_TRUE' if value else 'XTREAM_JSON_FALSE'),None
    if type(value) is str:
        return 'XTREAM_JSON_STRING',None
    if type(value) in (int,float):
        return 'XTREAM_JSON_NUMBER',None
    return 'XTREAM_UNSUPPORTED_JSON_SHAPE',None

def evaluate(catalog,episode):
    sections=catalog.get('episodes')
    if not isinstance(sections,dict):
        return dict(status='NO_EPISODE_CATALOG')
    matches=[]
    total=0
    for bucket,values in sections.items():
        if not isinstance(values,list):
            continue
        for row in values[:500]:
            if not isinstance(row,dict):
                continue
            total+=1
            try:
                season=int(row.get('season',bucket))
                ep=int(row.get('episode_num',row.get('episode',-1)))
            except (TypeError,ValueError):
                continue
            if (season,ep)==(7,6):
                matches.append(row)
    formats=Counter()
    for row in matches:
        value=row.get('container_extension') or row.get('extension')
        if isinstance(value,str) and value.lower().lstrip('.') in (
              'mp4','mkv','avi','m4v','ts','mpeg','mpg'):
            formats[value.lower().lstrip('.')]+=1
    ids={str(row.get('id')) for row in matches if row.get('id') is not None}
    return dict(status='CATALOG_EPISODE_COMPARISON',
                api_episode_count=total,
                season7_episode6_candidates=len(matches),
                analysis_stream_id_matches_catalog=str(episode['stream_id']) in ids,
                current_catalogue_extensions=dict(formats),
                stored_extension=str(episode['extension']).lower(),
                possible_multiple_language_editions=len(matches)>1)

def main():
    if DB.is_symlink() or not DB.is_file() or not ROOT.is_dir():
        print('SAFE_STOP: EXPECTED_INSTALLATION_MISSING')
        return 1
    sys.path.insert(0,str(ROOT))
    import skip_analysis as analysis
    from skip_analysis_accounts import using
    with read_only() as db:
        episode=chosen_episode(db)
        if episode is None:
            print('SAFE_STOP: RIVERDALE_FAILURE_NOT_FOUND')
            return 1
        series_ids,discovery=candidate_series_ids(db,episode)
    print('EPISODE: Riverdale; THE BEST; Staffel 7 Folge 6')
    print('STORED_EXTENSION:',str(episode['extension']).lower())
    print('CATALOGUE_LOOKUP_TYPES:',discovery)
    if len(series_ids)!=1:
        print('SAFE_STOP: SERIES_ID_JOIN_'+('UNAVAILABLE' if not series_ids else 'AMBIGUOUS'))
        print('NO_PROVIDER_REQUEST; NO_DATABASE_OR_MARKER_CHANGES')
        return 0
    # Compare the Riverdale response with two independently indexed series.
    # No titles, series identifiers or raw provider JSON are exported.
    with read_only() as db:
        controls=control_series_ids(db,series_ids[0])
    # This metadata call does not open or decode any video.
    with using(read_only):
        with read_only() as db:
            playlist=db.execute(
                'SELECT * FROM skip_analysis_playlists WHERE id=10 AND archived=0').fetchone()
            if playlist is None:
                print('SAFE_STOP: ANALYSIS_ACCESS_DISABLED')
                return 1
            cfg=analysis.configured_source(playlist)
        url=cfg['xtream_server'].rstrip('/')+'/player_api.php?'+urllib.parse.urlencode({
            'username':cfg['xtream_username'],'password':cfg['xtream_password'],
            'action':'get_series_info','series_id':series_ids[0]})
        result,data=api_fetch(analysis,url)
    print('XTREAM_SERIES_INFO_STATUS:',result)
    if result=='OK':
        print('EPISODE_COMPARISON:',json.dumps(evaluate(data,episode),sort_keys=True))
    if result=='XTREAM_EMPTY_ARRAY':
        other_results=[]
        for index,sid in enumerate(controls[:2]):
            query=urllib.parse.urlencode({
                'username':cfg['xtream_username'],'password':cfg['xtream_password'],
                'action':'get_series_info','series_id':sid})
            control_url=cfg['xtream_server'].rstrip('/')+'/player_api.php?'+query
            status,_=api_fetch(analysis,control_url)
            other_results.append(status)
            print('CONTROL_'+('A' if index==0 else 'B')+'_STATUS:',status)
        if not other_results:
            print('INTERPRETATION: NO_INDEPENDENT_REFERENCE_SERIES')
        elif all(status=='XTREAM_EMPTY_ARRAY' for status in other_results) and len(other_results)>=2:
            print('INTERPRETATION: SERIES_INFO_EMPTY_ACROSS_THREE_DISTINCT_SERIES')
        elif 'OK' in other_results:
            print('INTERPRETATION: RIVERDALE_SERIES_ID_NOT_RETURNED_BUT_OTHER_SERIES_WORK')
        else:
            print('INTERPRETATION: ENDPOINT_SUPPORT_INCONCLUSIVE')
    print('NO_VIDEO_STREAM_OPENED; NO_DATABASE_OR_MARKER_CHANGES')
    return 0

if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (sqlite3.Error,ValueError,OSError,KeyError) as exc:
        print('SAFE_STOP:',type(exc).__name__)
        raise SystemExit(1)
