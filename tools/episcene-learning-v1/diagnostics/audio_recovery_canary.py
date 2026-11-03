#!/usr/bin/env python3
"""EpiScene: strictly bounded recovery canary for missing V3 audio-cache windows.

Default --plan is READ-ONLY. --queue-canary changes at most ONE existing analysis
job per source (8,10), never approves markers, contacts providers, or starts
services. The normal scheduler remains responsible for playback/concurrency.

Run once, then observe audio cache and job outcomes before any broader recovery.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time

DB = Path('/var/lib/epimediahub/provisioning.db')
SOURCES = (8,10)
RETRYABLE = ('done','review','no_match','no_reference','partial')
MACHINE = ('audio','audio_repetition','auto_audio','episcene','theintrodb','chapter')
LEDGER = 'episcene_audio_cache_canary_v1'

def parse(raw):
    try:
        v = json.loads(raw or '{}')
        return v if isinstance(v,dict) else {}
    except (TypeError,ValueError):
        return {}

def columns(con,table):
    return {r[1] for r in con.execute('PRAGMA table_info('+table+')')}

def exists(con,table):
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone() is not None

def verify_schema(con):
    for table,required in {
        'skip_records':{'id','asset_key','source','status','segment_type','season','episode',
                        'source_key','media_type','duration_ms','disabled'},
        'skip_assets':{'asset_key','playlist_id','source_key','season','episode','media_type','duration_ms'},
        'skip_auto_evidence':{'record_id','evidence_json','human_review'},
        'skip_auto_windows':{'asset_key','kind'},
        'skip_jobs':{'id','asset_key','status','attempts','detail','updated_at'},
        'skip_analysis_sources':{'playlist_id','enabled'},
        'skip_analysis_playlists':{'id','archived'},
        'skip_auto_settings':{'playlist_id','enabled'},
        'skip_release_settings':{'playlist_id','enabled'},
        'skip_auto_blocks':{'asset_key','kind','duration_ms'},
        'skip_presence':{'playlist_id','expires_at'},
    }.items():
        if not exists(con,table) or not required <= columns(con,table):
            raise RuntimeError('Unknown database schema: '+table)
    if exists(con,LEDGER):
        required={'asset_key','playlist_id','original_status','queued_at'}
        if not required <= columns(con,LEDGER):
            raise RuntimeError('Unknown canary ledger schema')

def source_enabled(con,pid):
    p = con.execute("SELECT * FROM skip_analysis_playlists WHERE id=?",(pid,)).fetchone()
    if p is None or p['archived'] != 0:
        return False
    if 'enabled' in p.keys() and p['enabled'] != 1:
        return False
    if 'active' in p.keys() and p['active'] != 1:
        return False
    if 'paused' in p.keys() and p['paused'] == 1:
        return False
    for table in ('skip_analysis_sources','skip_auto_settings'):
        r=con.execute('SELECT enabled FROM '+table+' WHERE playlist_id=?',(pid,)).fetchone()
        if r is None or r['enabled'] != 1:
            return False
    # Production release settings default to enabled when no override exists.
    release=con.execute('SELECT enabled FROM skip_release_settings WHERE playlist_id=?',
                        (pid,)).fetchone()
    if release is not None and release['enabled'] != 1:
        return False
    return True

def source_busy(con,pid,now):
    if con.execute('SELECT 1 FROM skip_presence WHERE playlist_id=? AND expires_at>? LIMIT 1',
                   (pid,now)).fetchone():
        return 'playback_active'
    # Existing scheduler/worker guards remain responsible for serial
    # provider access; adding a queued DB row never starts a stream itself.
    return None

def candidates(con,now):
    available=set(tuple(r) for r in con.execute('SELECT asset_key,kind FROM skip_auto_windows'))
    blockers={p:Counter() for p in SOURCES}
    needs=defaultdict(set)
    source_missing={p:set() for p in SOURCES}
    sql="""SELECT r.asset_key,r.source_key,r.season,r.episode,
                  r.segment_type,r.source,r.duration_ms,
                  e.evidence_json,a.playlist_id
           FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
           LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
           WHERE r.status='pending' AND a.playlist_id IN (8,10)
             AND r.source IN ('audio','audio_repetition','auto_audio','episcene','theintrodb','chapter')
             AND r.media_type='episode' AND a.media_type='episode'
             AND a.source_key=r.source_key AND a.season=r.season
             AND a.episode=r.episode AND ABS(a.duration_ms-r.duration_ms)<=2000"""
    for row in con.execute(sql):
        ev=parse(row['evidence_json'])
        if (ev.get('status')!='AUTO_CONFIRMED'
            or ev.get('episcene_required') is not True
            or ev.get('method')=='episcene_consensus'
            or ev.get('audio_visual_disagreement') is True):
            continue
        windows=ev.get('windows')
        if not isinstance(windows,list):
            continue
        pid=row['playlist_id']
        for item in windows:
            if (not isinstance(item,dict) or item.get('origin','server')!='server'
                    or not isinstance(item.get('asset_key'),str)):
                continue
            asset=item['asset_key']
            pair=(asset,row['segment_type'])
            if pair in available:
                continue
            # Never cross unrelated series, seasons, or source playists.
            target=con.execute(
                "SELECT playlist_id,source_key,season,episode,duration_ms FROM skip_assets WHERE asset_key=?",
                (asset,)).fetchone()
            if target is None:
                blockers[pid]['missing_registry_asset']+=1
                continue
            if (target['playlist_id']!=pid or target['source_key']!=row['source_key']
                    or target['season']!=row['season']):
                blockers[pid]['different_family']+=1
                continue
            needs[(pid,asset)].add(row['segment_type'])
            source_missing[pid].add(pair)
    for pid in SOURCES:
        blockers[pid]['distinct_missing_references']=len(source_missing[pid])
    chosen={pid:[] for pid in SOURCES}
    if exists(con,LEDGER):
        ledger={r[0] for r in con.execute('SELECT asset_key FROM '+LEDGER)}
        today=datetime.now(timezone.utc).date().isoformat()
        daily={pid:con.execute('SELECT COUNT(*) FROM '+LEDGER+
            ' WHERE playlist_id=? AND substr(queued_at,1,10)=?', (pid,today)).fetchone()[0]
            for pid in SOURCES}
    else:
        ledger=set()
        daily={pid:0 for pid in SOURCES}
    if exists(con,'episcene_safe_release_retries'):
        prior={r[0] for r in con.execute('SELECT asset_key FROM episcene_safe_release_retries')}
    else:
        prior=set()
    for pid in SOURCES:
        if not source_enabled(con,pid):
            blockers[pid]['disabled_source']+=1
            continue
        busy=source_busy(con,pid,now)
        if busy:
            blockers[pid][busy]+=1
            continue
        if daily[pid] >= 1:
            blockers[pid]['already_canaried_today']+=1
            continue
        ranked=[]
        for (p,asset),kinds in needs.items():
            if p!=pid:
                continue
            if asset in ledger or asset in prior:
                blockers[pid]['already_retried']+=1
                continue
            records=con.execute(
                "SELECT id,status,updated_at FROM skip_jobs WHERE asset_key=?",
                (asset,)).fetchall()
            if len(records)!=1:
                blockers[pid]['ambiguous_job']+=1
                continue
            job=records[0]
            if job['status'] not in RETRYABLE:
                blockers[pid]['busy_or_unsupported_job_status']+=1
                continue
            # Avoid any manual correction or actively disputed marker.
            protected=con.execute("""
                SELECT 1 FROM skip_records r
                LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
                WHERE r.asset_key=? AND r.disabled=0
                  AND (r.source='device' OR COALESCE(e.human_review,0)=1)
                LIMIT 1""",(asset,)).fetchone()
            if protected:
                blockers[pid]['human_marker_protected']+=1
                continue
            if con.execute("""
                SELECT 1 FROM skip_auto_blocks b JOIN skip_assets a ON a.asset_key=b.asset_key
                WHERE b.asset_key=? AND b.kind IN (%s)
                  AND ABS(b.duration_ms-a.duration_ms)<=2000
                LIMIT 1""" % (','.join('?' for _ in kinds)),
                (asset,*sorted(kinds))).fetchone():
                blockers[pid]['explicit_safety_block']+=1
                continue
            ranked.append((-len(kinds), 0 if job['status'] in ('done','review') else 1,
                           str(job['updated_at'] or ''), job['id'], asset, job['status'],tuple(sorted(kinds))))
        ranked.sort(key=lambda x:(x[0],x[1],x[2],x[3]))
        blockers[pid]['eligible_distinct_assets']=len(ranked)
        if ranked:
            chosen[pid]=[ranked[0]]
    return chosen,blockers

def execute(con, apply, now):
    verify_schema(con)
    selected,blockers=candidates(con,now)
    print('EPISCENE AUDIO CACHE CANARY / '+('QUEUE' if apply else 'READ_ONLY PLAN'))
    print('Maximum: one existing job per source, once/day. No direct media requests.')
    for pid,name in ((8,'4K ANALYSE'),(10,'THE BEST')):
        print('\n'+name)
        print('  eligible_asset_jobs:',blockers[pid]['eligible_distinct_assets'])
        print('  planned_canary_jobs:',len(selected[pid]))
        print('  planned_segment_types:',
              ','.join(selected[pid][0][-1]) if selected[pid] else '-')
        for k,n in sorted(blockers[pid].items()):
            if k!='eligible_distinct_assets':
                print('  %-37s %d' % (k,n))
    if not apply:
        print('READ_ONLY: database unchanged, no jobs queued')
        return 0
    jobs=[(pid,row) for pid in SOURCES for row in selected[pid]]
    if not jobs:
        print('NOTHING_QUEUED: no safe canary candidate at this time')
        return 0
    con.execute('''CREATE TABLE IF NOT EXISTS episcene_audio_cache_canary_v1(
        asset_key TEXT PRIMARY KEY, playlist_id INTEGER NOT NULL,
        original_status TEXT NOT NULL,queued_at TEXT NOT NULL)''')
    stamp=datetime.now(timezone.utc).isoformat()
    queued=[]
    for pid,item in jobs:
        _,_,_,job_id,asset,old,kinds=item
        cur=con.execute("""UPDATE skip_jobs SET status='queued',attempts=0,
                        detail='Gezielter EpiScene Audiocache-Wiederherstellungstest',
                        updated_at=? WHERE id=? AND asset_key=? AND status=?""",
                        (stamp,job_id,asset,old))
        if cur.rowcount!=1:
            raise RuntimeError('Job changed while scheduling; rollback all')
        con.execute('INSERT INTO episcene_audio_cache_canary_v1 VALUES(?,?,?,?)',
                    (asset,pid,old,stamp))
        queued.append(pid)
    print('CANARY_QUEUED_ATOMICALLY:',len(queued),
          'by_analysis_source:',{str(pid):queued.count(pid) for pid in SOURCES})
    print('Existing normal scheduler will handle later analysis; no immediate downloads or approvals.')
    return len(queued)

def main():
    p=argparse.ArgumentParser()
    group=p.add_mutually_exclusive_group()
    group.add_argument('--plan',action='store_true')
    group.add_argument('--queue-canary',action='store_true')
    args=p.parse_args()
    if DB.is_symlink() or not DB.is_file():
        raise RuntimeError('Unknown or missing production DB')
    now=int(time.time())
    con=sqlite3.connect(DB.resolve().as_uri()+('' if args.queue_canary else '?mode=ro'),
                        uri=True,timeout=20)
    con.row_factory=sqlite3.Row
    try:
        if args.queue_canary:
            con.execute('BEGIN IMMEDIATE')
        else:
            con.execute('PRAGMA query_only=ON')
            con.execute('BEGIN')
        result=execute(con,args.queue_canary,now)
        if args.queue_canary and result:
            con.commit()
        else:
            con.rollback()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

if __name__=='__main__':
    try: main()
    except (RuntimeError,sqlite3.Error,ValueError,TypeError) as exc:
        print('CANARY_STOP: '+str(exc))
        raise SystemExit(1)
