#!/usr/bin/env python3
"""EpiScene recovery: bounded 2-peer SAME-SEASON canary.

Default --plan only reads SQLite. --queue-peers atomically requeues no more
than TWO existing *review* jobs per source (4K ANALYSE / THE BEST) one time.
Normal EpiScene workers decide scheduling, provider connections and releases;
there are no direct media calls, no approvals, and no worker restarts.

Safety checks: original canary has finished and intro/outro windows exist;
target season/source matches, manual markers and blocks protected, no active
playback lease on the source, no prior canary/retry, selected jobs exactly in
review and unchanged in the UPDATE transaction. Ledger records original status.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time

DB=Path('/var/lib/epimediahub/provisioning.db')
SOURCES=((8,'4K ANALYSE'),(10,'THE BEST'))
SEED='episcene_audio_cache_canary_v1'
LEDGER='episcene_audio_peer_canary_v1'
TYPES=('intro','outro')


def schema(con, table, required):
    row=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
    if row is None:
        raise RuntimeError('Missing schema table: '+table)
    cols={r[1] for r in con.execute('PRAGMA table_info('+table+')')}
    if not required <= cols:
        raise RuntimeError('Unexpected schema of '+table)


def preflight(con):
    for table,cols in {
        SEED:{'asset_key','playlist_id','queued_at'},
        'skip_assets':{'asset_key','playlist_id','source_key','season','episode','media_type','duration_ms'},
        'skip_jobs':{'id','asset_key','status','attempts','updated_at','detail'},
        'skip_auto_windows':{'asset_key','kind'},
        'skip_records':{'asset_key','source','disabled'},
        'skip_auto_evidence':{'record_id','human_review'},
        'skip_analysis_playlists':{'id','archived'},
        'skip_analysis_sources':{'playlist_id','enabled'},
        'skip_auto_settings':{'playlist_id','enabled'},
        'skip_auto_blocks':{'asset_key','kind','duration_ms'},
        'skip_presence':{'playlist_id','expires_at'},
    }.items():
        schema(con,table,cols)
    if table_exists(con,LEDGER):
        schema(con,LEDGER,{'asset_key','playlist_id','original_status','queued_at'})
    if table_exists(con,'episcene_safe_release_retries'):
        schema(con,'episcene_safe_release_retries',{'asset_key'})


def table_exists(con,table):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (table,)).fetchone() is not None


def enabled(con,pid):
    a=con.execute('SELECT archived FROM skip_analysis_playlists WHERE id=?',(pid,)).fetchone()
    if not a or a['archived']!=0:
        return False
    for tbl in ('skip_analysis_sources','skip_auto_settings'):
        row=con.execute('SELECT enabled FROM '+tbl+' WHERE playlist_id=?',(pid,)).fetchone()
        if not row or row['enabled']!=1:
            return False
    return True


def seed(con,pid):
    rows=con.execute("""
        SELECT l.asset_key,a.source_key,a.season,a.episode,j.status
          FROM episcene_audio_cache_canary_v1 l
          JOIN skip_assets a ON a.asset_key=l.asset_key
          LEFT JOIN skip_jobs j ON j.asset_key=l.asset_key
         WHERE l.playlist_id=? AND a.playlist_id=? AND a.media_type='episode'
         ORDER BY l.queued_at""",(pid,pid)).fetchall()
    if len(rows)!=1:
        raise RuntimeError('Expected exactly one tested seed for source '+str(pid))
    r=rows[0]
    if r['status']!='no_reference':
        raise RuntimeError('Seed not in expected no_reference state for source '+str(pid))
    if not r['source_key'] or r['season'] is None or r['episode'] is None:
        raise RuntimeError('Missing seed identity')
    kinds={x[0] for x in con.execute(
        'SELECT kind FROM skip_auto_windows WHERE asset_key=?',
        (r['asset_key'],)).fetchall()}
    if not set(TYPES)<=kinds:
        raise RuntimeError('Seed is missing intro or outro cached window')
    return r


def eligible(con, pid, original, now):
    blockers=Counter()
    if not enabled(con,pid):
        blockers['source_disabled']+=1
        return [],blockers
    if con.execute('SELECT 1 FROM skip_presence WHERE playlist_id=? AND expires_at>? LIMIT 1',
                   (pid,now)).fetchone():
        blockers['playback_active']+=1
        return [],blockers
    if table_exists(con,LEDGER):
        n=con.execute('SELECT COUNT(*) FROM '+LEDGER+' WHERE playlist_id=?',(pid,)).fetchone()[0]
        if n:
            blockers['peer_canary_already_recorded']+=1
            return [],blockers
    candidates=con.execute("""
        SELECT j.id, j.asset_key, j.status,j.attempts,j.updated_at,
               a.episode,a.duration_ms
          FROM skip_assets a JOIN skip_jobs j ON j.asset_key=a.asset_key
         WHERE a.playlist_id=? AND a.source_key=? AND a.season=?
           AND a.media_type='episode' AND a.duration_ms>0
           AND a.episode<>? AND a.asset_key<>? AND j.status='review'
           AND j.attempts<3
         ORDER BY ABS(a.episode-?),a.episode,j.id""",
        (pid,original['source_key'],original['season'],original['episode'],
         original['asset_key'],original['episode'])).fetchall()
    selected=[]
    used_ep=set()
    for r in candidates:
        asset=r['asset_key']
        if r['episode'] in used_ep:
            blockers['duplicate_episode']+=1
            continue
        if con.execute('SELECT 1 FROM '+SEED+' WHERE asset_key=?',(asset,)).fetchone():
            blockers['already_original_canary']+=1
            continue
        if table_exists(con,'episcene_safe_release_retries'):
            if con.execute('SELECT 1 FROM episcene_safe_release_retries WHERE asset_key=?',(asset,)).fetchone():
                blockers['prior_safe_retry']+=1
                continue
        if con.execute("""
            SELECT 1 FROM skip_records r
            LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
            WHERE r.asset_key=? AND r.disabled=0
              AND (r.source='device' OR COALESCE(e.human_review,0)=1)
            LIMIT 1""",(asset,)).fetchone():
            blockers['manual_marker_protected']+=1
            continue
        if con.execute("""
            SELECT 1 FROM skip_auto_blocks b
            WHERE b.asset_key=? AND b.kind IN ('intro','outro')
              AND ABS(b.duration_ms-?)<=2000 LIMIT 1""",
            (asset,r['duration_ms'])).fetchone():
            blockers['safety_block']+=1
            continue
        current={x[0] for x in con.execute(
            'SELECT kind FROM skip_auto_windows WHERE asset_key=?',(asset,))}
        if set(TYPES)<=current:
            blockers['both_windows_already_present']+=1
            continue
        selected.append(r)
        used_ep.add(r['episode'])
        if len(selected)==2:
            break
    blockers['eligible_selected']=len(selected)
    if len(selected)<2:
        blockers['insufficient_safe_peers']+=1
        return [],blockers
    return selected,blockers


def run(con,queue,now):
    preflight(con)
    selections={}
    for pid,name in SOURCES:
        original=seed(con,pid)
        jobs,counts=eligible(con,pid,original,now)
        selections[pid]=jobs
        print('\n'+name)
        print('  candidate_peer_jobs:',len(jobs))
        for k,v in sorted(counts.items()):
            print('  '+k+':',v)
    print('\nMaximum 2 queued peer jobs per source, first approved canary only.')
    if not queue:
        print('PLAN_ONLY: no queue or worker changes')
        return 0
    if any(len(jobs)!=2 for jobs in selections.values()):
        print('NO_CHANGES: cannot safely prepare two peers for BOTH sources')
        return 0
    con.execute("""CREATE TABLE IF NOT EXISTS episcene_audio_peer_canary_v1(
      asset_key TEXT PRIMARY KEY,
      playlist_id INTEGER NOT NULL,
      original_status TEXT NOT NULL,
      queued_at TEXT NOT NULL)""")
    stamp=datetime.now(timezone.utc).isoformat()
    updated=[]
    for pid,_name in SOURCES:
        for row in selections[pid]:
            cur=con.execute("""
              UPDATE skip_jobs SET status='queued',attempts=0,
              detail='EpiScene kontrollierte Peer-Audiofenster-Wiederherstellung',
              updated_at=?
              WHERE id=? AND asset_key=? AND status='review' AND attempts<3
            """,(stamp,row['id'],row['asset_key']))
            if cur.rowcount!=1:
                raise RuntimeError('Peer job changed before UPDATE; rollback all')
            con.execute('INSERT INTO episcene_audio_peer_canary_v1 VALUES(?,?,?,?)',
                        (row['asset_key'],pid,row['status'],stamp))
            updated.append(pid)
    print('PEER_JOBS_QUEUED:',len(updated))
    print('BY_SOURCE:', {str(pid):updated.count(pid) for pid,_name in SOURCES})
    print('NO DIRECT MEDIA CALLS OR RELEASES; NORMAL WORKERS APPLY PROVIDER LIMITS')
    return len(updated)


def main():
    ap=argparse.ArgumentParser()
    g=ap.add_mutually_exclusive_group()
    g.add_argument('--plan',action='store_true')
    g.add_argument('--queue-peers',action='store_true')
    args=ap.parse_args()
    if DB.is_symlink() or not DB.is_file():
        raise RuntimeError('Database missing or symlink')
    # For --plan the file is opened SQLite read-only. For --queue-peers
    # all changes occur under a single immediate transaction.
    uri=DB.resolve().as_uri()+('' if args.queue_peers else '?mode=ro')
    con=sqlite3.connect(uri,uri=True,timeout=30)
    con.row_factory=sqlite3.Row
    try:
        if args.queue_peers:
            con.execute('BEGIN IMMEDIATE')
        else:
            con.execute('PRAGMA query_only=ON')
            con.execute('BEGIN')
        rows=run(con,args.queue_peers,int(time.time()))
        if args.queue_peers and rows==4:
            con.commit()
        else:
            con.rollback()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

if __name__=='__main__':
    try:
        main()
    except (RuntimeError,sqlite3.Error,TypeError,ValueError) as exc:
        print('PEER_CANARY_STOP:',type(exc).__name__,str(exc)[:200])
        raise SystemExit(1)
