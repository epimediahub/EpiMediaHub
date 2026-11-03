#!/usr/bin/env python3
"""EpiScene canary versus active scheduler series focus; strictly read-only.

Explains if existing parallel focus has queued work and if the recovery
canary shares its series. Does not change a focus, queue, workers or
permissions, import production code, or output any series identifiers.
"""
import sqlite3
from pathlib import Path

DB=Path('/var/lib/epimediahub/provisioning.db')
LEDGER='episcene_audio_cache_canary_v1'

def schema(db,t,required):
    exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone()
    if not exists: raise RuntimeError('missing table '+t)
    cols={r[1] for r in db.execute('PRAGMA table_info('+t+')')}
    if not required<=cols:raise RuntimeError('changed schema '+t)

def main():
    if DB.is_symlink() or not DB.is_file():
        raise RuntimeError('Original DB unavailable or symlink')
    db=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=25)
    db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        for t,fields in {
            LEDGER:{'asset_key','playlist_id'},
            'skip_assets':{'asset_key','playlist_id','source_key','media_type'},
            'skip_jobs':{'asset_key','status','attempts'},
            'skip_parallel_focus':{'playlist_id','source_key'}
        }.items():
            schema(db,t,fields)
        print('EPISCENE FOCUS & CANARY QUEUE / NUR LESEN')
        print('No raw episode keys, customer info, queue writes or provider requests.')
        for pid,name in ((8,'4K ANALYSE'),(10,'THE BEST')):
            print('\\n'+name)
            canaries=db.execute("""SELECT a.source_key,j.status,j.attempts
                  FROM episcene_audio_cache_canary_v1 c
                  JOIN skip_assets a ON a.asset_key=c.asset_key
                  LEFT JOIN skip_jobs j ON j.asset_key=c.asset_key
                  WHERE c.playlist_id=? ORDER BY c.queued_at""",(pid,)).fetchall()
            focus=db.execute("SELECT source_key FROM skip_parallel_focus WHERE playlist_id=? LIMIT 1",(pid,)).fetchone()
            print('  canary_job_count:',len(canaries))
            print('  focus_state:', 'absent' if focus is None else 'present')
            if focus is not None:
                status=db.execute("""SELECT j.status,COUNT(*) n
                    FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
                    WHERE a.playlist_id=? AND a.source_key=? AND a.media_type='episode'
                      AND j.attempts<3
                    GROUP BY j.status""",(pid,focus['source_key'])).fetchall()
                for r in status:
                    print('  focus_series_'+str(r['status'])[:20]+':',r['n'])
                queued=db.execute("""SELECT COUNT(*) FROM skip_jobs j
                    JOIN skip_assets a ON a.asset_key=j.asset_key
                    WHERE a.playlist_id=? AND a.source_key=? AND a.media_type='episode'
                      AND j.status='queued' AND j.attempts<3""",(pid,focus['source_key'])).fetchone()[0]
                print('  focus_has_eligible_queued_episode:',queued>0)
            for i,r in enumerate(canaries,1):
                print('  canary_'+str(i)+'_status:',r['status'] or 'unknown')
                print('  canary_'+str(i)+'_is_focus_series:',
                    'no_active_focus' if focus is None else (r['source_key']==focus['source_key']))
        print('\\nFocus ownership alone cannot prove which job select_job() chooses; language stage and requests also matter.')
        print('NO CHANGES PERFORMED.')
    finally:db.close()

if __name__=='__main__':
    try:main()
    except (RuntimeError,sqlite3.Error) as e:
        print('FOCUS_AUDIT_STOP:',type(e).__name__,str(e))
        raise SystemExit(1)
