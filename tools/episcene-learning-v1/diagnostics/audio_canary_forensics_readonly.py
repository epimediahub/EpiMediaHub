#!/usr/bin/env python3
"""EpiScene audio recovery canary forensics — strictly read-only, no imports.

Show whether each canary's intro/outro window was saved since it was queued,
its current job status, and number of other cached episodes in same
analysis playlist, series and season. No customer data or provider details.
"""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

DB = Path('/var/lib/epimediahub/provisioning.db')
LEDGER = 'episcene_audio_cache_canary_v1'

def stamp(value):
    if isinstance(value, (int,float)) and not isinstance(value,bool):
        v=float(value)
        return v/1000 if v>100000000000 else v
    if not isinstance(value,str) or not value.strip():
        return None
    try:
        return stamp(float(value))
    except ValueError:
        pass
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        if dt.tzinfo is None:
            dt=dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError,OverflowError):
        return None

def chronology(t,queued):
    t=stamp(t)
    queued=stamp(queued)
    if t is None or queued is None:
        return 'UNKNOWN_TIMESTAMP_FORMAT'
    return 'AFTER_QUEUE' if t>=queued-2 else 'BEFORE_QUEUE'

def table(con,name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None

def cols(con,name):
    return {r[1] for r in con.execute('PRAGMA table_info('+name+')')}

def main():
    if DB.is_symlink() or not DB.is_file():
        raise SystemExit('STOP: DB missing/unsafe')
    con=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=20)
    con.row_factory=sqlite3.Row
    try:
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')
        if not table(con,LEDGER):
            print('NO_CANARY_LEDGER; no DB modifications')
            return
        required={
            LEDGER:{'asset_key','playlist_id','original_status','queued_at'},
            'skip_jobs':{'asset_key','status','updated_at'},
            'skip_assets':{'asset_key','playlist_id','source_key','season','episode'},
            'skip_auto_windows':{'asset_key','kind','created_at'}
        }
        if any(not table(con,t) or not need <= cols(con,t) for t,need in required.items()):
            raise RuntimeError('Schema mismatch; no changes')
        rows=con.execute('''
            SELECT l.asset_key,l.playlist_id,l.original_status,l.queued_at,
                   j.status job_status,j.updated_at job_updated,
                   a.source_key,a.season,a.episode
            FROM episcene_audio_cache_canary_v1 l
            LEFT JOIN skip_jobs j ON j.asset_key=l.asset_key
            LEFT JOIN skip_assets a ON a.asset_key=l.asset_key
            WHERE l.playlist_id IN (8,10)
            ORDER BY l.playlist_id,l.queued_at
        ''').fetchall()
        print('EPISCENE AUDIO CANARY FORENSICS / NUR LESEN')
        print('AFTER_QUEUE shows cache write chronology, not proof of valid fingerprint or release.')
        print('No job edits, service actions, provider calls or raw identifiers.')
        for pid,label in ((8,'4K ANALYSE'),(10,'THE BEST')):
            matching=[r for r in rows if r['playlist_id']==pid]
            print('\n'+label)
            print('  recorded_canaries:',len(matching))
            for i,r in enumerate(matching,1):
                print('  Canary',i)
                print('    job_status:',r['job_status'] or 'MISSING')
                print('    job_updated:',chronology(r['job_updated'],r['queued_at']))
                for kind in ('intro','outro'):
                    window=con.execute('''SELECT created_at FROM skip_auto_windows
                          WHERE asset_key=? AND kind=? ORDER BY created_at DESC LIMIT 1''',
                          (r['asset_key'],kind)).fetchone()
                    print('    '+kind+'_cache:', 'MISSING' if window is None else
                          chronology(window['created_at'],r['queued_at']))
                    if r['source_key'] is not None and r['season'] is not None:
                        peer=con.execute('''SELECT COUNT(DISTINCT a.episode)
                          FROM skip_auto_windows w JOIN skip_assets a ON a.asset_key=w.asset_key
                          WHERE a.playlist_id=? AND a.source_key=? AND a.season=?
                            AND a.asset_key<>? AND w.kind=?''',
                            (pid,r['source_key'],r['season'],r['asset_key'],kind)).fetchone()[0]
                        print('    '+kind+'_other_cached_episodes_same_season:',peer)
        print('\nTotal audio cache windows:',
              con.execute('SELECT COUNT(*) FROM skip_auto_windows').fetchone()[0])
        print('NOTE: Job no_reference can have several causes; peer coverage alone is not a diagnosis.')
    finally:
        con.close()

if __name__=='__main__':
    main()
