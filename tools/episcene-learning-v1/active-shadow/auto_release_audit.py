#!/usr/bin/env python3
"""Explain why existing EpiScene proposals have not been auto-approved.

Production provisioning DB is opened with SQLite mode=ro/query_only. This
tool must never update statuses, fabricate manual approval, or release markers.
Group counts are diagnostics, NOT simulated approve_pending decisions.
"""
from __future__ import annotations
import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT=Path('/var/lib/epimediahub/provisioning.db')
SOURCES=('audio','chapter','theintrodb','audio_repetition','auto_audio','episcene')


def as_json(s):
    try:
        value=json.loads(s or '{}')
        return value if isinstance(value,dict) else {}
    except (ValueError,TypeError):
        return {}


def query_database(con):
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    con.execute('BEGIN')
    cols={r[1] for r in con.execute('PRAGMA table_info(skip_records)')}
    required={'id','asset_key','status','segment_type','source','duration_ms','start_ms','end_ms'}
    if not required<=cols:
        raise RuntimeError('Unexpected skip_records schema')
    assets={r[1] for r in con.execute('PRAGMA table_info(skip_assets)')}
    if not {'asset_key','playlist_id','duration_ms'}<=assets:
        raise RuntimeError('Unexpected skip_assets schema')
    evidence_exists=bool(con.execute("""
        SELECT 1 FROM sqlite_master WHERE name='skip_auto_evidence' AND type='table'
    """).fetchone())
    join=("LEFT JOIN skip_auto_evidence e ON e.record_id=r.id"
          if evidence_exists else "")
    evidence=("e.evidence_json,e.human_review" if evidence_exists else
              "NULL AS evidence_json,0 AS human_review")
    rows=[dict(r) for r in con.execute(f"""SELECT
          r.id,r.asset_key,r.segment_type,r.source,r.status,r.start_ms,r.end_ms,
          r.duration_ms,r.disabled,r.confidence,a.playlist_id,
          a.duration_ms AS asset_duration,{evidence}
          FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
          {join}
          WHERE r.status IN ('pending','approved','rejected')
          AND r.segment_type IN ('intro','recap','outro')
          AND r.source IN ('audio','chapter','theintrodb','audio_repetition',
                          'auto_audio','episcene','device','manual','app','user')
          """)]
    return rows


def diagnostic(rows):
    decisions=defaultdict(list)
    manual_wait=defaultdict(list)
    for r in rows:
        key=(r['asset_key'],r['segment_type'])
        if r['status'] in ('approved','rejected'):
            decisions[key].append(r)
        if r['status']=='pending' and (r['source'] in ('device','manual','app','user')
                                       or r['human_review']):
            manual_wait[key].append(r)
    reasons=Counter()
    by_kind=defaultdict(Counter)
    by_playlist=defaultdict(Counter)
    by_source=defaultdict(Counter)
    examples=defaultdict(list)
    total=0
    for r in rows:
        if r['status']!='pending' or r['source'] not in SOURCES:
            continue
        total+=1
        evidence=as_json(r['evidence_json'])
        decision=evidence.get('decision') if isinstance(evidence.get('decision'),dict) else {}
        type_=r['segment_type']
        key=(r['asset_key'],type_)
        if r['disabled']:
            reason='DISABLED_MARKER'
        elif (not isinstance(r['start_ms'],int) or not isinstance(r['end_ms'],int)
              or not 0<=r['start_ms']<r['end_ms']<=r['duration_ms']+2000
              or abs(r['asset_duration']-r['duration_ms'])>2000):
            reason='INVALID_OR_STALE_DURATION'
        elif any(abs(int(d['duration_ms'])-int(r['duration_ms']))<=2000
                 for d in decisions[key]):
            reason='ALREADY_DECIDED_FOR_SAME_ASSET'
        elif any(abs(int(d['duration_ms'])-int(r['duration_ms']))<=2000
                 for d in manual_wait[key]):
            reason='OWNER_CORRECTION_PENDING'
        elif evidence.get('method')=='episcene_consensus':
            if evidence.get('audio_visual_disagreement') is True:
                reason='AUDIO_VISUAL_DISAGREEMENT'
            elif decision.get('status')=='REVIEW':
                reason='VISUAL_REVIEW'
            elif decision.get('status')!='AUTO_CONFIRMED':
                reason='VISUAL_UNCONFIRMED'
            else:
                reason='POSSIBLY_READY_RECHECK_FULL_GATE'
        elif evidence.get('episcene_required') is True:
            reason='NEEDS_VISUAL_EVIDENCE'
        elif evidence.get('method')=='reviewed_audio_match':
            vote=evidence.get('vote')
            if not isinstance(vote,dict) or vote.get('boundaries_confirmed') is not True:
                reason='AUDIO_BOUNDARIES_UNCONFIRMED'
            else:
                reason='AUDIO_VOTE_RECHECK_FULL_GATE'
        elif evidence.get('method') in ('episode_consensus_v3','episode_consensus'):
            if evidence.get('status')=='AUTO_CONFIRMED':
                reason='AUDIO_CONSENSUS_RECHECK_FULL_GATE'
            else:
                reason='AUDIO_CONSENSUS_NOT_CONFIRMED'
        elif r['source']=='audio_repetition':
            reason='REPETITION_ALONE_NOT_VERIFIED'
        elif r['source']=='theintrodb':
            reason='ONLINE_HINT_NOT_INDEPENDENT_PROOF'
        elif r['source']=='chapter':
            reason='CHAPTER_HINT_NOT_INDEPENDENT_PROOF'
        else:
            reason='INSUFFICIENT_MACHINE_EVIDENCE'
        reasons[reason]+=1
        by_kind[type_][reason]+=1
        by_source[r['source']][reason]+=1
        if r['playlist_id'] is not None:
            by_playlist[str(r['playlist_id'])][reason]+=1
        if len(examples[reason])<8:
            examples[reason].append(int(r['id']))
    return {
        'mode':'READ_ONLY_AUTOAPPROVAL_DIAGNOSTIC',
        'pending_machine_markers_checked':total,
        'classification_note':'Reason codes approximate the first visible blocker. POSSIBLY_READY and RECHECK do NOT claim that production approve_pending would approve.',
        'reasons':dict(sorted(reasons.items(),key=lambda kv:(-kv[1],kv[0]))),
        'by_kind':{k:dict(v) for k,v in sorted(by_kind.items())},
        'by_source':{k:dict(v) for k,v in sorted(by_source.items())},
        'by_playlist_id':{k:dict(v) for k,v in sorted(by_playlist.items())},
        'sample_marker_ids':dict(examples),
        'owner_pending_rows':sum(r['status']=='pending' and r['source'] in ('device','manual','app','user') for r in rows),
        'owner_pending_episodes':len({(r['asset_key'],r['segment_type']) for r in rows
                                      if r['status']=='pending' and r['source'] in ('device','manual','app','user')}),
        'verified_learning_labels_added':0,
        'production_db_modified':False,
        'new_auto_approvals':0,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,default=DEFAULT)
    a=p.parse_args()
    if a.source.is_symlink() or not a.source.is_file():
        raise SystemExit('Original SQLite database missing or is a symlink')
    with sqlite3.connect(a.source.resolve().as_uri()+'?mode=ro',uri=True,timeout=10) as con:
        print(json.dumps(diagnostic(query_database(con)),indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
