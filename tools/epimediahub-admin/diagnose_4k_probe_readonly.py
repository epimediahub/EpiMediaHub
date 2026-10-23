#!/usr/bin/env python3
"""Privacy-safe investigation of recent 4K ANALYSE probe failures.

Read-only. No provider requests, app/worker restarts, asset names, stream
IDs, URLs, accounts or raw error details. DB metadata & aggregate failures only.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import json
import re
import sqlite3
import time

DB=Path('/var/lib/epimediahub/provisioning.db')
WINDOW_SECONDS=7200
PID=8
FINISHED={'done','review','partial','no_match','no_reference'}
STATUSES={'queued','running','failed','done','review','partial',
          'no_match','no_reference','disabled'}

def timestamp(value):
    if type(value) in (float,int):
        return float(value)
    if not isinstance(value,str):
        return None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.tzinfo is None:
            parsed=parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (ValueError,OverflowError):
        return None

def cause(detail):
    """Strict allowlist; never output any fragment of a private error detail."""
    text=str(detail or '')[:6000]
    if re.search(r'(?i)(?:HTTP[_\s-]*|status[=:\s]+|code[=:\s]+)(401|403)\b',text):
        return 'HTTP_AUTH_401_403'
    if re.search(r'(?i)(?:HTTP[_\s-]*|status[=:\s]+|code[=:\s]+)404\b',text):
        return 'HTTP_404_MISSING_STREAM'
    if re.search(r'(?i)(?:HTTP[_\s-]*|status[=:\s]+|code[=:\s]+)405\b',text):
        return 'HTTP_405_STREAM_METHOD'
    if re.search(r'(?i)(?:HTTP[_\s-]*|status[=:\s]+|code[=:\s]+)410\b',text):
        return 'HTTP_410_GONE'
    if re.search(r'(?i)(?:HTTP[_\s-]*|status[=:\s]+|code[=:\s]+)429\b',text):
        return 'HTTP_429_RATE_LIMIT'
    if re.search(r'(?i)(?:HTTP[_\s-]*|status[=:\s]+|code[=:\s]+)5\d\d\b',text):
        return 'HTTP_5XX_PROXY_OR_PROVIDER'
    if re.search(r'(?i)\b401\b|\b403\b|\bforbidden\b|unauthori[sz]|account.expir|token.expir|abgelaufen|nicht.autoris',text):
        return 'AUTH_OR_ACCESS'
    if re.search(r'(?i)\b(?:too.many.connections?|max.connections?|limit.connections?|concurrent|simultaneous|zu.viele.anfragen)\b',text):
        return 'PROVIDER_SESSION_LIMIT'
    if re.search(r'(?i)\b(?:timeout|timed.out|deadline|zeitüberschreit|zeitlimit)\b',text):
        return 'TIMEOUT'
    if re.search(r'(?i)\b(?:connection|network|socket|dns|host.unreachable|verbindungsfehler)\b',text):
        return 'NETWORK'
    if re.search(r'(?i)ffprobe|ffmpeg|decoder|codec|invalid.data|cannot.decode|decode.fail',text):
        return 'MEDIA_PROBE_OR_DECODER'
    if re.search(r'(?i)no.stream|stream.unavailable|no.frames|stream.offline|kein.video|no.video|empty.stream',text):
        return 'EMPTY_OR_UNAVAILABLE_STREAM'
    if not text.strip():
        return 'EMPTY_DETAIL'
    return 'OTHER_PRIVATE_ERROR'

def columns(db,name):
    return {r[1] for r in db.execute('PRAGMA table_info('+name+')')}

def collect(db,now):
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    required={'skip_jobs':{'asset_key','status','detail','updated_at'},
              'skip_assets':{'asset_key','playlist_id'},
              'skip_analysis_playlists':{'id','archived'},
              'skip_analysis_sources':{'playlist_id','enabled'}}
    for table,fields in required.items():
        if not fields.issubset(columns(db,table)):
            raise RuntimeError('STOP_UNEXPECTED_SCHEMA_'+table)
    line=db.execute("""SELECT p.archived,s.enabled FROM skip_analysis_playlists p
          LEFT JOIN skip_analysis_sources s ON s.playlist_id=p.id
          WHERE p.id=?""",(PID,)).fetchone()
    if not line:
        raise RuntimeError('STOP_PLAYLIST_8_NOT_FOUND')
    playlistcols=columns(db,'skip_analysis_playlists')
    expiry=None
    if 'expires_at' in playlistcols:
        entry=db.execute('SELECT expires_at FROM skip_analysis_playlists WHERE id=?',(PID,)).fetchone()
        expiry=entry[0] if entry else None
    output={
        'mode':'EPISCENE_4K_RECENT_PROBE_TRIAGE',
        'playlist_id':PID,
        'analysis_enabled':line['enabled']==1 and line['archived']==0,
        'catalogue_expiry_state':('UNKNOWN' if expiry is None or expiry==0
            else 'PAST' if type(expiry) in (int,float) and expiry<now
            else 'FUTURE' if type(expiry) in (int,float) else 'UNPARSEABLE'),
        'lookback_minutes':WINDOW_SECONDS//60,
    }
    totals=Counter()
    all_failures=Counter()
    recent_failures=Counter()
    recent=Counter()
    latest_updated={}
    last_completed=None
    last_failed=None
    last_failed_cause=None
    recent_fail_records=[]
    recent_completions=0
    for row in db.execute("""SELECT j.status,j.detail,j.updated_at
       FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
       WHERE a.playlist_id=?""",(PID,)):
        status=row['status']
        if status not in STATUSES:continue
        totals[status]+=1
        moment=timestamp(row['updated_at'])
        if moment is None:continue
        if moment>now+300: continue
        if moment>latest_updated.get(status,0):
            latest_updated[status]=moment
        if status in FINISHED and (last_completed is None or moment>last_completed):
            last_completed=moment
        if status=='failed':
            typ=cause(row['detail'])
            all_failures[typ]+=1
            if last_failed is None or moment>last_failed:
                last_failed=moment
                last_failed_cause=typ
        if 0<=now-moment<=WINDOW_SECONDS:
            recent[status]+=1
            if status=='failed':
                typ=cause(row['detail'])
                recent_failures[typ]+=1
                recent_fail_records.append((moment,typ))
            if status in FINISHED:recent_completions+=1
    output.update({
        'status_totals':dict(sorted(totals.items())),
        'last_completed_age_minutes':(int((now-last_completed)//60) if last_completed else None),
        'last_failed_age_minutes':(int((now-last_failed)//60) if last_failed else None),
        'recent_changes_by_status':dict(sorted(recent.items())),
        'recent_failed_count':sum(recent_failures.values()),
        'recent_completed_count':recent_completions,
        'recent_failure_categories':dict(sorted(recent_failures.items())),
        'last_failure_category':last_failed_cause,
        'last_up_to_ten_failure_categories_newest_first':[
            kind for _,kind in sorted(recent_fail_records,reverse=True)[:10]],
        'all_failed_categories_for_context':dict(sorted(all_failures.items())),
        'no_sensitive_error_text_printed':True,
        'database_changed':False,'services_restarted':False,
        'provider_requests':0,
    })
    return output

def main():
    if DB.is_symlink() or not DB.is_file():
        raise RuntimeError('STOP_PRIVATE_EPI_DB_MISSING')
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=15) as db:
        result=collect(db,time.time())
    print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))

if __name__=='__main__':
    try:main()
    except (OSError,sqlite3.Error,RuntimeError) as exc:
        message=str(exc)
        print(message if isinstance(exc,RuntimeError) and message.startswith('STOP_')
              else 'STOP_PRIVATE_DIAGNOSTIC_ERROR')
        raise SystemExit(1)
