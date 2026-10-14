#!/usr/bin/env python3
"""EpiScene reference learning pilot; all original markers READ ONLY.

Persists an owner-attested reference batch with source provenance (NOT
server-authenticated reviewer labels) and generates private shadow proposals.
Never writes to the production analyzer or its existing LearningStore labels.
"""
import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

ANALYZER=Path('/var/lib/epimediahub/provisioning.db')
ROUND=Path('/var/lib/episcene-learning/reference-round-40')
OUTPUT=Path('/var/lib/episcene-learning/reference-round-40/shadow.sqlite3')
EXCLUDE={2282}


def normalize(x): return ' '.join(str(x or '').casefold().split())


def date(x):
    try:
        v=datetime.fromisoformat(str(x).replace('Z','+00:00'))
        return v.astimezone(timezone.utc) if v.tzinfo else None
    except (TypeError, ValueError): return None


def snapshot(con):
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA query_only=ON')
    con.execute('BEGIN')
    for table,required in {'skip_records':{'id','asset_key','title','season','episode','created_at','segment_type','start_ms','end_ms','source','status','disabled'},'skip_assets':{'asset_key','playlist_id','title','season','episode','source_key','duration_ms'}}.items():
        got={r[1] for r in con.execute(f'PRAGMA table_info({table})')}
        if not required<=got:raise ValueError('Analyzer schema mismatch: '+table)
    return [dict(r) for r in con.execute('''SELECT r.id,r.asset_key,r.title AS marker_title,
        r.season AS marker_season,r.episode AS marker_episode,r.created_at,r.segment_type,
        r.start_ms,r.end_ms,r.source,r.status,r.disabled,
        a.title AS asset_title,a.season AS asset_season,a.episode AS asset_episode,
        a.playlist_id,a.source_key,a.duration_ms
        FROM skip_records r LEFT JOIN skip_assets a ON a.asset_key=r.asset_key
        WHERE (lower(r.source)='device' OR (r.source='audio_repetition' AND r.segment_type='outro'))
    ''')]


def choose(rows,plan,baseline):
    keys=defaultdict(list)
    for e in plan['episodes']:
        keys[(normalize(e['series']),int(e['season']),int(e['episode']))].append(e)
    since=date(baseline['recorded_utc'])
    if since is None:raise ValueError('Baseline timestamp invalid')
    selected=[]; automatic=[]
    for r in rows:
        if normalize(r['segment_type']) not in ('intro','recap','outro'):continue
        try:
            start,end=int(r['start_ms']),int(r['end_ms'])
            if not 0<=start<end<=86400000:continue
            ss=r['asset_season'] if r['asset_season'] is not None else r['marker_season']
            ee=r['asset_episode'] if r['asset_episode'] is not None else r['marker_episode']
            k=(normalize(r['asset_title'] or r['marker_title']),int(ss),int(ee))
        except (TypeError,ValueError):continue
        r=dict(r,ref_key=k,start_ms=start,end_ms=end)
        if normalize(r['source'])=='audio_repetition':automatic.append(r);continue
        possible=keys.get(k,[])
        if len(possible)!=1:continue
        e=possible[0]
        if r['playlist_id'] is not None and r['playlist_id']!=int(e['playlist_id']):continue
        if date(r['created_at']) is None or date(r['created_at'])<since:continue
        if int(r['id']) in EXCLUDE or int(r['disabled']) or normalize(r['status'])=='superseded':
            continue
        selected.append(dict(r,ref=e['id'],expected_playlist=e['playlist_id']))
    # Multiple corrections on the same episode/type are not silently trusted.
    buckets=defaultdict(list)
    for r in selected:buckets[(r['ref'],normalize(r['segment_type']))].append(r)
    conflicts={k for k,v in buckets.items() if len(v)>1}
    return [r for r in selected if (r['ref'],normalize(r['segment_type'])) not in conflicts],automatic,conflicts


def calibrations(refs,autos):
    by_asset=defaultdict(list)
    for r in autos:
        if r['source_key'] is not None and r['playlist_id'] is not None and normalize(r['status'])!='superseded':
            by_asset[str(r['asset_key'])].append(r)
    groups=defaultdict(list)
    for r in refs:
        if r['playlist_id'] is None or r['source_key'] is None or normalize(r['segment_type'])!='outro':continue
        same=[a for a in by_asset[str(r['asset_key'])] if a['playlist_id']==r['playlist_id'] and a['source_key']==r['source_key']]
        if len(same)!=1:continue  # Never cherry-pick from contradictory autos
        a=same[0]
        if abs(a['end_ms']-r['end_ms'])>20000:continue
        shift=a['start_ms']-r['start_ms']
        if not 8000<=shift<=120000:continue
        key=(r['ref_key'][0],int(r['ref_key'][1]),int(r['playlist_id']),str(r['source_key']))
        groups[key].append((r['ref'],shift))
    models=[]
    for key,pairs in groups.items():
        if len(pairs)<4 or len(set(k for k,_ in pairs))!=len(pairs):continue
        shifts=[v for _,v in pairs]
        center=median(shifts)
        deviation=median(abs(s-center) for s in shifts)
        loo=median(abs(v-median(t for j,t in enumerate(shifts) if j!=i)) for i,v in enumerate(shifts))
        if deviation>3000 or max(shifts)-min(shifts)>10000:continue
        models.append(dict(series=key[0],season=key[1],playlist_id=key[2],source_key=key[3],
           shift_ms=round(center),reference_episodes=len(shifts),mad_ms=round(deviation),
           leave_one_out_mae_ms=round(loo),source='audio_repetition',
           status='shadow_only',publish_allowed=0))
    return models


