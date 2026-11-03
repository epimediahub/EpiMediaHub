#!/usr/bin/env python3
"""Read-only EpiScene canary scheduler priority/focus audit; aggregate output only."""
import sqlite3
from pathlib import Path

DB=Path('/var/lib/epimediahub/provisioning.db')
LEDGER='episcene_audio_cache_canary_v1'

def exists(db,t):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone() is not None

def cols(db,t):
    return {r[1] for r in db.execute('PRAGMA table_info('+t+')')}

def focus(db,t,pid,series):
    if not exists(db,t):return 'no_table'
    if not {'playlist_id','source_key'} <= cols(db,t):return 'unknown_schema'
    row=db.execute('SELECT source_key FROM '+t+' WHERE playlist_id=? LIMIT 1',(pid,)).fetchone()
    return 'no_focus' if row is None else ('canary_series' if row['source_key']==series else 'different_series')

def main():
    if not DB.is_file() or DB.is_symlink():raise RuntimeError('DB unavailable')
    db=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=25)
    try:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        for t,req in {
            LEDGER:{'asset_key','playlist_id','queued_at'},
            'skip_jobs':{'asset_key','status','updated_at','attempts','id'},
            'skip_assets':{'asset_key','playlist_id','source_key'},
            'skip_catalogue_priority':{'asset_key','priority'}
        }.items():
            if not exists(db,t) or not req <= cols(db,t):
                raise RuntimeError('Missing/changed schema: '+t)
        print('EPISCENE CANARY SCHEDULER RANK / NUR LESEN')
        print('Initial ORDER BY estimate only; language stage and series focus may override.')
        for pid,name in ((8,'4K ANALYSE'),(10,'THE BEST')):
            print('\\n'+name)
            rows=db.execute("""
                SELECT l.asset_key,a.source_key,j.id,j.status,j.attempts,j.updated_at,
                       p.priority AS explicit_priority,COALESCE(p.priority,1) AS effective_priority
                FROM episcene_audio_cache_canary_v1 l
                JOIN skip_assets a ON a.asset_key=l.asset_key
                LEFT JOIN skip_jobs j ON j.asset_key=l.asset_key
                LEFT JOIN skip_catalogue_priority p ON p.asset_key=l.asset_key
                WHERE l.playlist_id=? ORDER BY l.queued_at""",(pid,)).fetchall()
            print('  canary_count:',len(rows))
            for i,r in enumerate(rows,1):
                print('  canary_'+str(i)+'_status:',r['status'] or 'missing')
                if r['id'] is None:continue
                print('  attempts:',r['attempts'])
                print('  explicit_priority:',r['explicit_priority'] if r['explicit_priority'] is not None else 'missing')
                print('  effective_priority:',r['effective_priority'])
                if r['status']=='queued' and type(r['attempts']) is int and r['attempts']<3:
                    ahead=db.execute("""
                      SELECT COUNT(*) FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
                      LEFT JOIN skip_catalogue_priority p ON p.asset_key=j.asset_key
                      WHERE a.playlist_id=? AND j.status='queued' AND j.attempts<3
                        AND (COALESCE(p.priority,1)<? OR
                            (COALESCE(p.priority,1)=? AND
                             (j.updated_at<? OR (j.updated_at=? AND j.id<?))))""",
                      (pid,r['effective_priority'],r['effective_priority'],
                       r['updated_at'],r['updated_at'],r['id'])).fetchone()[0]
                    print('  estimated_jobs_ahead_initial_sort:',ahead)
                print('  serial_focus:',focus(db,'skip_schedule_focus',pid,r['source_key']))
                print('  parallel_focus:',focus(db,'skip_parallel_focus',pid,r['source_key']))
                if exists(db,'skip_language_priority'):
                    langcols=cols(db,'skip_language_priority')
                    if 'asset_key' in langcols:
                        lr=db.execute('SELECT * FROM skip_language_priority WHERE asset_key=?',
                                      (r['asset_key'],)).fetchone()
                        print('  language_entry:',bool(lr))
                        if lr is not None:
                            for f in ('stage','language_stage','priority'):
                                if f in langcols:
                                    print('  language_'+f+':',str(lr[f])[:30])
            print('  queue_by_effective_priority:')
            for v in db.execute("""
              SELECT COALESCE(p.priority,1) pr,COUNT(*) n
              FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
              LEFT JOIN skip_catalogue_priority p ON p.asset_key=j.asset_key
              WHERE a.playlist_id=? AND j.status='queued' AND j.attempts<3
              GROUP BY COALESCE(p.priority,1) ORDER BY pr LIMIT 10""",(pid,)):
                print('    '+str(v['pr'])+':',v['n'])
        print('\\nNo DB changes, no worker imports, no media requests.')
    finally:
        db.close()

if __name__=='__main__':
    try:main()
    except (RuntimeError,sqlite3.Error) as e:
        print('AUDIT_STOP:',type(e).__name__,str(e))
        raise SystemExit(1)
