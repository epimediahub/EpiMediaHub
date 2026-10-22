#!/usr/bin/env python3
"""Read-only EpiScene release-path diagnostic for analysis IDs 8 and 10.

Correlates actual pending segment evidence with actual visual window ownership,
duration, revision and same-season independent episodes. Never emits provider
data, title, stream URL, asset key, record ID or raw job details. No network,
media reads, mutations or service restarts.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3

DB_PATH = Path('/var/lib/epimediahub/provisioning.db')
IDS = (8, 10)
FIELDS = ('asset_key','source_key','playlist_id','stream_id','extension',
          'duration_ms','season','episode','updated_at','content_version','etag')
KINDS = ('intro','recap','outro')
MACHINE = ('audio','chapter','theintrodb','audio_repetition','auto_audio','episcene')

def columns(db, table):
    return {row[1] for row in db.execute('PRAGMA table_info('+table+')')}

def exists(db, table):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone())

def version(asset):
    """Known EpiScene visual-cache revision algorithm; non-applicable if schema differs."""
    values = {key:asset[key] if key in asset.keys() else None for key in FIELDS}
    return hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':'),
                                     allow_nan=False).encode()).hexdigest()

def evidence(value):
    try:
        result = json.loads(value or '{}')
        return result if isinstance(result, dict) else {}
    except (ValueError,TypeError):
        return {}

def failure_category(value):
    """Fixed allowlist only. Unknown details never leave the server."""
    if value is None or not str(value).strip():
        return 'EMPTY_DETAIL'
    text=str(value)[:3000]
    tests = (
        ('HTTP_AUTH_OR_EXPIRED', r'\b(?:401|403)\b|unauthori[sz]|forbidden|token.expir|zugriff.verweig|abgelaufen'),
        ('HTTP_RATE_OR_SESSION_LIMIT', r'\b429\b|too.many.requests|rate.limit|concurrent|session.limit|zu.viele.anfragen|gleichzeitig'),
        ('TIME_OR_DEADLINE', r'time.?out|timed.out|deadline|watchdog|zeit.?(?:ueber|über)schreit|zeitlimit|time.budget'),
        ('REMOTE_IO_OR_NETWORK', r'\b5\d\d\b|network|dns|broken.pipe|connection.reset|verbindung|socket|network.unreachable'),
        ('MEDIA_DECODING', r'ffmpeg|ffprobe|decoder|codec|decode|demux|unlesbar|ungültig|invalid.data'),
        ('AUDIO_FAILURE', r'audio|fingerprint|tonspur'),
        ('VISUAL_FAILURE', r'visual|frame|bild|szene|scene'),
        ('UNSUPPORTED_OR_NO_MATCH', r'no.match|no.reference|kein.treffer|keine.referenz|nicht.gefunden|missing.reference'),
        ('RETRY_OR_DEFERRED', r'retry|requeue|zurückgestellt|erneut.versuch|versuch.wiederholen'),
    )
    for name, pattern in tests:
        if re.search(pattern,text,re.I):
            return name
    return 'UNKNOWN_PRIVATE_DETAIL'

def analyze(db):
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    if not db.in_transaction:
        db.execute('BEGIN')
    schema = {
        'skip_assets': {'asset_key','playlist_id','source_key','season','episode','duration_ms'},
        'skip_jobs': {'asset_key','status'},
        'skip_records': {'id','asset_key','status','source','segment_type'},
        'skip_auto_evidence': {'record_id','evidence_json'},
        'skip_scene_windows': {'id','asset_key','kind','duration_ms'},
    }
    for name, required in schema.items():
        if not exists(db,name) or not required.issubset(columns(db,name)):
            raise RuntimeError('Required live schema missing or different: '+name)

    has_versions = exists(db,'skip_scene_window_versions') and {
        'window_id','version'}.issubset(columns(db,'skip_scene_window_versions'))
    joins = ('LEFT JOIN skip_scene_window_versions v ON v.window_id=w.id'
             if has_versions else '')
    version_sql = 'v.version AS window_version' if has_versions else 'NULL AS window_version'
    windows=defaultdict(lambda: Counter())
    peers=defaultdict(set)
    cache_counters={p:Counter() for p in IDS}
    for row in db.execute(f"""SELECT a.*,w.kind AS window_kind,w.duration_ms AS window_duration,
            {version_sql}
          FROM skip_scene_windows w JOIN skip_assets a ON a.asset_key=w.asset_key
          {joins}
          WHERE a.playlist_id IN (8,10) AND w.kind IN ('intro','recap','outro')"""):
        pid=row['playlist_id']; kind=row['window_kind']
        key=(row['asset_key'],kind)
        windows[key]['any']+=1
        cache_counters[pid]['all']+=1
        if row['window_duration']!=row['duration_ms']:
            cache_counters[pid]['duration_mismatch']+=1
            continue
        windows[key]['duration_match']+=1
        if has_versions:
            if row['window_version']==version(row):
                windows[key]['revision_match']+=1
            else:
                cache_counters[pid]['revision_mismatch_or_missing']+=1
        if row['source_key'] is not None and row['season'] is not None and row['episode'] is not None:
            peers[(pid,row['source_key'],row['season'],kind)].add(row['episode'])

    block={p:Counter() for p in IDS}
    by_kind={p:defaultdict(Counter) for p in IDS}
    source_phases={p:Counter() for p in IDS}
    for row in db.execute("""SELECT a.playlist_id,a.source_key,a.season,a.episode,
                  r.asset_key,r.segment_type,r.source,e.evidence_json
              FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
              LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
              WHERE a.playlist_id IN (8,10) AND r.status='pending'
                AND r.segment_type IN ('intro','recap','outro')
                AND r.source IN ('audio','chapter','theintrodb',
                                 'audio_repetition','auto_audio','episcene')"""):
        pid=row['playlist_id']; kind=row['segment_type']; ev=evidence(row['evidence_json'])
        if ev.get('audio_visual_disagreement') is True:
            stage='AUDIO_VISUAL_CONFLICT'
        elif ev.get('episcene_required') is True and ev.get('method')!='episcene_consensus':
            stage='AWAITING_VISUAL_CONSENSUS'
        elif ev.get('method')=='episcene_consensus':
            d=ev.get('decision')
            d=d if isinstance(d,dict) else {}
            stage='VISUAL_REVIEW' if d.get('status')=='REVIEW' else 'VISUAL_OTHER'
        else:
            stage='OTHER_PENDING'
        source_phases[pid][stage]+=1
        if stage not in ('AWAITING_VISUAL_CONSENSUS','VISUAL_REVIEW'):
            continue
        target=by_kind[pid][kind]
        target['pending_'+stage]+=1
        k=windows[(row['asset_key'],kind)]
        if not k['any']:
            gap='NO_VISUAL_WINDOWS_FOR_ASSET_AND_KIND'
        elif not k['duration_match']:
            gap='WINDOWS_BUT_WRONG_DURATION'
        elif has_versions and not k['revision_match']:
            gap='WINDOWS_BUT_NO_MATCHING_ASSET_REVISION'
        elif len(peers[(pid,row['source_key'],row['season'],kind)])<3:
            gap='VISUAL_WINDOWS_BUT_FEWER_THAN_3_EPISODES'
        else:
            gap='THREE_PLUS_EPISODES_HAVE_WINDOWS_CHECK_CONSENSUS_ENGINE'
        block[pid][gap]+=1
        target[gap]+=1

    failures={p:Counter() for p in IDS}
    unknowns={p:Counter() for p in IDS}
    known_statuses={p:Counter() for p in IDS}
    jobcols=columns(db,'skip_jobs')
    detail='j.detail' if 'detail' in jobcols else 'NULL'
    attempts='j.attempts' if 'attempts' in jobcols else 'NULL'
    for r in db.execute(f"""SELECT a.playlist_id,j.status,{detail} AS job_detail,
                  {attempts} AS attempts
           FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
           WHERE a.playlist_id IN (8,10) AND j.status IN
                 ('failed','partial','review','done','running')"""):
        pid=r['playlist_id']; status=r['status']
        known_statuses[pid][status]+=1
        if status=='failed':
            cat=failure_category(r['job_detail'])
            failures[pid][cat]+=1
            if cat=='UNKNOWN_PRIVATE_DETAIL':
                unknowns[pid][str(r['job_detail'] or '')]+=1
    failure_output={}
    for pid in IDS:
        freq=sorted(unknowns[pid].values(),reverse=True)
        failure_output[str(pid)]={
            'failed_reason_classes':dict(sorted(failures[pid].items())),
            'unclassified_distinct_details':len(unknowns[pid]),
            'unclassified_most_common_detail_repetitions':freq[0] if freq else 0,
            'unclassified_single_occurrence_detail_count':sum(n==1 for n in freq),
            'statuses_checked':dict(sorted(known_statuses[pid].items()))
        }
    return {
        'mode':'EPISCENE_RELEASE_GAP_READ_ONLY',
        'version_algorithm':'known_visual_cache_asset_version',
        'version_table_present':has_versions,
        'visual_windows_by_playlist':{str(p):dict(sorted(cache_counters[p].items())) for p in IDS},
        'pending_stage_by_playlist':{str(p):dict(sorted(source_phases[p].items())) for p in IDS},
        'window_to_pending_marker_gap':{str(p):dict(sorted(block[p].items())) for p in IDS},
        'gap_by_segment_type':{str(p):{
            k:dict(sorted(v.items())) for k,v in sorted(by_kind[p].items())
        } for p in IDS},
        'failed_jobs':failure_output,
        'limits_of_this_check':'3+ visual-window episodes means potential comparison coverage, not proof of visual agreement or automatic release.',
        'production_db_modified':False,
        'services_restarted':False,
        'marker_approvals_triggered':0,
        'raw_error_messages_or_identifiers_exported':False
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',type=Path,default=DB_PATH)
    args=parser.parse_args()
    if args.db.is_symlink() or not args.db.is_file():
        raise SystemExit('STOP: expected live database file not found')
    with sqlite3.connect(args.db.resolve().as_uri()+'?mode=ro',uri=True,timeout=20) as db:
        print(json.dumps(analyze(db),indent=2,ensure_ascii=False))

if __name__=='__main__':
    main()
