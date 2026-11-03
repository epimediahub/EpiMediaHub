#!/usr/bin/env python3
"""EpiScene audio-recovery cohort preflight; READ-ONLY and identity-free.

Reports canary-series inventory, existing cached audio-window peer coverage,
eligible job status inventory, source queue depth and worker timer state.
Does not import worker code, download streams or change DB.
"""
from collections import Counter
from pathlib import Path
import sqlite3
import subprocess

DB = Path('/var/lib/epimediahub/provisioning.db')
LEDGER = 'episcene_audio_cache_canary_v1'

def cols(db,table):
    return {x[1] for x in db.execute('PRAGMA table_info('+table+')')}

def check(db):
    for name,expected in {
        LEDGER: {'asset_key','playlist_id','queued_at'},
        'skip_assets': {'asset_key','playlist_id','source_key','season','episode','media_type','duration_ms'},
        'skip_jobs': {'asset_key','status'},
        'skip_auto_windows': {'asset_key','kind'},
        'skip_analysis_playlists': {'id','archived'},
        'skip_auto_settings': {'playlist_id','enabled'},
        'skip_analysis_sources': {'playlist_id','enabled'},
    }.items():
        if not expected <= cols(db,name):
            raise RuntimeError('Unexpected DB schema: '+name)

def status(unit):
    try:
        r=subprocess.run(['systemctl','is-active',unit],
                         capture_output=True,text=True,timeout=6,check=False)
        s=r.stdout.strip()
        return s if s in ('active','inactive','failed','activating','deactivating') else 'unavailable'
    except (OSError,subprocess.TimeoutExpired):
        return 'unavailable'

def report():
    if DB.is_symlink() or not DB.is_file():
        raise RuntimeError('DB unavailable / symlink')
    db=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=20)
    try:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        check(db)
        rows=db.execute('''SELECT l.asset_key,l.playlist_id,a.source_key,a.season,a.episode,
                                  j.status job_status
                          FROM episcene_audio_cache_canary_v1 l
                          JOIN skip_assets a ON a.asset_key=l.asset_key
                          LEFT JOIN skip_jobs j ON j.asset_key=l.asset_key
                          WHERE l.playlist_id IN (8,10)
                          ORDER BY l.playlist_id,l.queued_at''').fetchall()
        print('EPISCENE AUDIO PEER GROUP PREFLIGHT / READ ONLY')
        print('No identifiers, no jobs queued, no modifications, no provider calls.')
        for pid,title in ((8,'4K ANALYSE'),(10,'THE BEST')):
            queue=db.execute('''SELECT j.status, COUNT(DISTINCT j.asset_key)
                FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
                WHERE a.playlist_id=? AND j.status IN ('queued','running')
                GROUP BY j.status''',(pid,)).fetchall()
            queues={r[0]:r[1] for r in queue}
            print('\\n'+title)
            print('  source_queued_jobs:',queues.get('queued',0))
            print('  source_running_jobs:',queues.get('running',0))
            seeds=[r for r in rows if r['playlist_id']==pid]
            print('  recorded_canary_jobs:',len(seeds))
            for index,seed in enumerate(seeds,1):
                print('  Canary',index)
                print('    current_job_status:',seed['job_status'] or 'MISSING')
                family=db.execute('''SELECT a.asset_key,a.episode,j.status
                   FROM skip_assets a LEFT JOIN skip_jobs j ON j.asset_key=a.asset_key
                   WHERE a.playlist_id=? AND a.source_key=? AND a.season=?
                     AND a.media_type='episode' AND a.duration_ms>0''',
                   (pid,seed['source_key'],seed['season'])).fetchall()
                unique_episodes=len({x['episode'] for x in family})
                print('    available_same_season_episodes:',unique_episodes)
                print('    other_same_season_episodes:',len({x['episode'] for x in family if x['episode']!=seed['episode']}))
                print('    other_job_status_counts:')
                statuscounts=Counter(x['status'] or 'no_job' for x in family if x['asset_key']!=seed['asset_key'])
                for label,number in sorted(statuscounts.items()):
                    print('      '+str(label)[:22]+':',number)
                for kind in ('intro','outro'):
                    n=db.execute('''SELECT COUNT(DISTINCT a.episode)
                        FROM skip_auto_windows w JOIN skip_assets a ON a.asset_key=w.asset_key
                        WHERE a.playlist_id=? AND a.source_key=? AND a.season=?
                          AND a.asset_key<>? AND w.kind=?''',
                        (pid,seed['source_key'],seed['season'],seed['asset_key'],kind)).fetchone()[0]
                    print('    '+kind+'_distinct_cached_peer_episodes:',n)
                print('    same_series_has_3_episodes:',unique_episodes>=3)
        print('\\nAnalysis service:',status('epimediahub-skip-analysis.service'))
        print('Analysis timer:',status('epimediahub-skip-analysis.timer'))
        print('This is a cohort assessment, not a guarantee of a new audio match.')
    finally:
        db.close()

if __name__=='__main__':
    try: report()
    except (sqlite3.Error,RuntimeError,OSError) as ex:
        print('PREFLIGHT_STOP:',type(ex).__name__,str(ex))
        raise SystemExit(1)
