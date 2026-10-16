#!/usr/bin/env python3
"""EpiScene feedback learning: authenticated human decisions -> durable shadow evidence.

Reads original SQLite read-only. Records actual, current human decisions and
historical revisions in a separate root-protected learning DB. Compares *same
asset/cut* machine proposals for boundary error and safe, shadow-only seasonal
calibration. No customer releases, forged approval or analyzer database writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

ORIGINAL=Path('/var/lib/epimediahub/provisioning.db')
OUTPUT=Path('/var/lib/episcene-learning/reference-round-40/feedback.sqlite3')
MANUAL_KINDS={'intro','recap','outro'}
REJECTED_HISTORICAL_MARKER_IDS={2282}
MACHINE_SOURCES={'audio','chapter','theintrodb','audio_repetition','auto_audio','episcene'}
SOURCE_VERSION_KEYS=('asset_key','source_key','playlist_id','stream_id','extension',
                     'duration_ms','season','episode','updated_at','content_version','etag')


def iso():
    return datetime.now(timezone.utc).isoformat()


def iso_date(value):
    if not isinstance(value,str):return None
    try:
        obj=datetime.fromisoformat(value.replace('Z','+00:00'))
        return obj.astimezone(timezone.utc) if obj.tzinfo else None
    except ValueError:
        return None


def asset_version(asset):
    return hashlib.sha256(json.dumps(
        {k:asset.get(k) for k in SOURCE_VERSION_KEYS},
        sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def records(db):
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    needed={
      'skip_records':{'id','asset_key','source','source_key','segment_type','status',
          'season','episode','media_type','title','start_ms','end_ms','duration_ms',
          'disabled','reviewed_at','created_at','device_id','customer_id'},
      'skip_assets':{'asset_key','playlist_id','source_key','season','episode','media_type',
          'title','duration_ms','stream_id','extension'},
      'devices':{'id','customer_id','enabled'},
      'customer_playlists':{'id','customer_id'},
      'skip_analysis_playlists':{'id','archived'},
      'skip_analysis_sources':{'playlist_id','enabled'},
      'skip_auto_evidence':{'record_id','human_review'},
    }
    for table,fields in needed.items():
        found={r[1] for r in db.execute('PRAGMA table_info('+table+')')}
        if not fields<=found:raise RuntimeError('Production schema unexpected: '+table)
    return [dict(r) for r in db.execute("""
      SELECT r.*,COALESCE(e.human_review,0) human_review,
        a.playlist_id as_asset_playlist,a.source_key as_asset_source,
        a.media_type as_asset_media,a.season as_asset_season,
        a.episode as_asset_episode,a.title as_asset_title,
        a.duration_ms as_asset_duration,
        a.stream_id as_asset_stream,a.extension as_asset_extension,
        a.updated_at as_asset_updated_at,
        p.customer_id as_playlist_owner,
        ap.id as_analysis_playlist,ap.archived as_analysis_archived,
        ss.enabled as_analysis_source_on,
        d.customer_id as_device_owner,d.enabled as_device_enabled
      FROM skip_records r
      LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
      LEFT JOIN skip_assets a ON a.asset_key=r.asset_key
      LEFT JOIN customer_playlists p ON p.id=a.playlist_id
      LEFT JOIN skip_analysis_playlists ap ON ap.id=a.playlist_id
      LEFT JOIN skip_analysis_sources ss ON ss.playlist_id=a.playlist_id
      LEFT JOIN devices d ON d.id=r.device_id
      WHERE r.media_type='episode' AND r.segment_type IN ('intro','recap','outro')
        AND (r.source='device' OR r.source IN
             ('audio','chapter','theintrodb','audio_repetition','auto_audio','episcene'))
    """)]


def valid_identity(r):
    return (r['as_asset_playlist'] is not None and r['as_asset_source']==r['source_key']
            and r['as_asset_media']==r['media_type']
            and r['as_asset_season']==r['season'] and r['as_asset_episode']==r['episode']
            and r['as_asset_title'] and r['as_asset_title'].strip().casefold()==r['title'].strip().casefold()
            and isinstance(r['as_asset_duration'],int) and isinstance(r['duration_ms'],int)
            and abs(r['as_asset_duration']-r['duration_ms'])<=500
            and isinstance(r['as_asset_stream'],str) and bool(r['as_asset_stream']))


def current_human(r):
    if (r['id'] in REJECTED_HISTORICAL_MARKER_IDS or
            not valid_identity(r) or r['status'] not in ('approved','rejected')):
        return None
    if iso_date(r['reviewed_at']) is None:
        return None
    if r['source']=='device':
        if (r['device_id'] is None or r['customer_id'] is None
            or r['as_device_enabled']!=1 or r['as_device_owner']!=r['customer_id']):
            return None
        ordinary=(r['as_playlist_owner']==r['customer_id'])
        independent=(
            r['as_asset_playlist'] in (8,10)
            and r['as_playlist_owner'] is None
            and r['as_analysis_playlist']==r['as_asset_playlist']
            and r['as_analysis_archived']==0
            and r['as_analysis_source_on']==1
        )
        if not (ordinary or independent):
            return None
        provenance='device_authenticated_direct'
    elif r['source'] in MACHINE_SOURCES and r['human_review']==1:
        provenance='admin_reviewed_machine'
    else:
        return None
    start,end,duration=r['start_ms'],r['end_ms'],r['duration_ms']
    if not all(type(x) is int for x in (start,end,duration)):return None
    if r['status']=='approved' and not r['disabled']:
        if not 0<=start<end<=duration or end-start<5000:return None
        outcome='positive'
    else:
        outcome='negative'
    current={k:r[k] for k in ('asset_key','source_key','season','episode','segment_type',
                               'start_ms','end_ms','duration_ms','reviewed_at','status','disabled')}
    current.update(playlist_id=r['as_asset_playlist'],outcome=outcome,provenance=provenance)
    v=asset_version(dict(asset_key=r['asset_key'],source_key=r['as_asset_source'],
        playlist_id=r['as_asset_playlist'],stream_id=r['as_asset_stream'],
        extension=r['as_asset_extension'],duration_ms=r['as_asset_duration'],
        season=r['as_asset_season'],episode=r['as_asset_episode'],
        updated_at=r['as_asset_updated_at']))
    current['asset_version']=v
    current['marker_id']=r['id']
    current['revision_sha256']=hashlib.sha256(json.dumps(
        current,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return current


def derive(rows):
    """Only current noncontradictory exact-device/admin decisions become labels."""
    humans=[h for r in rows if (h:=current_human(r)) is not None]
    groups=defaultdict(list)
    for h in humans:
        groups[(h['asset_key'],h['segment_type'])].append(h)
    conflicts={key for key,v in groups.items() if len(v)>1}
    humans=[h for h in humans if (h['asset_key'],h['segment_type']) not in conflicts]
    machine=defaultdict(list)
    for r in rows:
        if (r['source'] in MACHINE_SOURCES and valid_identity(r) and not r['disabled']
                and isinstance(r['start_ms'],int) and isinstance(r['end_ms'],int)
                and 0<=r['start_ms']<r['end_ms']<=r['duration_ms']):
            machine[(r['asset_key'],r['segment_type'],r['source'])].append(r)
    comparisons=[]
    for h in humans:
        for source in sorted(MACHINE_SOURCES):
            possibilities=[m for m in machine.get((h['asset_key'],h['segment_type'],source),[])
                           if m['id']!=h['marker_id'] and
                           (iso_date(m['created_at']) is not None and
                            iso_date(m['created_at'])<=iso_date(h['reviewed_at']))]
            if len(possibilities)!=1:
                # Multiple predictions from one detector are ambiguous; never
                # silently choose the one nearest a known correct marker.
                continue
            m=possibilities[0]
            comparisons.append(dict(marker_id=h['marker_id'],machine_id=m['id'],
                playlist_id=h['playlist_id'],source_key=h['source_key'],
                season=h['season'],episode=h['episode'],kind=h['segment_type'],
                machine_source=source,outcome=h['outcome'],asset_version=h['asset_version'],
                human_start_ms=h['start_ms'],human_end_ms=h['end_ms'],
                machine_start_ms=m['start_ms'],machine_end_ms=m['end_ms'],
                start_error_ms=m['start_ms']-h['start_ms'] if h['outcome']=='positive' else None,
                end_error_ms=m['end_ms']-h['end_ms'] if h['outcome']=='positive' else None,
                reviewed_at=h['reviewed_at']))
    models=calibrations(comparisons)
    return humans,comparisons,models,len(conflicts)


def calibrations(comparisons):
    groups=defaultdict(list)
    for v in comparisons:
        if v['outcome']!='positive':continue
        if v['start_error_ms'] is None or v['end_error_ms'] is None:continue
        if abs(v['start_error_ms'])>120000 or abs(v['end_error_ms'])>30000:continue
        key=(v['playlist_id'],v['source_key'],v['season'],v['kind'],v['machine_source'])
        groups[key].append(v)
    result=[]
    for k,items in groups.items():
        # Independent episode/cut, not duplicate references or language versions.
        by_episode=defaultdict(list)
        for v in items:by_episode[v['episode']].append(v)
        independent=[group[0] for group in by_episode.values() if len(group)==1]
        if len(independent)<4:continue
        starts=[v['start_error_ms'] for v in independent]
        ends=[v['end_error_ms'] for v in independent]
        s=median(starts);e=median(ends)
        mad_s=median(abs(v-s) for v in starts)
        mad_e=median(abs(v-e) for v in ends)
        loo=median(abs(value-median([v for j,v in enumerate(starts) if j!=i]))
                   for i,value in enumerate(starts))
        if (mad_s>1500 or mad_e>2000 or
                max(starts)-min(starts)>10000 or
                max(ends)-min(ends)>12000 or loo>2000):
            continue
        result.append(dict(playlist_id=k[0],source_key=k[1],season=k[2],kind=k[3],
            machine_source=k[4],start_shift_ms=round(s),end_shift_ms=round(e),
            independent_episodes=len(independent),loo_median_start_error_ms=round(loo),
            status='SHADOW_ONLY',auto_publish_allowed=0))
    return result


def write(output,humans,comparisons,models,conflicts):
    if output.is_symlink():raise RuntimeError('Unexpected training output symlink')
    if output.parent.stat().st_mode & 0o077:
        raise RuntimeError('Training output directory must be root-private (0700)')
    with sqlite3.connect(output,timeout=30) as db:
        db.executescript("""
          CREATE TABLE IF NOT EXISTS feedback_versions(
            marker_id INTEGER NOT NULL,revision_sha256 TEXT NOT NULL,
            decision TEXT NOT NULL,kind TEXT NOT NULL,provenance TEXT NOT NULL,
            asset_key TEXT NOT NULL,asset_version TEXT NOT NULL,
            playlist_id INTEGER NOT NULL,source_key TEXT NOT NULL,
            season INTEGER NOT NULL,episode INTEGER NOT NULL,
            start_ms INTEGER NOT NULL,end_ms INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL,active INTEGER NOT NULL,
            first_observed TEXT NOT NULL,
            PRIMARY KEY(marker_id,revision_sha256));
          CREATE TABLE IF NOT EXISTS machine_comparisons(
            marker_id INTEGER NOT NULL,machine_id INTEGER NOT NULL,
            asset_version TEXT NOT NULL,kind TEXT NOT NULL,machine_source TEXT NOT NULL,
            outcome TEXT NOT NULL,start_error_ms INTEGER,end_error_ms INTEGER,
            PRIMARY KEY(marker_id,machine_id));
          CREATE TABLE IF NOT EXISTS shadow_calibrations(
            playlist_id INTEGER NOT NULL,source_key TEXT NOT NULL,
            season INTEGER NOT NULL,kind TEXT NOT NULL,machine_source TEXT NOT NULL,
            start_shift_ms INTEGER NOT NULL,end_shift_ms INTEGER NOT NULL,
            independent_episodes INTEGER NOT NULL,
            loo_median_start_error_ms INTEGER NOT NULL,
            status TEXT NOT NULL,auto_publish_allowed INTEGER NOT NULL,
            PRIMARY KEY(playlist_id,source_key,season,kind,machine_source));
        """)
        db.execute('UPDATE feedback_versions SET active=0')
        moment=iso()
        db.executemany("""INSERT INTO feedback_versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)
            ON CONFLICT(marker_id,revision_sha256) DO UPDATE SET active=1""",
            [(h['marker_id'],h['revision_sha256'],h['outcome'],h['segment_type'],
              h['provenance'],h['asset_key'],h['asset_version'],h['playlist_id'],
              h['source_key'],h['season'],h['episode'],h['start_ms'],h['end_ms'],
              h['reviewed_at'],moment) for h in humans])
        db.execute('DELETE FROM machine_comparisons')
        db.executemany("""INSERT INTO machine_comparisons VALUES(?,?,?,?,?,?,?,?)""",
            [(v['marker_id'],v['machine_id'],v['asset_version'],v['kind'],
              v['machine_source'],v['outcome'],v['start_error_ms'],v['end_error_ms'])
             for v in comparisons])
        db.execute('DELETE FROM shadow_calibrations')
        db.executemany("""INSERT INTO shadow_calibrations VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            [(m['playlist_id'],m['source_key'],m['season'],m['kind'],
              m['machine_source'],m['start_shift_ms'],m['end_shift_ms'],
              m['independent_episodes'],m['loo_median_start_error_ms'],
              m['status'],m['auto_publish_allowed']) for m in models])
    return dict(mode='CONTINUOUS_AUTHENTICATED_FEEDBACK_LEARNING',
        active_human_decisions=len(humans),positive=sum(h['outcome']=='positive' for h in humans),
        negative=sum(h['outcome']=='negative' for h in humans),
        by_kind=dict(Counter(h['segment_type'] for h in humans)),
        ambiguous_human_asset_kinds=conflicts,
        same_asset_machine_comparisons=len(comparisons),
        shadow_models=len(models),reviewed_machine_comparisons_not_auto_release=True,
        auto_publish=False,verified_admin_claims_fabricated=0,production_db_modified=False)


def run(source=ORIGINAL,output=OUTPUT,*,persist=True):
    if source.is_symlink() or not source.is_file():raise RuntimeError('Production source unavailable')
    with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True,timeout=15) as db:
        db.execute('BEGIN')
        rows=records(db)
    humans,comparisons,models,conflicts=derive(rows)
    if not persist:
        return dict(mode='FEEDBACK_PREFLIGHT_READ_ONLY',eligible=len(humans),
            positives=sum(h['outcome']=='positive' for h in humans),
            negatives=sum(h['outcome']=='negative' for h in humans),
            same_asset_comparisons=len(comparisons),shadow_models=len(models),
            ambiguous_asset_kinds=conflicts,no_writes=True)
    return write(output,humans,comparisons,models,conflicts)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=ORIGINAL)
    parser.add_argument('--dest',type=Path,default=OUTPUT)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run(args.source,args.dest,persist=not args.check),
                     indent=2,ensure_ascii=False))


if __name__=='__main__':main()