def proposals(refs,autos,models,rows):
    known={(normalize(r['ref_key'][0]),int(r['ref_key'][1]),r['source_key'],r['playlist_id'],int(r['ref_key'][2])) for r in refs if r['playlist_id'] is not None}
    human_assets={str(r['asset_key']) for r in rows if normalize(r['source'])=='device' and normalize(r['segment_type'])=='outro'}
    produced=[]
    for m in models:
        for a in autos:
            if a['source_key']!=m['source_key'] or a['playlist_id']!=m['playlist_id'] or normalize(a['status'])!='pending':continue
            if a['ref_key'][0]!=m['series'] or a['ref_key'][1]!=m['season']:continue
            if str(a['asset_key']) in human_assets:continue
            if (a['ref_key'][0],a['ref_key'][1],a['source_key'],a['playlist_id'],a['ref_key'][2]) in known:continue
            start=a['start_ms']-m['shift_ms']
            try:duration=int(a['duration_ms'])
            except (ValueError,TypeError):continue
            if not (0.65*duration<=start<a['end_ms']<=duration+2000):continue
            produced.append(dict(auto_marker_id=int(a['id']),asset_key=str(a['asset_key']),
                series=m['series'],season=m['season'],episode=a['ref_key'][2],playlist_id=m['playlist_id'],
                original_start_ms=a['start_ms'],suggested_start_ms=start,end_ms=a['end_ms'],
                offset_ms=m['shift_ms'],status='SHADOW_REVIEW_ONLY'))
    return produced


def write(dbpath,refs,models,candidates):
    dbpath.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(dbpath) as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS owner_attested_round40(
           marker_id INTEGER PRIMARY KEY,ref TEXT NOT NULL,title TEXT NOT NULL,
           season INTEGER NOT NULL,episode INTEGER NOT NULL,playlist_id INTEGER,
           asset_key TEXT NOT NULL,kind TEXT NOT NULL,start_ms INTEGER NOT NULL,
           end_ms INTEGER NOT NULL,provenance TEXT NOT NULL,verified_backend INTEGER NOT NULL DEFAULT 0);
           CREATE TABLE IF NOT EXISTS shadow_outro_models(
           series TEXT NOT NULL,season INTEGER NOT NULL,playlist_id INTEGER NOT NULL,
           source_key TEXT NOT NULL,shift_ms INTEGER NOT NULL,reference_episodes INTEGER NOT NULL,
           mad_ms INTEGER NOT NULL,leave_one_out_mae_ms INTEGER NOT NULL,
           status TEXT NOT NULL,publish_allowed INTEGER NOT NULL,
           PRIMARY KEY(series,season,playlist_id,source_key));
           CREATE TABLE IF NOT EXISTS shadow_outro_candidates(
           auto_marker_id INTEGER PRIMARY KEY,asset_key TEXT NOT NULL,series TEXT NOT NULL,
           season INTEGER NOT NULL,episode INTEGER NOT NULL,playlist_id INTEGER NOT NULL,
           original_start_ms INTEGER NOT NULL,suggested_start_ms INTEGER NOT NULL,
           end_ms INTEGER NOT NULL,offset_ms INTEGER NOT NULL,status TEXT NOT NULL);
           ''')
        # This file is generated exclusively from source-of-truth on every run;
        # no production tables or pre-existing LearningStore labels are touched.
        for table in ('owner_attested_round40','shadow_outro_models','shadow_outro_candidates'):
            db.execute('DELETE FROM '+table)
        db.executemany('INSERT INTO owner_attested_round40 VALUES(?,?,?,?,?,?,?,?,?,?,?,0)',[
           (int(r['id']),r['ref'],r['ref_key'][0],r['ref_key'][1],r['ref_key'][2],r['playlist_id'],
            str(r['asset_key']),normalize(r['segment_type']),r['start_ms'],r['end_ms'],'owner_chat_batch_attestation_2026_10_14') for r in refs])
        db.executemany('INSERT INTO shadow_outro_models VALUES(?,?,?,?,?,?,?,?,?,?)',[
           (m['series'],m['season'],m['playlist_id'],m['source_key'],m['shift_ms'],m['reference_episodes'],
            m['mad_ms'],m['leave_one_out_mae_ms'],m['status'],m['publish_allowed']) for m in models])
        db.executemany('INSERT INTO shadow_outro_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?)',[
           (c['auto_marker_id'],c['asset_key'],c['series'],c['season'],c['episode'],c['playlist_id'],
           c['original_start_ms'],c['suggested_start_ms'],c['end_ms'],c['offset_ms'],c['status']) for c in candidates])


def run(source=ANALYZER,state=ROUND,dest=OUTPUT):
    if source.is_symlink() or not source.is_file():raise RuntimeError('Original DB unavailable')
    plan=json.loads((state/'plan.json').read_text())
    baseline=json.loads((state/'baseline.json').read_text())
    if len(plan.get('episodes',[]))!=40:raise RuntimeError('Reference plan mismatch')
    with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True,timeout=10) as source_db:
        rows=snapshot(source_db)
    refs,autos,conflicts=choose(rows,plan,baseline)
    models=calibrations(refs,autos)
    candidates=proposals(refs,autos,models,rows)
    write(dest,refs,models,candidates)
    result=dict(attested_examples=len(refs),orphaned=sum(r['playlist_id'] is None for r in refs),
        conflicted_episode_kinds=len(conflicts),verified_backend_labels=0,
        shadow_calibrations=len(models),new_shadow_outro_candidates=len(candidates),
        auto_publish=False,original_db_modified=False,
        models=[{k:v for k,v in m.items() if k!='source_key'} for m in models])
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,default=ANALYZER)
    p.add_argument('--state',type=Path,default=ROUND)
    p.add_argument('--dest',type=Path,default=OUTPUT)
    a=p.parse_args();run(a.source,a.state,a.dest)


if __name__=='__main__':main()
