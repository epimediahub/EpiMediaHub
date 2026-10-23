#!/usr/bin/env python3
"""Read-only EpiScene alert age and live progress check for the Admin app.

Shows ONLY lane IDs, numeric counters and incident timestamps. No IPTV
credentials, assets, titles, client accounts, token data or stream URLs.
"""
from __future__ import annotations

from datetime import datetime,timezone
from pathlib import Path
import sqlite3,time
from zoneinfo import ZoneInfo

DATA=Path('/var/lib/epimediahub/admin-mobile')
SOURCE=Path('/var/lib/epimediahub/provisioning.db')
BERLIN=ZoneInfo('Europe/Berlin')
STATUSES=('queued','running','done','review','no_match','no_reference','partial','failed','disabled')
PROGRESS=('done','review','no_match','no_reference','partial')

def ro(path):
    if not path.is_file() or path.is_symlink():
        return None
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db

def date(value):
    if value is None:
        return '-'
    if isinstance(value,(int,float)):
        return datetime.fromtimestamp(value,BERLIN).strftime('%d.%m. %H:%M:%S')
    try:
        parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if parsed.tzinfo is None:
            parsed=parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(BERLIN).strftime('%d.%m. %H:%M:%S')
    except (TypeError,ValueError,OverflowError):
        return 'invalid'

def age(value,now):
    if value is None:
        return 'unknown'
    try:
        if isinstance(value,str):
            d=datetime.fromisoformat(value.replace('Z','+00:00'))
            if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
            seconds=int(now-d.timestamp())
        else:
            seconds=int(now-float(value))
        return str(max(seconds,0)//60)+' min'
    except (TypeError,ValueError,OverflowError):
        return 'unknown'

def alerts(now):
    print('ADMIN_ALERTS:')
    with ro(DATA/'incidents.sqlite3') as db:
        rows=db.execute("""SELECT alert_key,state,first_seen_epoch,
            last_seen_epoch,occurrences FROM admin_incidents
            WHERE alert_key IN ('analysis_stalled:8','analysis_stalled:10')
            ORDER BY first_seen_epoch DESC""").fetchall()
    if not rows:
        print('  NO_RECORDED_EPISCENE_STALL_INCIDENTS')
        return
    for row in rows:
        key=row['alert_key']
        print(' ',key,'state=',row['state'],
              'first=',date(row['first_seen_epoch']),
              'last=',date(row['last_seen_epoch']),
              'first_age=',age(row['first_seen_epoch'],now),
              'seen_times=',row['occurrences'])
    with ro(DATA/'registrations.sqlite3') as db:
        table=db.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
            AND name='admin_mobile_outbox'""").fetchone()
        if not table:
            return
        rows=db.execute("""SELECT alert_key,generation_epoch,
            MIN(sent_epoch) sent_epoch, COUNT(*) n
            FROM admin_mobile_outbox
            WHERE alert_key IN ('analysis_stalled:8','analysis_stalled:10')
            GROUP BY alert_key,generation_epoch
            ORDER BY generation_epoch DESC LIMIT 8""").fetchall()
    for row in rows:
        print('  PUSH',row['alert_key'],
              'incident_created=',date(row['generation_epoch']),
              'sent=',date(row['sent_epoch']),
              'delivery_receipt_not_proven=TRUE')

def progress(now):
    print('LIVE_ANALYSIS:')
    db=ro(SOURCE)
    if db is None:
        print('  SOURCE_DB_NOT_FOUND')
        return
    with db:
        for pid in (8,10):
            state=db.execute("""SELECT p.archived,s.enabled
               FROM skip_analysis_playlists p LEFT JOIN skip_analysis_sources s
                 ON p.id=s.playlist_id WHERE p.id=?""",(pid,)).fetchone()
            if state is None:
                print('  LANE',pid,'NOT_CONFIGURED')
                continue
            rows=db.execute("""SELECT j.status,COUNT(*) total,MAX(j.updated_at) updated
                FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
                WHERE a.playlist_id=? GROUP BY j.status""",(pid,)).fetchall()
            statuses={r['status']:r['total'] for r in rows
                      if r['status'] in STATUSES}
            last=max((r['updated'] for r in rows
                      if r['status'] in PROGRESS and r['updated']),
                     default=None)
            print('  LANE',pid,'enabled=',state['enabled']==1,
                  'archived=',state['archived']==1,
                  'queued=',statuses.get('queued',0),
                  'running=',statuses.get('running',0),
                  'failed=',statuses.get('failed',0),
                  'completed_review_total=',sum(statuses.get(s,0) for s in PROGRESS),
                  'last_completed=',date(last),
                  'minutes_since_progress=',age(last,now),
                  'monitor_threshold_minutes=15')

def main():
    now=time.time()
    print('CHECKED_BERLIN:',date(now))
    try:
        alerts(now)
    except (OSError,sqlite3.Error,TypeError,ValueError):
        print('  ADMIN_ALERTS_UNAVAILABLE')
    try:
        progress(now)
    except (OSError,sqlite3.Error,TypeError,ValueError):
        print('  ANALYSIS_PROGRESS_UNAVAILABLE')
    print('READ_ONLY=TRUE; NO_PROVIDER_REQUESTS=TRUE; NO_SECRETS_PRINTED=TRUE')

if __name__=='__main__':
    main()
