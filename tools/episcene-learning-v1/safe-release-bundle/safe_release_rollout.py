#!/usr/bin/env python3
"""One-shot EpiScene safe release maintenance plus hourly bounded feedback learning.

Retroactively confirms ONLY old, authenticated, still-owned exact manual-file
submissions. Re-runs the ORIGINAL production automatic evidence gates and
queues a few stale visual jobs with approved sibling references. Never turns
shadow guesses into verified labels or bypasses audio/visual disagreement.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

DB=Path('/var/lib/epimediahub/provisioning.db')
CODE=Path('/opt/epimediahub/provisioning')
LOCK=Path('/var/lib/epimediahub/.episcene-one-step-releases.lock')
BAD_REFERENCE_IDS={2282}
MAX_PENDING_MANUAL=120  # maximum accepted human corrections per run, not backlog cap
MAX_REQUEUE_PER_DAY=8
MAX_REQUEUE_PER_RUN=4
RETRY_PLAYLISTS=(8,10)
RETRY_KINDS=('intro','recap','outro')
KIND_LIMITS={'intro':300_000,'recap':300_000,'outro':900_000}
MACHINE=('audio','chapter','theintrodb','audio_repetition','auto_audio','episcene')


def schema(con):
    expected={
      'skip_records':{'id','asset_key','source','status','device_id','customer_id',
          'source_key','media_type','segment_type','start_ms','end_ms','duration_ms',
          'disabled','season','episode','title'},
      'skip_assets':{'asset_key','playlist_id','source_key','stream_id','extension',
          'media_type','duration_ms','season','episode','title'},
      'customer_playlists':{'id','customer_id','config_json'},
      'skip_analysis_playlists':{'id','archived','config_json'},
      'customers':{'id','enabled'},
      'devices':{'id','customer_id','enabled'},
      'skip_jobs':{'id','asset_key','status','attempts','updated_at'},
      'skip_analysis_sources':{'playlist_id','enabled'},
      'skip_auto_settings':{'playlist_id','enabled'},
      'skip_auto_evidence':{'record_id','evidence_json'},
    }
    for table,required in expected.items():
        cols={r[1] for r in con.execute('PRAGMA table_info('+table+')')}
        if not required<=cols:
            raise RuntimeError('Expected production schema not present: '+table)
    return True


def manual_rows(con):
    return [dict(x) for x in con.execute("""
      SELECT r.*,a.playlist_id mapped_playlist,a.source_key mapped_source,
        a.media_type mapped_type,a.season mapped_season,a.episode mapped_episode,
        a.duration_ms mapped_duration,a.stream_id mapped_stream,
        a.extension mapped_extension,a.title mapped_title,
        d.customer_id device_customer,d.enabled device_enabled,
        c.enabled customer_enabled,p.customer_id playlist_customer,
        p.config_json playlist_config,
        ap.id analysis_playlist,ap.archived analysis_archived,
        ap.config_json analysis_config,s.enabled analysis_source_on
      FROM skip_records r
      LEFT JOIN devices d ON d.id=r.device_id
      LEFT JOIN customers c ON c.id=d.customer_id
      LEFT JOIN skip_assets a ON a.asset_key=r.asset_key
      LEFT JOIN customer_playlists p ON p.id=a.playlist_id
      LEFT JOIN skip_analysis_playlists ap ON ap.id=a.playlist_id
      LEFT JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id
      WHERE r.status='pending' AND r.source='device'
      ORDER BY r.id
    """)]


def manual_plan(con, rows, identity_key=None, validate=None):
    """Immutable eligibility calculation; caller supplies production key validator."""
    # A large number of human corrections must not halt all releases.
    # Inspect the full set for duplicates, but approve only a bounded batch.
    # Future runs can continue past permanently excluded older records.
    groups=defaultdict(list)
    for r in rows:
        groups[(r['asset_key'],r['segment_type'])].append(r)
    accepted=[];excluded=Counter()
    for r in rows:
        def reject(reason):
            excluded[reason]+=1
        if r['id'] in BAD_REFERENCE_IDS:
            reject('KNOWN_INVALID_REFERENCE')
            continue
        # Device identity must remain proven. Only the playlist-owner check
        # differs for independent ANALYSIS sources, which intentionally have
        # no row in customer_playlists. Never authorize orphaned device marks.
        if (r['device_id'] is None or r['customer_id'] is None or
            r['device_enabled']!=1 or r['customer_enabled']!=1 or
            r['device_customer']!=r['customer_id'] or
            r['mapped_playlist'] is None):
            reject('MISSING_CURRENT_DEVICE_OWNERSHIP')
            continue
        customer_owned=(r['playlist_customer']==r['customer_id'])
        independent_analysis=(
            r['mapped_playlist'] in RETRY_PLAYLISTS
            and r['analysis_playlist']==r['mapped_playlist']
            and r['analysis_archived']==0
            and r['analysis_source_on']==1
            and r['playlist_customer'] is None
        )
        if not (customer_owned or independent_analysis):
            reject('MISSING_VALID_PLAYLIST_OR_ANALYSIS_SOURCE')
            continue
        if len(groups[(r['asset_key'],r['segment_type'])]) != 1:
            reject('CONFLICTING_PENDING_MANUAL_MARKERS')
            continue
        if (r['mapped_source']!=r['source_key'] or
            r['mapped_type']!=r['media_type'] or
            r['mapped_season']!=r['season'] or
            r['mapped_episode']!=r['episode'] or
            r['mapped_title'].strip().casefold()!=r['title'].strip().casefold() or
            abs(r['mapped_duration']-r['duration_ms'])>500):
            reject('CHANGED_ASSET_OR_RUNTIME')
            continue
        if (r['segment_type'] not in RETRY_KINDS or r['duration_ms']<=0 or
            not isinstance(r['start_ms'],int) or not isinstance(r['end_ms'],int)):
            reject('INVALID_BOUNDS')
            continue
        if r['disabled'] not in (0,1):
            reject('INVALID_DISABLED_VALUE')
            continue
        if not r['disabled'] and (not 0<=r['start_ms']<r['end_ms']<=r['duration_ms']
                                 or not 5000<=r['end_ms']-r['start_ms']<=KIND_LIMITS[r['segment_type']]):
            reject('INVALID_BOUNDS')
            continue
        if con.execute("""SELECT 1 FROM skip_records x
             WHERE x.asset_key=? AND x.segment_type=? AND x.id<>?
               AND ABS(x.duration_ms-?)<=2000
               AND x.status IN ('approved','rejected') LIMIT 1""",
             (r['asset_key'],r['segment_type'],r['id'],r['duration_ms'])).fetchone():
            reject('EXISTING_HUMAN_OR_MACHINE_DECISION')
            continue
        if con.execute("""SELECT 1 FROM skip_auto_blocks
            WHERE asset_key=? AND kind=? AND ABS(duration_ms-?)<=2000 LIMIT 1""",
            (r['asset_key'],r['segment_type'],r['duration_ms'])).fetchone():
            reject('EXPLICIT_BLOCK_PRESENT')
            continue
        if len(accepted)>=MAX_PENDING_MANUAL:
            reject('DEFERRED_FOR_NEXT_SAFE_BATCH')
            continue
        if not validate or not validate(r):
            reject('UNVERIFIED_PROVIDER_ASSET')
            continue
        accepted.append(r)
    return accepted,dict(excluded)


def trusted_validator():
    if str(CODE) not in sys.path:sys.path.insert(0,str(CODE))
    from skip_analysis import source_url,provider_asset_key
    def verify(r):
        stream=r['mapped_stream']
        ext=r['mapped_extension']
        if not isinstance(stream,str) or not re.fullmatch(r'[0-9]{1,12}',stream):
            return False
        if ext not in ('mp4','mkv','m4v','avi','ts','mpeg','mpg'):
            return False
        try:
            # The provider config of independent analysis sources is NOT
            # stored in customer_playlists. Resolve with the correct config.
            owned=(r['playlist_customer']==r['customer_id'])
            config=r['playlist_config'] if owned else r['analysis_config']
            if not isinstance(config,str) or not config:
                return False
            playlist={'config_json':config}
            actual=provider_asset_key(source_url(playlist,r),r['media_type'])
            return actual==r['asset_key']
        except (TypeError,ValueError,KeyError,IndexError):
            return False
    return verify


def ensure_retry_table(con):
    con.execute("""CREATE TABLE IF NOT EXISTS episcene_safe_release_retries(
      asset_key TEXT PRIMARY KEY,last_requeued_utc TEXT NOT NULL,
      attempt_count INTEGER NOT NULL CHECK(attempt_count BETWEEN 1 AND 2),
      original_job_status TEXT NOT NULL)""")


def requeue(con, limit=MAX_REQUEUE_PER_RUN):
    """Retry only jobs with a verified same-series human reference, once each."""
    from skip_release import enabled as release_enabled
    limit=min(max(int(limit),0),MAX_REQUEUE_PER_RUN)
    today=datetime.now(timezone.utc).strftime('%Y-%m-%d')
    used=con.execute("""SELECT COUNT(*) FROM episcene_safe_release_retries
                         WHERE substr(last_requeued_utc,1,10)=?""",(today,)).fetchone()[0]
    slots=min(limit,max(0,MAX_REQUEUE_PER_DAY-used))
    if not slots:return []
    # Eligible machine findings have missing/ambiguous image evidence, not
    # contradicting image evidence, and are still bound to an active source.
    records=con.execute("""
       SELECT DISTINCT j.id job_id,j.asset_key,j.status job_status,
              a.playlist_id,a.source_key,a.season,a.episode,
              r.segment_type,e.evidence_json
       FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
       JOIN skip_records r ON r.asset_key=a.asset_key AND r.status='pending'
           AND r.source IN ('audio','audio_repetition','episcene','theintrodb','chapter')
       LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
       JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
       JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
       WHERE a.playlist_id IN (8,10) AND a.media_type='episode'
         AND a.duration_ms>0 AND j.status IN ('no_reference','no_match','review','done')
         AND NOT EXISTS(SELECT 1 FROM episcene_safe_release_retries t WHERE t.asset_key=j.asset_key)
       ORDER BY CASE j.status WHEN 'review' THEN 0 WHEN 'no_reference' THEN 1
                 WHEN 'no_match' THEN 2 ELSE 3 END, j.updated_at,j.id
       LIMIT 600
    """).fetchall()
    byplaylist=Counter();planned=[];seen=set()
    for raw in records:
        r=dict(raw)
        if r['asset_key'] in seen or byplaylist[r['playlist_id']]>=2:continue
        if not release_enabled(con,r['playlist_id']):continue
        evidence={}
        try:evidence=json.loads(r['evidence_json'] or '{}')
        except (ValueError,TypeError):pass
        if not isinstance(evidence,dict):continue
        if evidence.get('audio_visual_disagreement') is True:continue
        if not (evidence.get('episcene_required') is True or
                evidence.get('method')=='episcene_consensus'):continue
        decision=evidence.get('decision')
        if isinstance(decision,dict) and decision.get('status')=='NO_MATCH':
            continue
        if con.execute("""SELECT 1 FROM skip_records m WHERE
             m.asset_key=? AND m.segment_type=? AND m.status='pending'
             AND m.source='device' AND ABS(m.duration_ms-(SELECT duration_ms
               FROM skip_assets WHERE asset_key=?))<=2000 LIMIT 1""",
             (r['asset_key'],r['segment_type'],r['asset_key'])).fetchone():continue
        if con.execute("""SELECT 1 FROM skip_presence WHERE playlist_id=?
                   AND expires_at>? LIMIT 1""",
                   (r['playlist_id'],int(time.time()))).fetchone():continue
        has_ref=con.execute("""SELECT 1 FROM skip_records h
           WHERE h.status='approved' AND h.source='device' AND h.disabled=0
             AND h.source_key=? AND h.season=? AND h.episode<>?
             AND h.segment_type=? AND h.duration_ms>0 LIMIT 1""",
             (r['source_key'],r['season'],r['episode'],r['segment_type'])).fetchone()
        if not has_ref:continue
        seen.add(r['asset_key'])
        byplaylist[r['playlist_id']]+=1
        planned.append(r)
        if len(planned)>=slots:break
    for r in planned:
        con.execute("""UPDATE skip_jobs SET status='queued',attempts=0,
             detail='Referenzlage verbessert: erneute begrenzte Bildprüfung',
             updated_at=? WHERE id=? AND status=?""",
             (datetime.now(timezone.utc).isoformat(),r['job_id'],r['job_status']))
        con.execute("""INSERT INTO episcene_safe_release_retries
             VALUES(?,?,1,?)""",(r['asset_key'],datetime.now(timezone.utc).isoformat(),r['job_status']))
    return [{'job_id':r['job_id'],'playlist_id':r['playlist_id']} for r in planned]


def run(con, *, apply=False,validate=None):
    schema(con)
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='skip_auto_blocks' AND type='table'").fetchone():
        raise RuntimeError('Original approval blocks missing')
    rows=manual_rows(con)
    selected,reasons=manual_plan(con,rows,validate=validate or trusted_validator())
    if not apply:
        return {'mode':'PREFLIGHT_READ_ONLY','old_manual_pending':len(rows),
            'eligible_exact_manual_marks':len(selected),
            'excluded':reasons,'production_changes':0}
    # Begin the write transaction only after preflight against current sources.
    con.execute('BEGIN IMMEDIATE')
    fresh=manual_rows(con)
    eligible,again=manual_plan(con,fresh,validate=validate or trusted_validator())
    if ({r['id'] for r in eligible}!={r['id'] for r in selected} or again!=reasons):
        raise RuntimeError('Backlog changed during preflight, no modifications')
    from skip_markers import review_record,wake_reference_jobs
    from skip_release import accept_pending
    wake=set()
    for row in eligible:
        live=con.execute("SELECT * FROM skip_records WHERE id=?",(row['id'],)).fetchone()
        if not live or live['status']!='pending' or live['source']!='device':
            raise RuntimeError('Manual marker changed during transaction')
        review_record(con,live,'approve',row['start_ms'],row['end_ms'],bool(row['disabled']),wake=False)
        if not row['disabled']:
            wake.add((row['source_key'],row['season']))
    for source,season in wake:
        wake_reference_jobs(con,source,season)
    # Reuse every original backend gate. Never lower thresholds or mark anything verified.
    machine_approved=accept_pending(con)
    ensure_retry_table(con)
    retried=requeue(con)
    remaining=con.execute("""SELECT COUNT(*) FROM skip_records
                              WHERE status='pending' AND source='device'""").fetchone()[0]
    return {
        'mode':'APPLIED_ORIGINAL_RELEASE_GATES',
        'old_manual_pending_before':len(rows),
        'old_manual_exact_source_approved':len(eligible),
        'manual_excluded_by_safety_check':reasons,
        'machine_approved_by_existing_all_gates':machine_approved,
        'visual_jobs_requeued':len(retried),
        'visual_retries_by_playlist':dict(Counter(str(x['playlist_id']) for x in retried)),
        'old_manual_still_pending':remaining,
        'new_unverified_labels':0,
        'loosened_automatic_release_thresholds':False,
        'note':'Remaining visual work runs through normal daily-budget and playback-aware analyzer lanes.',
    }


def main():
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--check',action='store_true')
    g.add_argument('--apply',action='store_true')
    p.add_argument('--source',type=Path,default=DB)
    args=p.parse_args()
    if args.apply and os.geteuid()!=0:raise RuntimeError('Root required')
    if args.source.is_symlink() or not args.source.is_file():
        raise RuntimeError('Unexpected source database')
    if args.apply:
        if LOCK.is_symlink():raise RuntimeError('Unexpected lock path')
        guard=LOCK.open('a')
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    else:guard=None
    try:
        connection=args.source.resolve().as_uri()+'?mode=ro' if args.check else str(args.source.resolve())
        with sqlite3.connect(connection,uri=args.check,timeout=30) as con:
            con.row_factory=sqlite3.Row
            con.execute('PRAGMA foreign_keys=ON')
            con.execute('PRAGMA busy_timeout=30000')
            if args.check:con.execute('PRAGMA query_only=ON')
            result=run(con,apply=args.apply)
            if args.apply:con.commit()
        # Preserve old human decisions, negative feedback and comparisons.
        # The exporter itself opens the original database READ ONLY.
        from feedback_learning import run as feedback_run
        result['feedback_learning']=feedback_run(persist=args.apply)
        print(json.dumps(result,indent=2,ensure_ascii=False),flush=True)
    finally:
        if guard:guard.close()


if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError,OSError,sqlite3.Error,BlockingIOError) as e:
        print('STOP:',str(e),file=sys.stderr)
        raise SystemExit(1)
