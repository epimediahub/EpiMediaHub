#!/usr/bin/env python3
"""EpiScene: one privacy-preserving, fully READ-ONLY root-cause report.

Three separate release/learning failure domains:
  1. Old device markers: original device/customer/asset relation, not guesses.
  2. Machine marks: live first blocker, and exact requeue eligibility funnel.
  3. Learning: whether approved/rejected corrections actually reach the
     production analyzer rather than staying in a private shadow SQLite.

No writes, no network, no account URLs, no tokens, no asset hashes, no names.
Requires only the Python standard library. Doesn't import production modules.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import time

ORIGINAL=Path('/var/lib/epimediahub/provisioning.db')
FEEDBACK=Path('/var/lib/episcene-learning/reference-round-40/feedback.sqlite3')
CAPTURES=Path('/var/lib/episcene-learning/reference-round-40/visual_fingerprints.sqlite3')
SHADOW=Path('/var/lib/episcene-learning/reference-round-40/shadow.sqlite3')
APP=Path('/opt/epimediahub/provisioning')
MARKED_BY_HUMAN=('device',)
MACHINE=('audio','chapter','theintrodb','audio_repetition','auto_audio','episcene')
ACTIVE=(8,10)


def open_readonly(path):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError('Required source database missing or symlink')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=12)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    return db


def present(db,table):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                           (table,)).fetchone())


def cols(db,table):
    return {r[1] for r in db.execute(f'PRAGMA table_info({table})')}


def parse(s):
    try:
        x=json.loads(s or '{}')
        return x if isinstance(x,dict) else {}
    except (ValueError, TypeError):
        return {}


def ownership(db):
    if not all(present(db,t) for t in ('skip_records','devices','customers','skip_assets','customer_playlists')):
        return {'status':'SCHEMA_MISSING','no_changes':True}
    q="""SELECT r.id,r.device_id,r.customer_id,r.source_key,r.media_type,r.season,
          r.episode,r.duration_ms,r.title,r.segment_type,
          d.id actual_device,d.customer_id device_owner,d.enabled device_active,
          c.id actual_customer,c.enabled customer_active,
          a.asset_key actual_asset,a.source_key asset_source,a.media_type asset_type,
          a.season asset_season,a.episode asset_episode,a.duration_ms asset_duration,
          a.playlist_id asset_playlist,a.title asset_title,
          p.id actual_playlist,p.customer_id playlist_owner
          FROM skip_records r
          LEFT JOIN devices d ON d.id=r.device_id
          LEFT JOIN customers c ON c.id=d.customer_id
          LEFT JOIN skip_assets a ON a.asset_key=r.asset_key
          LEFT JOIN customer_playlists p ON p.id=a.playlist_id
          WHERE r.status='pending' AND r.source='device' ORDER BY r.id"""
    rows=[dict(v) for v in db.execute(q)]
    issues=Counter(); primary=Counter(); by_kind=Counter()
    no_blockers=0; intact_device_without_asset=0
    for r in rows:
        by_kind[r['segment_type']]+=1
        checks=[
            ('MISSING_DEVICE_ID',r['device_id'] is None),
            ('DEVICE_NOT_FOUND',r['device_id'] is not None and r['actual_device'] is None),
            ('DEVICE_DISABLED',r['actual_device'] is not None and r['device_active']!=1),
            ('MISSING_CUSTOMER_ID',r['customer_id'] is None),
            ('DEVICE_CUSTOMER_MISMATCH',r['actual_device'] is not None and r['device_owner']!=r['customer_id']),
            ('CUSTOMER_NOT_FOUND',r['actual_device'] is not None and r['actual_customer'] is None),
            ('CUSTOMER_DISABLED',r['actual_customer'] is not None and r['customer_active']!=1),
            ('UNLINKED_MEDIA_ASSET',r['actual_asset'] is None),
            ('PLAYLIST_NOT_FOUND',r['actual_asset'] is not None and r['actual_playlist'] is None),
            ('PLAYLIST_OWNER_MISMATCH',r['actual_playlist'] is not None and r['playlist_owner']!=r['customer_id']),
            ('MEDIA_SOURCE_MISMATCH',r['actual_asset'] is not None and
             (r['asset_source']!=r['source_key'] or r['asset_type']!=r['media_type'] or
              r['asset_season']!=r['season'] or r['asset_episode']!=r['episode'] or
              abs(r['asset_duration']-r['duration_ms'])>500)),
        ]
        found=[tag for tag,condition in checks if condition]
        for name in found: issues[name]+=1
        primary[found[0] if found else 'CURRENT_LINKS_OK']+=1
        if not found:no_blockers+=1
        if (r['actual_device'] is not None and r['device_active']==1
              and r['customer_active']==1 and r['actual_asset'] is None):
            intact_device_without_asset+=1
    return dict(pending_manual=len(rows),by_kind=dict(by_kind),
                mutually_nonexclusive_missing_links=dict(issues),
                first_failure=dict(primary),current_links_all_ok=no_blockers,
                active_device_but_missing_asset=intact_device_without_asset,
                meaning='Current owner links may have been lost after the original submission. Historical provenance is NOT recoverable from this query alone.')


def release_settings(db):
    if not all(present(db,t) for t in ('customer_playlists','skip_analysis_sources','skip_auto_settings','skip_release_settings')):
        return {'status':'SETTINGS_TABLE_MISSING'}
    rows=db.execute("""SELECT p.id,COALESCE(s.enabled,0) source_on,
      COALESCE(a.enabled,0) auto_on,COALESCE(r.enabled,1) release_on,
      COALESCE(c.enabled,0) customer_on
      FROM customer_playlists p
      LEFT JOIN customers c ON c.id=p.customer_id
      LEFT JOIN skip_analysis_sources s ON s.playlist_id=p.id
      LEFT JOIN skip_auto_settings a ON a.playlist_id=p.id
      LEFT JOIN skip_release_settings r ON r.playlist_id=p.id
      WHERE p.id IN (8,10) ORDER BY p.id""").fetchall()
    return {str(x['id']):{'analysis':bool(x['source_on']),'automatic':bool(x['auto_on']),
                          'release':bool(x['release_on']),'customer_active':bool(x['customer_on'])} for x in rows}


def evidence_breakdown(db):
    if not all(present(db,t) for t in ('skip_records','skip_assets','skip_auto_evidence')):
        return {'status':'EVIDENCE_TABLE_MISSING'}
    data=[dict(r) for r in db.execute("""SELECT r.id,r.source,r.segment_type,r.status,r.asset_key,
        r.start_ms,r.end_ms,r.disabled,e.evidence_json,
        a.playlist_id FROM skip_records r
        LEFT JOIN skip_assets a ON a.asset_key=r.asset_key
        LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
        WHERE r.source IN ('audio','chapter','theintrodb','audio_repetition','auto_audio','episcene')
          AND r.segment_type IN ('intro','recap','outro')
          AND r.status IN ('pending','approved','rejected')""")]
    status=Counter(); block=Counter(); kinds=Counter(); low=Counter()
    for r in data:
        status[r['status']]+=1
        if r['status']!='pending':continue
        evidence=parse(r['evidence_json'])
        decision=evidence.get('decision')
        decision=decision if isinstance(decision,dict) else {}
        kinds[r['segment_type']]+=1
        source=r['source']
        if evidence.get('audio_visual_disagreement') is True:
            key='AUDIO_VISUAL_DISAGREEMENT'
        elif evidence.get('method')=='episcene_consensus' and decision.get('status')!='AUTO_CONFIRMED':
            key='VISUAL_REVIEW_OR_UNCONFIRMED'
        elif evidence.get('episcene_required') is True and evidence.get('method')!='episcene_consensus':
            key='MISSING_SCENE_CONSENSUS'
        elif source=='audio_repetition':
            key='REPETITION_ONLY_OR_UNCONFIRMED'
        elif evidence.get('method')=='episcene_consensus':
            key='SCENE_CONSENSUS_RECHECK_LIVE_GATES'
        else:
            key='OTHER_PENDING_RELEASE_GATE'
        block[key]+=1
        if key=='VISUAL_REVIEW_OR_UNCONFIRMED':
            low[str(decision.get('status') or 'NO_STATUS')]+=1
    return dict(machine_status=dict(status),pending_by_kind=dict(kinds),
                first_evidence_categories=dict(block),visual_decision_status=dict(low),
                note='Evidence categories are descriptive, not complete release-gate simulations; no records autoapproved.')


def queue_funnel(db):
    tables=('skip_jobs','skip_assets','skip_records','skip_analysis_sources',
            'skip_auto_settings','skip_release_settings','skip_presence',
            'skip_auto_evidence','episcene_safe_release_retries')
    if not all(present(db,t) for t in tables):
        return {'status':'MISSING_REQUIRED_QUEUE_TABLE',
                'missing':[t for t in tables if not present(db,t)]}
    counts=Counter(); stage=Counter(); jobs=Counter()
    for r in db.execute("SELECT status,COUNT(*) n FROM skip_jobs GROUP BY status"):
        jobs[str(r['status'])]+=r['n']
    allrows=[dict(x) for x in db.execute("""
       SELECT j.id job_id,j.asset_key,j.status job_status,
              a.playlist_id,a.source_key,a.season,a.episode,
              r.segment_type,e.evidence_json,
              s.enabled source_on,x.enabled auto_on,
              rr.enabled release_on,c.enabled customer_on
       FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
       JOIN skip_records r ON r.asset_key=a.asset_key
           AND r.status='pending'
           AND r.source IN ('audio','audio_repetition','episcene','theintrodb','chapter')
       LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
       LEFT JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id
       LEFT JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id
       LEFT JOIN skip_release_settings rr ON rr.playlist_id=a.playlist_id
       LEFT JOIN customer_playlists p ON p.id=a.playlist_id
       LEFT JOIN customers c ON c.id=p.customer_id
       WHERE a.playlist_id IN (8,10) AND a.media_type='episode'
         AND a.duration_ms>0 AND j.status IN ('no_reference','no_match','review','done')
       ORDER BY j.id,r.segment_type LIMIT 2000
    """)]
    counts['potential_job_marker_pairs']=len(allrows)
    counts['distinct_assets_considered']=len({r['asset_key'] for r in allrows})
    by_asset=defaultdict(set)
    for x in db.execute("""SELECT asset_key,segment_type FROM skip_records
                            WHERE status='pending' AND source='device'"""):
        by_asset[x['asset_key']].add(x['segment_type'])
    reference={(x['source_key'],x['season'],x['segment_type'],x['episode'])
         for x in db.execute("""SELECT source_key,season,segment_type,episode
                               FROM skip_records
                               WHERE status='approved' AND source='device' AND disabled=0""")}
    ref_groups=defaultdict(set)
    for src,season,kind,episode in reference:ref_groups[(src,season,kind)].add(episode)
    active={x['playlist_id'] for x in db.execute('SELECT playlist_id FROM skip_presence WHERE expires_at>?',(int(time.time()),))}
    retries={x['asset_key'] for x in db.execute('SELECT asset_key FROM episcene_safe_release_retries')}
    seen=set()
    for r in allrows:
        asset=r['asset_key']
        if asset in seen:
            stage['REPEAT_ASSET_SKIPPED']+=1;continue
        if r['source_on']!=1:
            stage['ANALYSIS_SOURCE_OFF']+=1;continue
        if r['auto_on']!=1:
            stage['AUTO_DISCOVERY_OFF']+=1;continue
        if r['customer_on']!=1:
            stage['CUSTOMER_OFF']+=1;continue
        if r['release_on']==0:
            stage['AUTOMATIC_RELEASE_OFF']+=1;continue
        if asset in retries:
            stage['ALREADY_REQUEUED_ONCE']+=1;continue
        ev=parse(r['evidence_json'])
        if ev.get('audio_visual_disagreement') is True:
            stage['CONFIRMED_AV_CONTRADICTION']+=1;continue
        if not (ev.get('episcene_required') is True or ev.get('method')=='episcene_consensus'):
            stage['NOT_MARKED_FOR_VISUAL_FOLLOWUP']+=1;continue
        dec=ev.get('decision')
        if isinstance(dec,dict) and dec.get('status')=='NO_MATCH':
            stage['EXPLICIT_SCENE_NO_MATCH']+=1;continue
        if r['segment_type'] in by_asset[asset]:
            stage['PENDING_MANUAL_CORRECTION']+=1;continue
        if r['playlist_id'] in active:
            stage['PLAYBACK_IS_ACTIVE']+=1;continue
        if len(ref_groups[(r['source_key'],r['season'],r['segment_type'])] - {r['episode']})<1:
            stage['NO_APPROVED_SAME_SOURCE_SEASON_KIND_SIBLING']+=1;continue
        stage['PASSES_ALL_BEFORE_DAILY_QUOTAS']+=1
        seen.add(asset)
    return dict(job_statuses=jobs,counts=dict(counts),
                first_queue_requeue_blockers=dict(stage),
                note='A read-only approximation of the installed conservative requeue funnel, not a promise of completed video reads.')


def learning():
    result={}
    for label,path in (('feedback',FEEDBACK),('shadow',SHADOW),('visual_capture',CAPTURES)):
        if path.is_symlink():
            result[label]={'status':'SYMLINK_UNEXPECTED'};continue
        if not path.is_file():
            result[label]={'status':'NOT_PRESENT'};continue
        try:
            with open_readonly(path) as db:
                if label=='feedback':
                    result[label]={
                      'active_labels':db.execute('SELECT COUNT(*) FROM feedback_versions WHERE active=1').fetchone()[0],
                      'positive':db.execute("SELECT COUNT(*) FROM feedback_versions WHERE active=1 AND decision='positive'").fetchone()[0],
                      'negative':db.execute("SELECT COUNT(*) FROM feedback_versions WHERE active=1 AND decision='negative'").fetchone()[0],
                      'historical_versions':db.execute('SELECT COUNT(*) FROM feedback_versions').fetchone()[0],
                      'same_asset_machine_comparisons':db.execute('SELECT COUNT(*) FROM machine_comparisons').fetchone()[0],
                      'shadow_models':db.execute('SELECT COUNT(*) FROM shadow_calibrations').fetchone()[0],
                      'auto_publish_flags':db.execute('SELECT COUNT(*) FROM shadow_calibrations WHERE auto_publish_allowed<>0').fetchone()[0],
                    }
                elif label=='shadow':
                    result[label]={
                      'round_40_observations':db.execute('SELECT COUNT(*) FROM owner_attested_round40').fetchone()[0],
                      'shadow_outro_models':db.execute('SELECT COUNT(*) FROM shadow_outro_models').fetchone()[0],
                      'shadow_candidates':db.execute('SELECT COUNT(*) FROM shadow_outro_candidates').fetchone()[0]
                    }
                else:
                    result[label]={'visual_windows':db.execute('SELECT COUNT(*) FROM frames').fetchone()[0],
                                   'reference_windows':db.execute("SELECT COUNT(*) FROM frames WHERE kind='reference'").fetchone()[0],
                                   'candidate_windows':db.execute("SELECT COUNT(*) FROM frames WHERE kind='candidate'").fetchone()[0]}
        except (sqlite3.Error,ValueError) as e:
            result[label]={'status':'READ_FAILED','error_type':type(e).__name__}
    # Static text reference check does not require importing app code or accessing secrets.
    exact=('feedback.sqlite3','shadow_calibrations','visual_fingerprints.sqlite3',
           'shadow_outro_models','safe_release_rollout')
    refs=Counter()
    if APP.is_dir() and not APP.is_symlink():
        for p in list(APP.glob('*.py'))[:200]:
            try:
                if p.is_symlink() or p.stat().st_size>500_000:continue
                body=p.read_text(encoding='utf-8')
                for term in exact:
                    if term in body:refs[term]+=1
            except (OSError,UnicodeDecodeError):pass
    result['production_code_static_reference_counts']=dict(refs)
    result['integration_warning']='Zero static references strongly suggests shadow model files are not consumed by the production analyzer. Nonzero references still require execution-path review.'
    return result


def services():
    names=('episcene-safe-release-learning.timer',
           'episcene-owner-learning-shadow.timer',
           'episcene-visual-shadow-capture.timer')
    items={}
    for name in names:
        try:
            r=subprocess.run(['systemctl','is-active',name],text=True,
                capture_output=True,timeout=4,check=False)
            state=r.stdout.strip()[:32]
            items[name]=state if state in ('active','inactive','failed','activating','deactivating') else 'unknown'
        except (OSError,subprocess.TimeoutExpired):
            items[name]='unknown'
    return items


def report(db):
    db.execute('PRAGMA query_only=ON')
    return dict(mode='EPISCENE_COMPREHENSIVE_READ_ONLY_ROOT_CAUSE',
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                legacy_manual=ownership(db),
                playlist_settings=release_settings(db),
                machine_evidence=evidence_breakdown(db),
                visual_requeue=queue_funnel(db),
                learning=learning(),background_services=services(),
                production_db_modified=False,auto_approvals_triggered=0,
                credentials_or_customer_identifiers_in_report=False)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,default=ORIGINAL)
    a=p.parse_args()
    with open_readonly(a.source) as db:
        print(json.dumps(report(db),indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
