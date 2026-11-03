#!/usr/bin/env python3
"""EpiScene audio evidence recovery: read-only planning, never queues jobs.

Ranks referenced missing audio windows by whether they can be regenerated
through EXISTING analysis jobs. Prints counts only; no stream access, secrets,
asset keys, series titles, job IDs, or modifications.
"""
import collections
import json
import sqlite3
import time
from pathlib import Path

DB = Path('/var/lib/epimediahub/provisioning.db')
SOURCE_IDS = (8, 10)
RETRYABLE = {'done','review','no_match','no_reference','partial','failed'}
MACHINE = ('audio','audio_repetition','episcene','chapter','theintrodb','auto_audio')


def parse(data):
    try:
        v=json.loads(data or '{}')
        return v if isinstance(v,dict) else {}
    except (ValueError,TypeError):
        return {}


def present(db,table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                      (table,)).fetchone() is not None


def columns(db,table):
    return {r[1] for r in db.execute('PRAGMA table_info('+table+')')}


def analyze(db):
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    for name,required in {
       'skip_records': {'id','asset_key','status','source','segment_type'},
       'skip_assets': {'asset_key','playlist_id','source_key','season','episode','duration_ms'},
       'skip_auto_evidence': {'record_id','evidence_json'},
       'skip_auto_windows': {'asset_key','kind'},
       'skip_jobs': {'asset_key','status'},
       'skip_analysis_playlists': {'id','archived'},
       'skip_analysis_sources': {'playlist_id','enabled'},
       'skip_auto_settings': {'playlist_id','enabled'},
    }.items():
        if not present(db,name) or not required <= columns(db,name):
            raise RuntimeError('Required schema missing/mismatched: '+name)

    available=set(tuple(r) for r in db.execute('SELECT asset_key,kind FROM skip_auto_windows'))
    missing=collections.defaultdict(set)
    stats={p:collections.Counter() for p in SOURCE_IDS}
    q="""SELECT r.asset_key,r.segment_type,a.playlist_id,e.evidence_json
         FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
         LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
         WHERE r.status='pending' AND a.playlist_id IN (8,10)
           AND r.source IN ('audio','audio_repetition','episcene','chapter','theintrodb','auto_audio')"""
    for row in db.execute(q):
        ev=parse(row['evidence_json'])
        if ev.get('status')!='AUTO_CONFIRMED' or ev.get('episcene_required') is not True:
            continue
        pid=row['playlist_id']
        stats[pid]['confirmed_markers']+=1
        windows=ev.get('windows')
        if not isinstance(windows,list):
            stats[pid]['evidence_without_window_list']+=1
            continue
        marker_missing=False
        for w in windows:
            if not isinstance(w,dict) or w.get('origin','server')!='server':
                continue
            key=w.get('asset_key')
            if not isinstance(key,str) or not key:
                stats[pid]['bad_window_asset_key']+=1
                continue
            pair=(key,row['segment_type'])
            if pair not in available:
                missing[pid].add(pair)
                marker_missing=True
                stats[pid]['missing_references_total']+=1
                stats[pid]['missing_own_references' if key==row['asset_key']
                           else 'missing_peer_references']+=1
        if marker_missing:
            stats[pid]['confirmed_markers_affected']+=1

    all_missing=set().union(*missing.values())
    # Keep result aggregate only. Query target assets using exact key internally.
    current_playbacks=set()
    if present(db,'skip_presence') and {'playlist_id','expires_at'} <= columns(db,'skip_presence'):
        current_playbacks={r[0] for r in db.execute(
            'SELECT DISTINCT playlist_id FROM skip_presence WHERE expires_at>?',
            (int(time.time()),))}

    retry_keys=set()
    if present(db,'episcene_safe_release_retries'):
        retry_keys={r[0] for r in db.execute('SELECT asset_key FROM episcene_safe_release_retries')}
    planned={p:collections.Counter() for p in SOURCE_IDS}
    for pid in SOURCE_IDS:
        settings = db.execute('''SELECT p.archived,s.enabled AS analysis_enabled,x.enabled AS automatic_enabled
              FROM skip_analysis_playlists p
              LEFT JOIN skip_analysis_sources s ON s.playlist_id=p.id
              LEFT JOIN skip_auto_settings x ON x.playlist_id=p.id WHERE p.id=?''',(pid,)).fetchone()
        if settings is None:
            raise RuntimeError('Missing source settings: '+str(pid))
        for asset_key,kind in missing[pid]:
            target = db.execute('SELECT playlist_id FROM skip_assets WHERE asset_key=?',
                                (asset_key,)).fetchone()
            if not target:
                planned[pid]['no_registered_asset']+=1
                continue
            if target[0]!=pid:
                planned[pid]['different_analysis_playlist']+=1
                continue
            if settings['archived']!=0 or settings['analysis_enabled']!=1 or settings['automatic_enabled']!=1:
                planned[pid]['source_or_automatic_disabled']+=1
                continue
            job=db.execute('SELECT status FROM skip_jobs WHERE asset_key=?',
                           (asset_key,)).fetchone()
            if job is None:
                planned[pid]['no_job']+=1
                continue
            if job[0] in ('queued','running'):
                planned[pid]['already_queued_or_running']+=1
            elif job[0] not in RETRYABLE:
                planned[pid]['unhandled_job_status']+=1
            elif asset_key in retry_keys:
                planned[pid]['already_in_safe_retry_history']+=1
            elif pid in current_playbacks:
                planned[pid]['playback_guard_active']+=1
            else:
                planned[pid]['possible_existing_job_retry']+=1

    print('EPISCENE AUDIO-RECOVERY READINESS / NUR LESEN')
    for pid,name in ((8,'4K ANALYSE'),(10,'THE BEST')):
        print('\\n'+name)
        for k,v in sorted(stats[pid].items()):
            print('  %-39s %d'%(k,v))
        print('  %-39s %d'%('distinct_missing_asset_kind_pairs',len(missing[pid])))
        for k,v in sorted(planned[pid].items()):
            print('  %-39s %d'%(k,v))
    print('\\nDISTINCT MISSING CACHE PAIRS ALL SOURCES:',len(all_missing))
    print('READ_ONLY: no queue changes, no media requests, no worker restarts')
    print('Potential jobs still need provider limits, review, safety blocks and release verification.')


def main():
    if not DB.is_file() or DB.is_symlink():
        raise RuntimeError('Original DB missing or symlink')
    con=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=30)
    try:
        analyze(con)
    finally:
        con.close()


if __name__=='__main__':
    main()
