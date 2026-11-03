#!/usr/bin/env python3
"""EpiScene: read-only status of the four same-season audio peer canary jobs.

Reports statuses, cache creation relative to queue time, and count of other
episodes with intro/outro windows in original canary's season.
No raw asset identifiers, series, customer data or provider URLs printed.
No marker changes, jobs, requests or worker imports.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

DB=Path('/var/lib/epimediahub/provisioning.db')
PEERS='episcene_audio_peer_canary_v1'
ORIGINAL='episcene_audio_cache_canary_v1'

def get_cols(con,t):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone():
        raise RuntimeError('Expected table missing: '+t)
    return {r[1] for r in con.execute('PRAGMA table_info('+t+')')}

def seconds(value):
    if type(value) in (int,float):
        return float(value)/1000 if value>1e11 else float(value)
    if isinstance(value,str):
        try: return seconds(float(value))
        except ValueError: pass
        try:
            dt=datetime.fromisoformat(value.replace('Z','+00:00'))
            return dt.replace(tzinfo=dt.tzinfo or timezone.utc).timestamp()
        except (ValueError,OverflowError): pass
    return None

def relative(stamp,queued):
    a,b=seconds(stamp),seconds(queued)
    if a is None or b is None:
        return 'timestamp_unknown'
    return 'after_queue' if a>=b-2 else 'before_queue'

def main():
    if DB.is_symlink() or not DB.is_file():
        raise RuntimeError('Missing or symlink production DB')
    db=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=30)
    db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        required={
            PEERS:{'asset_key','playlist_id','queued_at'},
            ORIGINAL:{'asset_key','playlist_id','queued_at'},
            'skip_jobs':{'asset_key','status'},
            'skip_auto_windows':{'asset_key','kind','created_at'},
            'skip_assets':{'asset_key','playlist_id','source_key','season','episode'}
        }
        for t,cols in required.items():
            if not cols<=get_cols(db,t):
                raise RuntimeError('Unexpected schema: '+t)
        print('EPISCENE AUDIO PEER CANARY / READ ONLY')
        print('Cache presence is NOT a fingerprint match or automatic approval.')
        for pid,name in ((8,'4K ANALYSE'),(10,'THE BEST')):
            print('\n'+name)
            peers=db.execute("""
                SELECT p.asset_key,p.queued_at,j.status FROM episcene_audio_peer_canary_v1 p
                LEFT JOIN skip_jobs j ON j.asset_key=p.asset_key
                WHERE p.playlist_id=? ORDER BY p.queued_at,p.asset_key""",(pid,)).fetchall()
            print('  peer_jobs:',len(peers))
            by_status=Counter(p['status'] or 'missing' for p in peers)
            for state,count in sorted(by_status.items()):
                print('  status_'+str(state)[:25]+':',count)
            for kind in ('intro','outro'):
                counter=Counter()
                for peer in peers:
                    row=db.execute("""SELECT created_at FROM skip_auto_windows
                        WHERE asset_key=? AND kind=? ORDER BY created_at DESC LIMIT 1""",
                        (peer['asset_key'],kind)).fetchone()
                    counter['missing' if not row else relative(row['created_at'],peer['queued_at'])]+=1
                for state,count in sorted(counter.items()):
                    print('  '+kind+'_'+state+':',count)
            seed=db.execute("""
                SELECT a.asset_key,a.source_key,a.season
                FROM episcene_audio_cache_canary_v1 c
                JOIN skip_assets a ON a.asset_key=c.asset_key
                WHERE c.playlist_id=? ORDER BY c.queued_at DESC LIMIT 1""",(pid,)).fetchone()
            if not seed:
                print('  original_canary:missing')
                continue
            for kind in ('intro','outro'):
                count=db.execute("""SELECT COUNT(DISTINCT a.episode)
                    FROM skip_auto_windows w JOIN skip_assets a ON a.asset_key=w.asset_key
                    WHERE a.playlist_id=? AND a.source_key=? AND a.season=?
                    AND a.asset_key<>? AND w.kind=?""",
                    (pid,seed['source_key'],seed['season'],seed['asset_key'],kind)).fetchone()[0]
                print('  '+kind+'_other_cached_episodes_same_season:',count)
        print('\nTOTAL_CACHE_WINDOWS:',db.execute('SELECT COUNT(*) FROM skip_auto_windows').fetchone()[0])
        print('NO CHANGES OR NETWORK MEDIA REQUESTS')
    finally:
        db.close()

if __name__=='__main__':
    try:main()
    except (sqlite3.Error,RuntimeError,TypeError,ValueError) as exc:
        print('PEER_STATUS_STOP:',type(exc).__name__,str(exc)[:160])
        raise SystemExit(1)
