#!/usr/bin/env python3
"""EpiScene queue backlog and scheduler preflight, strictly read-only.

Outputs aggregate 8/10 queue counts, job age, retry attempts, and
optional scheduler priority metadata. Never reads media streams or changes
any job, marker, worker or scheduler. No asset/customer identifiers printed.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import ast
import hashlib
import sqlite3
import subprocess

DB=Path('/var/lib/epimediahub/provisioning.db')
SCHEDULER=Path('/opt/epimediahub/provisioning/skip_schedule.py')
SOURCES=((8,'4K ANALYSE'),(10,'THE BEST'))

def columns(db, table):
    return {r[1] for r in db.execute('PRAGMA table_info('+table+')')}

def is_table(db, table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None

def updated_age(raw, now):
    if not isinstance(raw,str) or not raw:
        return 'timestamp_unknown'
    try:
        value=datetime.fromisoformat(raw.replace('Z','+00:00'))
        if value.tzinfo is None:
            value=value.replace(tzinfo=timezone.utc)
        age=(now-value).total_seconds()
    except (TypeError,ValueError,OverflowError):
        return 'timestamp_unknown'
    if age < -300:return 'timestamp_future'
    if age < 86400:return 'updated_24h'
    if age < 7*86400:return 'updated_1_to_7d'
    if age < 30*86400:return 'updated_7_to_30d'
    return 'updated_over_30d'

def service(unit):
    try:
        p=subprocess.run(['systemctl','is-active',unit],capture_output=True,text=True,timeout=5)
        return p.stdout.strip()[:22] or 'unavailable'
    except (OSError,subprocess.TimeoutExpired):
        return 'unavailable'

def scheduler_info():
    if SCHEDULER.is_symlink() or not SCHEDULER.is_file() or SCHEDULER.stat().st_size>1000000:
        return {'status':'unavailable'}
    data=SCHEDULER.read_bytes()
    try:
        tree=ast.parse(data.decode('utf-8'))
    except (UnicodeDecodeError,SyntaxError):
        return {'status':'parse_failed'}
    found=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='select_job']
    if len(found)!=1:
        return {'status':'select_job_not_unique','num_matches':len(found)}
    fn=found[0]
    text=' '.join(n.value for n in ast.walk(fn) if isinstance(n,ast.Constant) and isinstance(n.value,str))
    return {'status':'present','sha16':hashlib.sha256(data).hexdigest()[:16],
            'select_job_start_line':fn.lineno,
            'mentions_order_by':'ORDER BY' in text.upper(),
            'mentions_priority':'PRIORITY' in text.upper(),
            'mentions_limit':'LIMIT' in text.upper()}

def main():
    if DB.is_symlink() or not DB.is_file():
        raise SystemExit('STOP: production database missing or symlink')
    db=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=30)
    try:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        if not is_table(db,'skip_jobs') or not is_table(db,'skip_assets'):
            raise RuntimeError('Missing queue tables')
        required_jobs={'asset_key','status','attempts','updated_at'}
        required_assets={'asset_key','playlist_id'}
        if not required_jobs<=columns(db,'skip_jobs') or not required_assets<=columns(db,'skip_assets'):
            raise RuntimeError('Unexpected job/asset schema')
        now=datetime.now(timezone.utc)
        print('EPISCENE BACKLOG / NUR LESEN')
        for pid, name in SOURCES:
            print('\\n'+name)
            rows=db.execute('''SELECT j.status, j.attempts, j.updated_at
                FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
                WHERE a.playlist_id=?''',(pid,))
            status=Counter(); ages=Counter(); retries=Counter()
            for r in rows:
                status[str(r['status'])[:40]]+=1
                if r['status']=='queued':
                    ages[updated_age(r['updated_at'],now)]+=1
                    attempts=r['attempts']
                    retries['attempts_'+(str(attempts) if isinstance(attempts,int) and 0<=attempts<=4 else 'other')]+=1
            print('  total_jobs:',sum(status.values()))
            for k,v in sorted(status.items()):print('  status_'+k+':',v)
            print('  QUEUED_AGE_BUCKETS:')
            for k,v in sorted(ages.items()): print('    '+k+':',v)
            print('  QUEUED_ATTEMPTS:')
            for k,v in sorted(retries.items()):print('    '+k+':',v)
            if is_table(db,'skip_catalogue_priority'):
                priority_fields=columns(db,'skip_catalogue_priority')
                if {'asset_key','priority'}<=priority_fields:
                    print('  QUEUED_PRIORITIES:')
                    for r in db.execute('''SELECT COALESCE(CAST(p.priority AS TEXT),'missing') priority,COUNT(*) n
                        FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
                        LEFT JOIN skip_catalogue_priority p ON p.asset_key=j.asset_key
                        WHERE a.playlist_id=? AND j.status='queued'
                        GROUP BY p.priority ORDER BY n DESC LIMIT 12''',(pid,)):
                        print('    '+str(r['priority'])[:30]+':',r['n'])
            if is_table(db,'episcene_audio_cache_canary_v1'):
                print('  CANARY_STATUS:')
                for r in db.execute('''SELECT COALESCE(j.status,'missing_job') status,COUNT(*) n
                     FROM episcene_audio_cache_canary_v1 c
                     LEFT JOIN skip_jobs j ON j.asset_key=c.asset_key
                     WHERE c.playlist_id=? GROUP BY j.status''',(pid,)):
                    print('    '+str(r['status'])[:30]+':',r['n'])
        print('\\nSCHEDULER_STRUCTURE:',scheduler_info())
        print('ANALYSIS_TIMER:',service('epimediahub-skip-analysis.timer'))
        print('ANALYSIS_SERVICE:',service('epimediahub-skip-analysis.service'))
        print('NO JOB CHANGES. Pending backlog age reflects job updates, not original enqueue time.')
    finally:
        db.close()
if __name__=='__main__':
    main()
