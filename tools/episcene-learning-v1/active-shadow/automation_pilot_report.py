#!/usr/bin/env python3
"""One-page read-only EpiScene automation pilot readiness.

Maps learned SHADOW_ONLY models to real analysis episodes and job states.
Does not trust the models for release. No provider reads, DB writes, titles,
source keys, URLs, credentials, episode names, or customer IDs in output.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

PROD=Path('/var/lib/epimediahub/provisioning.db')
LEARNING=Path('/var/lib/episcene-learning/reference-round-40/feedback.sqlite3')
MACHINE={'audio','chapter','theintrodb','audio_repetition','auto_audio','episcene'}
KINDS={'intro','recap','outro'}


def open_ro(path):
    if not path.is_file() or path.is_symlink():
        raise RuntimeError('Expected read-only SQLite source missing')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=20)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    return db


def report(prod,learn):
    models=learn.execute("""SELECT playlist_id,source_key,season,kind,
            machine_source,independent_episodes,loo_median_start_error_ms,
            status,auto_publish_allowed
        FROM shadow_calibrations ORDER BY playlist_id,season,kind
    """).fetchall()
    labels=learn.execute("""SELECT decision,COUNT(*) n
             FROM feedback_versions WHERE active=1 GROUP BY decision""").fetchall()
    counters=Counter()
    family_details=[]
    for model in models:
        m=dict(model)
        if (m['playlist_id'] not in (8,10) or m['kind'] not in KINDS or
              m['machine_source'] not in MACHINE or
              m['status']!='SHADOW_ONLY' or m['auto_publish_allowed']!=0 or
              m['independent_episodes']<4 or m['loo_median_start_error_ms']>2000):
            counters['models_not_eligible_for_pilot']+=1
            continue
        assets=prod.execute("""SELECT a.asset_key,
                (SELECT j.status FROM skip_jobs j
                   WHERE j.asset_key=a.asset_key
                   ORDER BY j.id DESC LIMIT 1) latest_status
            FROM skip_assets a
            WHERE a.playlist_id=? AND a.source_key=? AND a.season=?
              AND a.media_type='episode' LIMIT 10001
        """,(m['playlist_id'],m['source_key'],m['season'])).fetchall()
        if len(assets)>10000:
            raise RuntimeError('Unusually large episode group')
        proposals=prod.execute("""SELECT r.asset_key,r.source,r.status,r.disabled,
                COALESCE(e.human_review,0) human_review
            FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
            LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
            WHERE a.playlist_id=? AND a.source_key=? AND a.season=?
              AND a.media_type='episode' AND r.segment_type=?
        """,(m['playlist_id'],m['source_key'],m['season'],m['kind'])).fetchall()
        grouped={}
        for row in proposals:
            grouped.setdefault(row['asset_key'],[]).append(row)
        entry=Counter()
        for asset in assets:
            rows=grouped.get(asset['asset_key'],[])
            human=any(row['source']=='device' or row['human_review']==1
                      for row in rows if row['status']=='approved' and not row['disabled'])
            auto=any(row['source'] in MACHINE and row['human_review']!=1
                     for row in rows if row['status']=='approved' and not row['disabled'])
            pending=any(row['source'] in MACHINE and row['status']=='pending'
                        for row in rows)
            job=asset['latest_status'] or 'missing'
            entry['episodes']+=1
            if human:entry['human_references']+=1
            if auto:entry['machine_approved']+=1
            if pending:entry['machine_pending']+=1
            if not human and not auto:entry['not_yet_approved']+=1
            if job in ('queued','running','processing','in_progress'):
                entry['jobs_waiting_or_active']+=1
            if job in ('review','no_match','no_reference','partial','done'):
                entry['jobs_finished_or_review']+=1
            if job=='missing':entry['jobs_missing']+=1
        for k,v in entry.items():counters[k]+=v
        counters['pilot_model_groups']+=1
        family_details.append({
            'playlist_id':m['playlist_id'],
            'kind':m['kind'],
            'verified_training_episodes':m['independent_episodes'],
            'episodes_in_group':entry['episodes'],
            'human_references':entry['human_references'],
            'machine_approved':entry['machine_approved'],
            'machine_pending':entry['machine_pending'],
            'jobs_waiting_or_active':entry['jobs_waiting_or_active'],
            'jobs_finished_or_review':entry['jobs_finished_or_review'],
            'not_yet_approved':entry['not_yet_approved'],
        })
    return {
        'mode':'EPISCENE_READ_ONLY_AUTOMATION_PILOT',
        'timestamp_utc':datetime.now(timezone.utc).isoformat(),
        'active_verified_labels':dict((r['decision'],r['n']) for r in labels),
        'shadow_models_total':len(models),
        'pilot_summary':dict(counters),
        'groups':family_details,
        'new_markers_approved':0,
        'jobs_requeued':0,
        'provider_requests':0,
        'production_modified':False,
        'next_decision':'If many matching episodes are queued, let existing lanes perform their work; if jobs are finished but model families lack new approvals, inspect the original acceptance gate and independent visual evidence before changing it.'
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--prod',type=Path,default=PROD)
    p.add_argument('--learning',type=Path,default=LEARNING)
    args=p.parse_args()
    with open_ro(args.prod) as prod,open_ro(args.learning) as learn:
        print(json.dumps(report(prod,learn),indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
