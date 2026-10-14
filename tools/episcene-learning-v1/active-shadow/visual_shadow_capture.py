#!/usr/bin/env python3
"""Capture at most ONE EpiScene outro boundary as private, unapproved visual evidence.

Reads the production analyzer and the owner-attested shadow model in SQLite
read-only mode. Uses the deployed, provider-limited EpiScene proxy/RPC.
Saves only 500ms image fingerprint hashes in a separate root-only database.
NEVER changes skip_records, their statuses, autoapproval, or analyzer settings.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ORIGINAL=Path('/var/lib/epimediahub/provisioning.db')
SHADOW=Path('/var/lib/episcene-learning/reference-round-40/shadow.sqlite3')
ROOT=Path('/var/lib/episcene-learning/reference-round-40')
OUTPUT=ROOT/'visual_fingerprints.sqlite3'
CONTROLLER=Path('/opt/epimediahub/provisioning')
WINDOW_MS=40_000
STEP_MS=500
MAX_TARGETS=20


def asset_version(asset):
    # Matches EpiScene reliability overlay, preserving NULL for missing fields.
    keys=('asset_key','source_key','playlist_id','stream_id','extension',
          'duration_ms','season','episode','updated_at','content_version','etag')
    values={key:asset.get(key) for key in keys}
    return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':'),
                                     allow_nan=False).encode()).hexdigest()


def prepare(db,shadow):
    db.row_factory=sqlite3.Row;shadow.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    shadow.execute('PRAGMA query_only=ON')
    db.execute('BEGIN');shadow.execute('BEGIN')
    models=shadow.execute('''SELECT series,season,playlist_id,shift_ms,reference_episodes,
        status,publish_allowed,source_key FROM shadow_outro_models''').fetchall()
    model=[dict(m) for m in models if m['series']=='mobland' and m['season']==1
           and m['playlist_id']==8 and m['status']=='shadow_only'
           and m['publish_allowed']==0 and m['reference_episodes']>=5]
    if len(model)!=1:raise RuntimeError('Stable MobLand shadow model missing or ambiguous')
    model=model[0]
    raw=[]
    for r in shadow.execute('''SELECT marker_id,asset_key,kind,start_ms,end_ms,playlist_id
        FROM owner_attested_round40 WHERE title='mobland' AND season=1
        AND playlist_id=8 AND kind='outro' ORDER BY episode'''):
        raw.append(dict(type='reference',record_id=r['marker_id'],
            asset_key=r['asset_key'],start_ms=r['start_ms'],end_ms=r['end_ms'],
            source='device',playlist_id=r['playlist_id']))
    for r in shadow.execute('''SELECT auto_marker_id,asset_key,suggested_start_ms,end_ms,
       playlist_id FROM shadow_outro_candidates
       WHERE series='mobland' AND season=1 AND playlist_id=8
       AND status='SHADOW_REVIEW_ONLY' ORDER BY episode'''):
        raw.append(dict(type='candidate',record_id=r['auto_marker_id'],
            asset_key=r['asset_key'],start_ms=r['suggested_start_ms'],end_ms=r['end_ms'],
            source='audio_repetition',playlist_id=r['playlist_id']))
    if not 5<=len(raw)<=MAX_TARGETS:raise RuntimeError('Unexpected MobLand targets')
    tasks=[]
    for item in raw:
        row=db.execute('''SELECT r.id,r.source,r.status,r.disabled,r.segment_type,
              r.start_ms record_start,r.end_ms record_end,
              a.* FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
              WHERE r.id=?''',(item['record_id'],)).fetchone()
        if row is None:continue
        asset=dict(row)
        if (asset['asset_key']!=item['asset_key'] or asset['playlist_id']!=item['playlist_id']
            or asset['source_key']!=model['source_key']
            or asset['source']!=item['source'] or asset['segment_type']!='outro'
            or asset['disabled'] or asset['status'] not in ('pending','approved')
            or asset['media_type']!='episode'):
            continue
        if item['type']=='reference':
            if (asset['record_start'],asset['record_end'])!=(item['start_ms'],item['end_ms']):continue
        else:
            if asset['record_start']-model['shift_ms']!=item['start_ms']:continue
            if asset['record_end']!=item['end_ms']:continue
            if asset['status']!='pending':continue
        duration=int(asset['duration_ms'])
        begin=max(0, (int(item['start_ms'])-20_000)//STEP_MS*STEP_MS)
        end=min(duration,begin+WINDOW_MS)
        if end-begin!=WINDOW_MS or not 0<item['start_ms']<duration:continue
        tasks.append(dict(type=item['type'],record_id=item['record_id'],
            asset_key=item['asset_key'],asset=asset,
            version=asset_version(asset),start_ms=begin,length_ms=WINDOW_MS))
    return tasks


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS frames(
       record_id INTEGER PRIMARY KEY,kind TEXT NOT NULL,
       asset_key TEXT NOT NULL,asset_version TEXT NOT NULL,
       offset_ms INTEGER NOT NULL,length_ms INTEGER NOT NULL,step_ms INTEGER NOT NULL,
       frames_json TEXT NOT NULL,sha256 TEXT NOT NULL,
       created_unix INTEGER NOT NULL,status TEXT NOT NULL
       CHECK(status='SHADOW_ONLY'))''')


def choose(tasks,out):
    out.row_factory=sqlite3.Row
    migrate(out)
    for task in tasks:
        saved=out.execute('SELECT asset_version,offset_ms,length_ms,step_ms,status FROM frames WHERE record_id=?',
                          (task['record_id'],)).fetchone()
        if (saved and saved['asset_version']==task['version'] and saved['offset_ms']==task['start_ms']
                and saved['length_ms']==task['length_ms'] and saved['step_ms']==STEP_MS
                and saved['status']=='SHADOW_ONLY'):
            continue
        return task
    return None


def capture(task,dbfactory):
    if str(CONTROLLER) not in sys.path:sys.path.insert(0,str(CONTROLLER))
    from skip_analysis import source_url,provider_proxy,probe
    from skip_remote_client import visual_fingerprint,configured,health
    from skip_analysis_worker import busy_check
    from skip_scene_reliability import analysis_playlist
    if not configured():raise RuntimeError('Private Hetzner RPC is not configured')
    with dbfactory() as db:
        s=db.execute('''SELECT enabled FROM skip_analysis_sources WHERE playlist_id=?''',
                     (task['asset']['playlist_id'],)).fetchone()
        if s is None or s[0]!=1:raise RuntimeError('Analysis source is not enabled')
        p=analysis_playlist(db,task['asset']['playlist_id'])
        if p is None:raise RuntimeError('Analysis playlist missing')
        playlist=dict(p)
        if 'enabled' in playlist and playlist['enabled']!=1:
            raise RuntimeError('Analysis playlist is disabled')
    busy=busy_check(dbfactory,[playlist])
    if busy():raise ValueError('analysis_deferred')
    health()
    with provider_proxy(source_url(playlist,task['asset']),busy) as source:
        if busy():raise ValueError('analysis_deferred')
        # Do not mark a runtime as "verified" unless it was actually probed.
        actual,_=probe(source,busy)
        if abs(actual-task['asset']['duration_ms'])>500:
            raise RuntimeError('Stream runtime has changed')
        frames=visual_fingerprint(source,task['start_ms'],task['length_ms'],STEP_MS,busy)
    if len(frames)!=WINDOW_MS//STEP_MS:
        raise RuntimeError('Unexpected fingerprint length')
    # No credential or video data stored, only 4 numerical hashes per frame.
    return frames


def run(source=ORIGINAL,shadow=SHADOW,destination=OUTPUT,fetcher=None):
    for path in (source,shadow):
        if path.is_symlink() or not path.is_file():raise RuntimeError('Missing source DB or symlink')
    if destination.is_symlink():raise RuntimeError('Unexpected output DB symlink')
    if not destination.parent.is_dir() or destination.parent.stat().st_mode & 0o077:
        raise RuntimeError('Shadow output directory must be private')
    with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True,timeout=5) as db, \
         sqlite3.connect(shadow.resolve().as_uri()+'?mode=ro',uri=True,timeout=5) as sh:
        tasks=prepare(db,sh)
    def dbfactory():
        db=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        return db
    with sqlite3.connect(destination,timeout=15) as out:
        task=choose(tasks,out)
    if task is None:
        print(json.dumps(dict(status='COMPLETE',captured_now=0,total_targets=len(tasks),
                              auto_publish=False)))
        return
    # Never use the production DB for any writes, including caches.
    try:
        frames=(fetcher or capture)(task,dbfactory)
    except ValueError as error:
        if str(error)=='analysis_deferred':
            print(json.dumps(dict(status='DEFERRED_ACTIVE_PLAYBACK',captured_now=0,
                                  record_id=task['record_id'],auto_publish=False)))
            return
        raise
    if len(frames)!=WINDOW_MS//STEP_MS:raise RuntimeError('Invalid frame count')
    from hashlib import sha256
    payload=json.dumps(frames,separators=(',',':'))
    with dbfactory() as db:
        live=db.execute('''SELECT r.source,r.status,r.start_ms,r.end_ms,a.* FROM skip_records r
          JOIN skip_assets a ON a.asset_key=r.asset_key WHERE r.id=?''',
          (task['record_id'],)).fetchone()
        if live is None or asset_version(dict(live))!=task['version']:
            raise RuntimeError('Asset changed during capture – no evidence stored')
    with sqlite3.connect(destination,timeout=15) as out:
        migrate(out)
        out.execute('''INSERT OR REPLACE INTO frames
          VALUES(?,?,?,?,?,?,?,?,?,?,?,'SHADOW_ONLY')''',
          (task['record_id'],task['type'],task['asset_key'],task['version'],
           task['start_ms'],task['length_ms'],STEP_MS,payload,
           sha256(payload.encode()).hexdigest(),int(time.time())))
    print(json.dumps(dict(status='SHADOW_CAPTURED',record_id=task['record_id'],
        kind=task['type'],offset_seconds=task['start_ms']/1000,
        seconds=WINDOW_MS/1000,frames=len(frames),auto_publish=False),
        ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=ORIGINAL)
    parser.add_argument('--shadow',type=Path,default=SHADOW)
    parser.add_argument('--dest',type=Path,default=OUTPUT)
    a=parser.parse_args()
    if os.geteuid()!=0:raise SystemExit('Run as root in protected EpiScene installation')
    lock=ROOT/'visual-shadow-capture.lock'
    with lock.open('a') as file:
        try:fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('CAPTURE_BUSY – another shadow image worker runs')
            return
        run(a.source,a.shadow,a.dest)


if __name__=='__main__': main()
