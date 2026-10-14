#!/usr/bin/env python3
"""Read-only visual coverage gate for the shadow EpiScene outro candidates.

Answers: do existing, revision-bound visual caches include the proposed
earlier story-to-credits boundary? No media is fetched, no marker is approved.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ORIGINAL=Path("/var/lib/epimediahub/provisioning.db")
SHADOW=Path("/var/lib/episcene-learning/reference-round-40/shadow.sqlite3")
VERSION_FIELDS=('asset_key','source_key','playlist_id','stream_id','extension',
                'duration_ms','season','episode','updated_at','content_version','etag')


def asset_version(asset):
    # Same algorithm as skip_scene_reliability.asset_version; absent optional
    # metadata is None and therefore cannot accidentally match another revision.
    data={key:asset.get(key) for key in VERSION_FIELDS}
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),
                                     allow_nan=False).encode()).hexdigest()


def table_exists(db,table):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone())


def columns(db,table):
    return {row[1] for row in db.execute('PRAGMA table_info('+table+')')}


def read(db,table,what,args=()):
    return db.execute('SELECT '+what+' FROM '+table,args).fetchall()


def continuous(intervals,start,end):
    if end<=start:return False
    cursor=start
    for a,b in sorted(intervals):
        if a>cursor:return False
        if b>cursor:cursor=b
        if cursor>=end:return True
    return False


def compare_prior(db,correction_ms):
    rows=[dict(x) for x in db.execute('''
      SELECT id,asset_key,start_ms,end_ms,source,segment_type FROM skip_records
      WHERE id IN (1970,1315)''')]
    by_id={x['id']:x for x in rows}
    if set(by_id)!={1970,1315}:
        return {'status':'NOT_TESTABLE','reason':'older_markers_not_present'}
    h,a=by_id[1970],by_id[1315]
    if not(h['asset_key'] and h['asset_key']==a['asset_key']):
        return {'status':'NOT_TESTABLE','reason':'different_asset_or_orphan'}
    if not(h['segment_type']==a['segment_type']=='outro'
           and a['source']=='audio_repetition'
           and isinstance(h['start_ms'],int) and isinstance(a['start_ms'],int)):
        return {'status':'NOT_TESTABLE','reason':'unexpected_record_type'}
    delta=int(a['start_ms'])-int(h['start_ms'])
    return {'status':'SAME_ASSET_CANDIDATE',
            'observed_offset_seconds':round(delta/1000,3),
            'difference_from_round_model_seconds':round((delta-correction_ms)/1000,3),
            'note':'Previously observed episode; not a blinded holdout or verified reviewer label'}


def inspect(db,shadow):
    db.row_factory=sqlite3.Row;shadow.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    shadow.execute('PRAGMA query_only=ON')
    db.execute('BEGIN');shadow.execute('BEGIN')
    for name,fields in {
        'skip_records':{'id','asset_key','start_ms','end_ms','source','segment_type','status'},
        'skip_assets':{'asset_key','duration_ms'},
    }.items():
        if not fields<=columns(db,name):raise RuntimeError('Live DB schema mismatch: '+name)
    for name in ('shadow_outro_models','shadow_outro_candidates'):
        if not table_exists(shadow,name):raise RuntimeError('Shadow database schema mismatch: '+name)
    models=[dict(x) for x in shadow.execute('''
      SELECT series,season,playlist_id,shift_ms,reference_episodes,mad_ms,status,publish_allowed
      FROM shadow_outro_models ORDER BY series,season,playlist_id''')]
    candidates=[dict(x) for x in shadow.execute('''
      SELECT auto_marker_id,asset_key,series,season,episode,playlist_id,
             original_start_ms,suggested_start_ms,end_ms,offset_ms,status
      FROM shadow_outro_candidates ORDER BY auto_marker_id''')]
    if len(models)>100 or len(candidates)>10000:raise RuntimeError('Unexpected shadow dataset size')
    has_windows=table_exists(db,'skip_scene_windows')
    has_versions=table_exists(db,'skip_scene_window_versions')
    if has_windows and not {'asset_key','kind','offset_ms','length_ms','duration_ms','id','created_at'}<=columns(db,'skip_scene_windows'):
        raise RuntimeError('Visual cache schema changed')
    if has_versions and not {'window_id','version'}<=columns(db,'skip_scene_window_versions'):
        raise RuntimeError('Cache version schema changed')
    output=[]
    for c in candidates:
        row=db.execute('''
          SELECT r.asset_key,r.source,r.segment_type,r.status,r.start_ms,r.end_ms,
                 a.* FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
          WHERE r.id=?''',(c['auto_marker_id'],)).fetchone()
        if row is None:
            output.append(dict(marker_id=c['auto_marker_id'],state='STALE_MISSING_ASSET'))
            continue
        asset=dict(row)
        if (asset['asset_key']!=c['asset_key'] or asset['source']!='audio_repetition'
                or asset['segment_type']!='outro' or asset['status']!='pending'
                or asset['start_ms']!=c['original_start_ms'] or asset['end_ms']!=c['end_ms']
                or asset.get('playlist_id')!=c['playlist_id']):
            output.append(dict(marker_id=c['auto_marker_id'],state='STALE_SOURCE_CHANGED'))
            continue
        before=max(0,c['suggested_start_ms']-6000)
        after=min(int(asset['duration_ms']),c['suggested_start_ms']+6000)
        oldbefore=max(0,c['original_start_ms']-6000)
        oldafter=min(int(asset['duration_ms']),c['original_start_ms']+6000)
        valid=[];other=0
        if has_windows:
            rows=db.execute('''SELECT w.id,w.offset_ms,w.length_ms,w.created_at,w.duration_ms,
                     v.version FROM skip_scene_windows w
                     LEFT JOIN skip_scene_window_versions v ON v.window_id=w.id
                     WHERE w.asset_key=? AND w.kind='outro' AND w.duration_ms=?
                     ORDER BY w.offset_ms LIMIT 2000''',(c['asset_key'],asset['duration_ms'])).fetchall() if has_versions else \
                 db.execute('''SELECT id,offset_ms,length_ms,created_at,duration_ms
                     FROM skip_scene_windows WHERE asset_key=? AND kind='outro'
                     AND duration_ms=? ORDER BY offset_ms LIMIT 2000''',
                     (c['asset_key'],asset['duration_ms'])).fetchall()
            expected=asset_version(asset)
            for v in rows:
                if has_versions and v['version']==expected:
                    valid.append((v['offset_ms'],v['offset_ms']+v['length_ms']))
                else:other+=1
        output.append({
            'marker_id':c['auto_marker_id'],
            'series':c['series'],
            'season':c['season'],
            'episode':c['episode'],
            'playlist_id':c['playlist_id'],
            'state':'READ_ONLY_PROPOSAL',
            'earlier_start_seconds':round(c['suggested_start_ms']/1000,3),
            'original_start_seconds':round(c['original_start_ms']/1000,3),
            'valid_revision_visual_windows':len(valid),
            'unverified_or_stale_windows':other,
            'earlier_boundary_covered_by_valid_cache':continuous(valid,before,after),
            'original_boundary_covered_by_valid_cache':continuous(valid,oldbefore,oldafter),
            'needs_new_visual_evidence':not continuous(valid,before,after),
            'eligible_for_automatic_release':False,
        })
    offsets=[x['shift_ms'] for x in models if x['series']=='mobland' and x['season']==1
             and x['playlist_id']==8 and x['status']=='shadow_only'
             and x['publish_allowed']==0]
    previous=compare_prior(db,offsets[0]) if len(offsets)==1 else \
             {'status':'NOT_TESTABLE','reason':'model_missing_or_ambiguous'}
    return {'mode':'READ_ONLY_VISUAL_GATE','production_marker_changes':0,
            'new_verified_labels':0,'new_auto_approvals':0,
            'models':len(models),'candidate_count':len(output),
            'independent_episode_one_check':previous,
            'candidates':output}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,default=ORIGINAL)
    p.add_argument('--shadow',type=Path,default=SHADOW)
    a=p.parse_args()
    for path in (a.source,a.shadow):
        if path.is_symlink() or not path.is_file():raise SystemExit('Missing/unexpected database path')
    with sqlite3.connect(a.source.resolve().as_uri()+'?mode=ro',uri=True,timeout=10) as db, \
         sqlite3.connect(a.shadow.resolve().as_uri()+'?mode=ro',uri=True,timeout=10) as sh:
        print(json.dumps(inspect(db,sh),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
