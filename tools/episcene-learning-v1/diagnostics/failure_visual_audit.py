#!/usr/bin/env python3
"""Aggregate live EpiScene failure classes and visual coverage, read-only.

No playback requests, external API calls, service restarts, DB writes, or raw
provider errors/titles/asset IDs in output. Uses only Python stdlib.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sqlite3

DEFAULT_DB = Path('/var/lib/epimediahub/provisioning.db')
PLAYLISTS = (8, 10)

# Categories only: never reveal details (which can contain stream URLs/tokens).
RULES = (
    ('PROVIDER_AUTH_OR_EXPIRED', re.compile(r'(?<!\d)(?:401|403)(?!\d)|unauthori[sz]|forbidden|expired|auth(?:entication|orization)?\s+(?:failed|error)',re.I)),
    ('PROVIDER_RATE_OR_CONNECTION_LIMIT', re.compile(r'(?<!\d)429(?!\d)|too\s+many\s+requests|rate.?limit|connection.?limit|concurrent\s+(?:stream|session)',re.I)),
    ('TIMEOUT_OR_BUDGET', re.compile(r'time.?out|timed\s+out|deadline|watchdog|time\s+budget|time\s+limit',re.I)),
    ('SOURCE_NOT_FOUND', re.compile(r'(?<!\d)(?:404|410)(?!\d)|(?:stream|file|resource)\s+not\s+found',re.I)),
    ('REMOTE_OR_NETWORK', re.compile(r'(?<!\d)5\d\d(?!\d)|network|connection\s+(?:reset|refused|aborted)|broken\s+pipe|dns|tls|ssl',re.I)),
    ('DECODER_OR_MEDIA', re.compile(r'ffmpeg|ffprobe|codec|decoder|demux|invalid\s+data|corrupt\s+(?:data|frame|stream)',re.I)),
    ('VISUAL_OR_FRAME_READ', re.compile(r'visual|scene|frame\s+(?:fetch|capture|read|fail)|image\s+(?:fetch|capture|read|fail)',re.I)),
    ('AUDIO_OR_FINGERPRINT', re.compile(r'audio|fingerprint',re.I)),
    ('NO_REFERENCE_OR_MATCH', re.compile(r'no.?reference|no.?match|reference\s+missing',re.I)),
)


def classify(detail):
    if detail is None or not str(detail).strip():
        return 'NO_DETAIL'
    text = str(detail)[:2048]
    for name, pattern in RULES:
        if pattern.search(text):
            return name
    return 'OTHER_NOT_CLASSIFIED'


def table_exists(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def cols(db, name):
    return {row[1] for row in db.execute('PRAGMA table_info('+name+')')}


def audit(db):
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    if not db.in_transaction:
        db.execute('BEGIN')
    for name, req in [('skip_jobs',{'asset_key','status'}),('skip_assets',{'asset_key','playlist_id'})]:
        if not table_exists(db,name) or not req.issubset(cols(db,name)):
            raise RuntimeError('Required analysis schema missing or changed: '+name)
    job_cols = cols(db, 'skip_jobs')
    detail_col = 'j.detail' if 'detail' in job_cols else 'NULL AS detail'
    attempts_col = 'j.attempts' if 'attempts' in job_cols else 'NULL AS attempts'
    counts = {p: Counter() for p in PLAYLISTS}
    classes = {p: defaultdict(Counter) for p in PLAYLISTS}
    attempts = {p: defaultdict(Counter) for p in PLAYLISTS}
    sql = f'''SELECT a.playlist_id,j.status,{detail_col},{attempts_col}
              FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
              WHERE a.playlist_id IN (8,10)'''
    for row in db.execute(sql):
        p=int(row['playlist_id'])
        status=str(row['status'] or 'UNKNOWN')
        counts[p][status]+=1
        if status in ('failed','partial','review','no_reference'):
            classes[p][status][classify(row['detail'])]+=1
            n=row['attempts']
            if isinstance(n,int):
                attempts[p][status]['0' if n==0 else '1' if n==1 else '2+' if n>=2 else 'negative']+=1
    result = {
        'mode':'EPISCENE_FAILURE_VISUAL_READ_ONLY',
        'jobs': {str(p): {
            'statuses':dict(sorted(counts[p].items())),
            'failure_classes_by_status': {status:dict(sorted(values.items(),key=lambda x:(-x[1],x[0]))) for status,values in sorted(classes[p].items())},
            'attempt_buckets_by_status': {status:dict(sorted(values.items())) for status,values in sorted(attempts[p].items())},
        } for p in PLAYLISTS},
        'visual_cache': {'status':'NOT_PRESENT'},
        'approval_evidence': {'status':'NOT_PRESENT'},
        'live_service_configuration_changed':False,
        'database_changed':False,
        'marker_approvals_triggered':0,
        'no_provider_requests':True,
        'privacy':'Aggregate classes only; no raw job details, titles, URLs or asset identifiers.',
    }
    if table_exists(db,'skip_scene_windows') and {'asset_key','kind'}.issubset(cols(db,'skip_scene_windows')):
        records=db.execute('''SELECT a.playlist_id, w.kind,COUNT(*) n,COUNT(DISTINCT w.asset_key) assets
            FROM skip_scene_windows w JOIN skip_assets a ON a.asset_key=w.asset_key
            WHERE a.playlist_id IN (8,10)
            GROUP BY a.playlist_id,w.kind''').fetchall()
        result['visual_cache']={'status':'PRESENT','by_playlist_kind':{str(p):{} for p in PLAYLISTS}}
        for r in records:
            result['visual_cache']['by_playlist_kind'][str(r['playlist_id'])][str(r['kind'])]={'windows':r['n'],'distinct_assets':r['assets']}
    if (table_exists(db,'skip_records') and table_exists(db,'skip_auto_evidence')
            and {'id','asset_key','status','source','segment_type'}.issubset(cols(db,'skip_records'))
            and {'record_id','evidence_json'}.issubset(cols(db,'skip_auto_evidence'))):
        evs={p:Counter() for p in PLAYLISTS}
        for r in db.execute('''SELECT a.playlist_id,r.source,r.segment_type,e.evidence_json
              FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
              LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
              WHERE a.playlist_id IN (8,10) AND r.status='pending'
                AND r.segment_type IN ('intro','recap','outro')
                AND r.source IN ('audio','chapter','theintrodb','audio_repetition','auto_audio','episcene')'''):
            p=int(r['playlist_id'])
            try:
                ev=json.loads(r['evidence_json'] or '{}')
                if not isinstance(ev,dict): ev={}
            except (TypeError,ValueError):
                ev={}
            decision=ev.get('decision')
            if not isinstance(decision,dict):decision={}
            if ev.get('audio_visual_disagreement') is True: reason='AUDIO_VISUAL_DISAGREEMENT'
            elif ev.get('episcene_required') is True and ev.get('method')!='episcene_consensus':reason='AWAITING_VISUAL_CONSENSUS'
            elif ev.get('method')=='episcene_consensus':reason='VISUAL_DECISION_'+str(decision.get('status','UNSPECIFIED'))[:30] if str(decision.get('status','')).replace('_','').isalnum() else 'VISUAL_DECISION_OTHER'
            else:reason='OTHER_PENDING_EVIDENCE'
            evs[p][reason]+=1
        result['approval_evidence']={'status':'PRESENT','by_playlist':{str(p):dict(sorted(evs[p].items())) for p in PLAYLISTS}}
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=DEFAULT_DB)
    args=parser.parse_args()
    if args.source.is_symlink() or not args.source.is_file():
        raise SystemExit('STOP: expected regular database file missing')
    with sqlite3.connect(args.source.resolve().as_uri()+'?mode=ro',uri=True,timeout=20) as db:
        print(json.dumps(audit(db),indent=2,ensure_ascii=False))

if __name__=='__main__':main()
