#!/usr/bin/env python3
"""Read-only EpiScene report: are the known THE BEST HTTP 405 failures old?

Never prints stream URLs, provider names, job details, account identifiers,
asset keys or private record IDs. Does not make provider requests or writes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import sqlite3
from zoneinfo import ZoneInfo

DB=Path('/var/lib/epimediahub/provisioning.db')
TZ=ZoneInfo('Europe/Berlin')
# Matching a known, previously disclosed fixed error string by hash; no raw
# job details are exposed. Any other HTTP 405 wording remains uncounted.
EXPECTED_405_HASH=hashlib.sha256(
    'Anbieter meldet HTTP 405; eigene Zeitmarken bleiben nutzbar'.encode()).hexdigest()
DISPLAY_STATES=('failed','done','review','partial','no_match','no_reference')
WATCH=(8,10)

def when(value):
    if value is None:return None
    try:
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    except (ValueError,TypeError):return None
    # The worker's now() stores UTC; a naive timestamp is treated as UTC.
    if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def summarize(db,now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError('now must be timezone aware')
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    cols=lambda name:{r[1] for r in db.execute('PRAGMA table_info('+name+')')}
    if not {'asset_key','playlist_id'}.issubset(cols('skip_assets')) or not {
      'asset_key','status','detail','updated_at'}.issubset(cols('skip_jobs')):
        raise RuntimeError('Unexpected skip_jobs/skip_assets schema')
    latest=defaultdict(dict)
    last72=defaultdict(Counter)
    last24=defaultdict(Counter)
    matching=[]
    unknown_dates=Counter()
    for r in db.execute('''SELECT a.playlist_id,j.status,j.updated_at,j.detail
          FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
          WHERE a.playlist_id IN (8,10)
            AND j.status IN ('failed','done','review','partial','no_match','no_reference')'''):
        pid=r['playlist_id']; status=r['status']; dt=when(r['updated_at'])
        if dt is None:
            unknown_dates[(pid,status)]+=1
        else:
            if status not in latest[pid] or dt>latest[pid][status]:
                latest[pid][status]=dt
            if now-timedelta(hours=72)<=dt<=now+timedelta(minutes=5):
                last72[pid][status]+=1
            if now-timedelta(hours=24)<=dt<=now+timedelta(minutes=5):
                last24[pid][status]+=1
        if pid==10 and status=='failed' and hashlib.sha256(
                str(r['detail'] or '').encode()).hexdigest()==EXPECTED_405_HASH:
            matching.append(dt)
    dated=[t for t in matching if t]
    recent={label:sum(t is not None and now-timedelta(hours=hours)<=t<=now+timedelta(minutes=5) for t in matching)
            for label,hours in [('1h',1),('3h',3),('24h',24),('72h',72)]}
    days=Counter(t.astimezone(TZ).strftime('%Y-%m-%d') for t in dated)
    stamp=lambda v:v.astimezone(TZ).strftime('%Y-%m-%d %H:%M:%S %Z') if v else None
    return {
      'mode':'EPISCENE_405_AGE_READ_ONLY',
      'checked_at_local':stamp(now),
      'the_best_405_still_failed_rows':len(matching),
      'the_best_405_earliest_last_update':stamp(min(dated)) if dated else None,
      'the_best_405_latest_last_update':stamp(max(dated)) if dated else None,
      'the_best_405_missing_or_invalid_timestamps':len(matching)-len(dated),
      'the_best_405_updated_within':recent,
      'the_best_405_failed_rows_by_local_day':dict(sorted(days.items(),reverse=True)[:14]),
      'other_recent_job_updates':{
        str(pid):{
          'last_24h_by_current_status':dict(sorted(last24[pid].items())),
          'last_72h_by_current_status':dict(sorted(last72[pid].items())),
          'latest_update_by_current_status':{
            key:stamp(val) for key,val in sorted(latest[pid].items())},
          'invalid_dates_by_current_status':{
            status:count for (key,status),count in sorted(unknown_dates.items())
            if key==pid}
        } for pid in WATCH},
      'interpretation_limit':(
        'These are last update timestamps for rows still in each current status. '
        'They do not prove when an old provider defect was fixed, and successful '
        'non-405 jobs alone do not prove the same asset works.'),
      'read_only':True,'provider_requests':0,'services_restarted':False
    }

def main():
    if DB.is_symlink() or not DB.is_file():
        raise SystemExit('STOP: expected production database missing')
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=20) as db:
        print(json.dumps(summarize(db),indent=2,ensure_ascii=False))

if __name__=='__main__':main()
