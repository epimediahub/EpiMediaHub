#!/usr/bin/env python3
"""Safe EpiScene visual peer seeding against real independent analysis sources.

Import original safeguarded reconciliation/release code; replace ONLY the
conservative follow-up scheduler that previously required a manual sibling
and incorrectly joined customer playlists. Seed bounded independent same-
season episodes so video can learn structure without human intervention.
All generated marks still pass the ORIGINAL production acceptance gates.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
import sys
import time

import safe_release_rollout as original

LEARNING=Path('/var/lib/episcene-learning/reference-round-40/feedback.sqlite3')
MAX_NEW_PER_RUN=4
MAX_DAILY=8
MAX_PER_PLAYLIST=2


def verified_feedback_models():
    """Calibrations affect work priority ONLY, never trust/release/marker times."""
    if not LEARNING.is_file() or LEARNING.is_symlink():
        return set()
    try:
        with sqlite3.connect(LEARNING.resolve().as_uri()+'?mode=ro',uri=True,timeout=4) as db:
            return {(p,s,season,kind) for p,s,season,kind in db.execute("""
                SELECT playlist_id,source_key,season,kind
                FROM shadow_calibrations
                WHERE status='SHADOW_ONLY' AND auto_publish_allowed=0
                  AND independent_episodes>=4
                  AND loo_median_start_error_ms<=2000
            """)}
    except sqlite3.Error:
        return set()


def protected(con,record):
    """Block unresolved manual corrections, disputed visual evidence and final decisions."""
    e=record['evidence']
    if not isinstance(e,dict):return True
    if e.get('audio_visual_disagreement') is True:return True
    if isinstance(e.get('decision'),dict) and e['decision'].get('status')=='NO_MATCH':
        return True
    if not (e.get('episcene_required') is True or e.get('method')=='episcene_consensus'):
        return True
    asset=record['asset_key'];kind=record['kind'];duration=record['duration_ms']
    if con.execute("""SELECT 1 FROM skip_records x
        LEFT JOIN skip_auto_evidence ev ON ev.record_id=x.id
        WHERE x.asset_key=? AND x.segment_type=? AND ABS(x.duration_ms-?)<=2000
          AND (x.status IN ('approved','rejected') OR
            (x.status='pending' AND (x.source='device' OR COALESCE(ev.human_review,0)=1)))
        LIMIT 1""",(asset,kind,duration)).fetchone():
        return True
    if con.execute("""SELECT 1 FROM skip_auto_blocks
        WHERE asset_key=? AND kind=? AND ABS(duration_ms-?)<=2000 LIMIT 1""",
        (asset,kind,duration)).fetchone():
        return True
    return False


def collect(con):
    """Bounded candidate population using the independent source table."""
    required=('skip_analysis_playlists','skip_assets','skip_jobs','skip_auto_settings',
              'skip_analysis_sources','skip_auto_evidence','skip_release_settings',
              'skip_records','episcene_safe_release_retries','skip_auto_blocks')
    if not all(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone()
               for t in required):
        return []
    cols={x[1] for x in con.execute('PRAGMA table_info(skip_analysis_playlists)')}
    if not {'id','archived'}<=cols:return []
    from skip_release import enabled as release_enabled
    active=Counter()
    for row in con.execute('SELECT playlist_id FROM skip_presence WHERE expires_at>?',(int(time.time()),)):
        active[row[0]]+=1
    allowed={p for p in (8,10) if not active[p] and release_enabled(con,p)}
    if not allowed:return []
    # This SQL intentionally DOES NOT join customer_playlists.
    rows=con.execute("""
      SELECT j.id job_id,j.asset_key,j.status original_status,
             a.playlist_id,a.source_key,a.season,a.episode,a.duration_ms,
             r.segment_type kind,r.id marker_id,e.evidence_json,
             COALESCE(l.priority,2) language_priority
      FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
      JOIN skip_analysis_playlists p ON p.id=a.playlist_id AND p.archived=0
      JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
      JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
      JOIN skip_records r ON r.asset_key=a.asset_key AND r.status='pending'
        AND r.source IN ('audio','audio_repetition','episcene','theintrodb','chapter')
        AND r.media_type='episode' AND r.source_key=a.source_key
        AND r.season=a.season AND r.episode=a.episode
        AND ABS(r.duration_ms-a.duration_ms)<=2000
      LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
      LEFT JOIN skip_language_priority l ON l.asset_key=a.asset_key
      WHERE a.playlist_id IN (8,10) AND a.media_type='episode'
        AND a.duration_ms>0
        AND j.status IN ('done','review','no_match','no_reference','partial')
        AND NOT EXISTS(SELECT 1 FROM episcene_safe_release_retries z
                       WHERE z.asset_key=j.asset_key)
      ORDER BY COALESCE(l.priority,2),j.updated_at,j.id
      LIMIT 1800
    """).fetchall()
    by_asset=defaultdict(list)
    for r in rows:
        d=dict(r)
        if d['playlist_id'] not in allowed:continue
        try:e=json.loads(d['evidence_json'] or '{}')
        except (TypeError,ValueError):continue
        d['evidence']=e
        if not protected(con,d):
            by_asset[d['asset_key']].append(d)
    # If two kinds share a file, analyze one at a time; never choose
    # a convenient machine alternative among disagreeing proposals.
    chosen=[]
    for entries in by_asset.values():
        kind_counts=Counter(x['kind'] for x in entries)
        for kind in sorted(kind_counts):
            group=[x for x in entries if x['kind']==kind]
            if len(group)!=1:continue
            chosen.append(group[0])
            break
    return chosen


def plan(con, candidates, max_jobs=MAX_NEW_PER_RUN, *, models=None):
    """Prefer learnt references, then independent visual peer groups."""
    if models is None:models=set()
    now=datetime.now(timezone.utc)
    today=now.strftime('%Y-%m-%d')
    daily=con.execute("""SELECT COUNT(*) FROM episcene_safe_release_retries
          WHERE substr(last_requeued_utc,1,10)=?""",(today,)).fetchone()[0]
    cap=max(0,min(int(max_jobs),MAX_NEW_PER_RUN,MAX_DAILY-daily))
    if cap==0:return []
    families=defaultdict(list)
    for r in candidates:
        families[(r['playlist_id'],r['source_key'],r['season'],r['kind'])].append(r)
    # From existing HUMAN observations, never use machine-approved records as
    # ground truth. A sibling informs priority; it is not required for work.
    references=set()
    for r in con.execute("""SELECT DISTINCT a.playlist_id,r.source_key,r.season,r.segment_type
        FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
        JOIN skip_analysis_playlists p ON p.id=a.playlist_id AND p.archived=0
        WHERE r.status='approved' AND r.disabled=0
          AND r.source='device' AND r.source_key=a.source_key
          AND r.season=a.season AND r.episode=a.episode
          AND ABS(r.duration_ms-a.duration_ms)<=500"""):
        references.add(tuple(r))
    # Continue a family already started on a previous hour before selecting
    # new groups. Three independent episodes may require multiple passes under
    # the per-playlist rate limit, and requeued ones leave the candidate pool.
    seeded=defaultdict(set)
    for item in con.execute("""SELECT DISTINCT a.playlist_id,a.source_key,a.season,
                r.segment_type,a.episode FROM episcene_safe_release_retries z
          JOIN skip_assets a ON a.asset_key=z.asset_key
          JOIN skip_records r ON r.asset_key=a.asset_key AND r.status='pending'
          WHERE a.playlist_id IN (8,10)
            AND r.segment_type IN ('intro','recap','outro')"""):
        seeded[tuple(item[:4])].add(item[4])
    # Prefer an in-progress family where independent episodes can provide
    # 3-way visual consensus. Isolated singletons cannot auto-approve.
    queue=[]
    for key,rows in families.items():
        epis={}
        for r in rows:
            episodic=epis.setdefault(r['episode'],r)
            if r['language_priority']<episodic['language_priority']:
                epis[r['episode']]=r
        if len(set(epis)|seeded[key])<3 and key not in references:
            continue
        roster=sorted(epis.values(),key=lambda x:(x['language_priority'],x['episode'],x['job_id']))
        priority=(not bool(seeded[key]),key not in models,key not in references,
                  -len(set(epis)|seeded[key]),min(r['language_priority'] for r in roster),
                  key[0],roster[0]['job_id'])
        queue.append((priority,key,roster))
    queue.sort(key=lambda x:x[0])
    output=[];taken=set();by_playlist=Counter()
    # Round robin across families, cap two per playlist per hourly run.
    for _,key,roster in queue:
        for r in roster[:3]:
            if len(output)>=cap:return output
            if by_playlist[r['playlist_id']]>=MAX_PER_PLAYLIST:break
            if r['asset_key'] in taken:continue
            output.append(r);taken.add(r['asset_key'])
            by_playlist[r['playlist_id']]+=1
    return output


def requeue(con,limit=MAX_NEW_PER_RUN):
    original.ensure_retry_table(con)
    candidates=collect(con)
    plan_rows=plan(con,candidates,limit,models=verified_feedback_models())
    selected=[]
    stamp=datetime.now(timezone.utc).isoformat()
    from skip_schedule import request_series
    for r in plan_rows:
        cur=con.execute("""UPDATE skip_jobs SET status='queued',attempts=0,
              detail='Gezielter Staffel-Bildvergleich: unabhängige Referenzen aufbauen',
              updated_at=?
              WHERE id=? AND status=?""",(stamp,r['job_id'],r['original_status']))
        if cur.rowcount!=1:continue
        con.execute("""INSERT INTO episcene_safe_release_retries
            (asset_key,last_requeued_utc,attempt_count,original_job_status)
            VALUES(?,?,1,?)""",(r['asset_key'],stamp,r['original_status']))
        # Normal scheduler owns resource/playback/language constraints.
        request_series(con,r['asset_key'],reason='playback')
        selected.append({'job_id':r['job_id'],'playlist_id':r['playlist_id'],
                         'kind':r['kind']})
    return selected


# Preserve original gates and the continuous feedback publisher. Only replace
# the scope of the conservative visual peer-retry scheduler.
original.requeue=requeue


def audit():
    if str(original.CODE) not in sys.path:
        sys.path.insert(0,str(original.CODE))
    with sqlite3.connect(original.DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=10) as db:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        candidates=collect(db)
        ready=plan(db,candidates)
        print(json.dumps(dict(mode='READ_ONLY_VISUAL_PEER_PREFLIGHT',
            candidate_assets=len(candidates),
            distinct_series_season_kinds=len({(r['playlist_id'],r['source_key'],
                                               r['season'],r['kind']) for r in candidates}),
            eligible_to_requeue_now=len(ready),
            by_playlist={str(p):sum(x['playlist_id']==p for x in ready) for p in (8,10)},
            no_provider_reads=True,no_marker_approvals=True),indent=2))


if __name__=='__main__':
    if len(sys.argv)==2 and sys.argv[1]=='--audit-peers':
        audit()
    else:
        original.main()
