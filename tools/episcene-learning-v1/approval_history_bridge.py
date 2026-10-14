#!/usr/bin/env python3
"""EpiScene provenance bridge (stdlib-only, production source READ ONLY).

Root exports sanitized candidate observations to a private spool file. The
unprivileged EpiScene account imports them into new learning tables. This does
NOT assert that source='device' or reviewed_at represents a human review.
"""
from __future__ import annotations
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

ORIGINAL = '/var/lib/epimediahub/provisioning.db'
LEARNING = '/var/lib/episcene-learning/knowledge.sqlite3'
PLAYLISTS = (8,10)
STATUSES = {'approved','pending','superseded','rejected','disabled','verified'}
KINDS = {'intro','outro','recap'}
DDL = '''
CREATE TABLE IF NOT EXISTS legacy_marker_snapshots (
  source_record_id INTEGER PRIMARY KEY, asset_key TEXT NOT NULL,
  playlist_id INTEGER NOT NULL, source_key TEXT NOT NULL,
  series_title TEXT NOT NULL, season INTEGER NOT NULL,
  episode INTEGER NOT NULL, segment_type TEXT NOT NULL,
  start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,
  detector_source TEXT NOT NULL, marker_status TEXT NOT NULL,
  confidence REAL, reviewed_at TEXT, created_at TEXT,
  provenance TEXT NOT NULL DEFAULT 'unverified_source_status',
  imported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS legacy_marker_asset_idx ON
  legacy_marker_snapshots(asset_key,segment_type);
CREATE TABLE IF NOT EXISTS legacy_app_window_observations (
  asset_key TEXT PRIMARY KEY, playlist_id INTEGER NOT NULL,
  window_count INTEGER NOT NULL, first_received TEXT, latest_received TEXT,
  provenance TEXT NOT NULL DEFAULT 'app_window_unverified',
  imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS legacy_sync_meta (
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);
'''


def utc_now():return datetime.now(timezone.utc).isoformat()


def read_only_db(path):
    p=Path(path)
    if not p.is_file() or p.is_symlink(): raise FileNotFoundError('Original analyzer database missing or symlink')
    db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro', uri=True, timeout=3)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def columns(db, name):
    assert name in {'skip_assets','skip_records','skip_app_windows'}
    return {r['name'] for r in db.execute('PRAGMA table_info('+name+')')}


def sanitize(row):
    try:
        r=dict(row)
        pl=int(r['playlist_id']);st=int(r['start_ms']);en=int(r['end_ms'])
        season=int(r['season']);ep=int(r['episode'])
        kind=str(r['segment_type'] or '').lower().strip()
        status=str(r['status'] or '').lower().strip()
        if pl not in PLAYLISTS or kind not in KINDS or status not in STATUSES:return None
        if not(0<=st<en<=86400000 and season>=0 and ep>=0):return None
        asset=str(r['asset_key'] or '')[:240]
        source=str(r['source_key'] or '')[:240]
        title=str(r['title'] or '')[:240]
        if not asset or not source or not title:return None
        confidence=r['confidence']
        if confidence is not None:
            confidence=float(confidence)
            if not 0<=confidence<=1:confidence=None
        return [int(r['id']),asset,pl,source,title,season,ep,kind,st,en,
                str(r['source'] or '')[:60],status,confidence,
                str(r['reviewed_at'])[:80] if r['reviewed_at'] is not None else None,
                str(r['created_at'])[:80] if r['created_at'] is not None else None]
    except (ValueError,TypeError,KeyError,OverflowError):return None


def export_source(source_path, dest_path):
    """Called as root; creates 0600 file in existing protected spool directory."""
    file=Path(dest_path)
    if file.exists() or file.is_symlink() or not file.parent.is_dir():
        raise RuntimeError('Export destination must not exist; protected spool dir required')
    with closing(read_only_db(source_path)) as db:
        required_records={'id','asset_key','segment_type','start_ms','end_ms','source','status','confidence','reviewed_at','created_at'}
        required_assets={'asset_key','source_key','playlist_id','season','episode','title'}
        if not required_records<=columns(db,'skip_records') or not required_assets<=columns(db,'skip_assets'):
            raise RuntimeError('Incompatible analyzer schema; no changes made')
        scanned=valid=windows=0
        with file.open('x',encoding='utf-8') as out:
            file.chmod(0o600)
            rows=db.execute('''SELECT r.id,r.asset_key,a.source_key,a.playlist_id,
              a.title,a.season,a.episode,r.segment_type,r.start_ms,r.end_ms,
              r.source,r.status,r.confidence,r.reviewed_at,r.created_at
              FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
              WHERE a.playlist_id IN (?,?) ORDER BY r.id''',PLAYLISTS)
            for row in rows:
                scanned+=1
                clean=sanitize(row)
                if clean is None:continue
                out.write(json.dumps({'type':'marker','row':clean},ensure_ascii=False,allow_nan=False)+'\n')
                valid+=1
            if {'asset_key','received_at'}<=columns(db,'skip_app_windows'):
                for row in db.execute('''SELECT w.asset_key,a.playlist_id,
                    COUNT(*) AS n,MIN(w.received_at) AS first_at,MAX(w.received_at) AS last_at
                    FROM skip_app_windows w JOIN skip_assets a ON a.asset_key=w.asset_key
                    WHERE a.playlist_id IN (?,?) GROUP BY w.asset_key,a.playlist_id''',PLAYLISTS):
                    clean=[str(row['asset_key'])[:240],int(row['playlist_id']),int(row['n']),
                           str(row['first_at'])[:80] if row['first_at'] is not None else None,
                           str(row['last_at'])[:80] if row['last_at'] is not None else None]
                    out.write(json.dumps({'type':'app_window','row':clean},ensure_ascii=False)+'\n')
                    windows+=int(row['n'])
        print(json.dumps({'exported_marker_candidates':valid,'scanned':scanned,
                          'app_window_observations':windows,'verified_labels':0}))


def import_candidates(source_path, target_path):
    """Called as episcene-learning unprivileged user; never alters labels."""
    target=Path(target_path)
    if not target.is_file() or target.is_symlink():raise FileNotFoundError('Learning DB missing')
    inp=Path(source_path)
    if not inp.is_file() or inp.is_symlink():raise ValueError('Protected source file required')
    with sqlite3.connect(target,timeout=10) as db:
        db.row_factory=sqlite3.Row
        db.executescript(DDL)
        imported=0;apps=0
        marker_sql='''INSERT INTO legacy_marker_snapshots VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'unverified_source_status',?)
            ON CONFLICT(source_record_id) DO UPDATE SET
            asset_key=excluded.asset_key,playlist_id=excluded.playlist_id,
            source_key=excluded.source_key,series_title=excluded.series_title,
            season=excluded.season,episode=excluded.episode,segment_type=excluded.segment_type,
            start_ms=excluded.start_ms,end_ms=excluded.end_ms,
            detector_source=excluded.detector_source,marker_status=excluded.marker_status,
            confidence=excluded.confidence,reviewed_at=excluded.reviewed_at,
            provenance='unverified_source_status',imported_at=excluded.imported_at'''
        app_sql='''INSERT INTO legacy_app_window_observations VALUES
            (?,?,?,?,?,'app_window_unverified',?) ON CONFLICT(asset_key) DO UPDATE SET
            window_count=excluded.window_count,first_received=excluded.first_received,
            latest_received=excluded.latest_received,imported_at=excluded.imported_at'''
        with inp.open('r',encoding='utf-8') as stream:
            with db:
                for line in stream:
                    record=json.loads(line)
                    row=record.get('row')
                    if record.get('type')=='marker' and isinstance(row,list) and len(row)==15:
                        db.execute(marker_sql,row+[utc_now()]);imported+=1
                    elif record.get('type')=='app_window' and isinstance(row,list) and len(row)==5:
                        db.execute(app_sql,row+[utc_now()]);apps+=int(row[2])
                    else:raise ValueError('Unexpected spool event; refusing import')
                db.execute('INSERT OR REPLACE INTO legacy_sync_meta VALUES (?,?)',('last_sync_at',utc_now()))
        src={r['detector_source']:r['n'] for r in db.execute('''SELECT detector_source,COUNT(*) n
             FROM legacy_marker_snapshots WHERE marker_status='approved' GROUP BY detector_source''')}
        statuses={r['marker_status']:r['n'] for r in db.execute('''SELECT marker_status,COUNT(*) n
             FROM legacy_marker_snapshots GROUP BY marker_status''')}
        result={'status':'ok','mode':'shadow','marker_candidates_synced':imported,
                'app_windows_synced':apps,'status_counts':statuses,
                'approved_candidates_by_source':src,'verified_human_labels_added':0,
                'automatic_publication_enabled':False}
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['export','import'])
    p.add_argument('--db')
    p.add_argument('--file',required=True)
    a=p.parse_args()
    if a.action=='export':export_source(a.db or ORIGINAL,a.file)
    else:import_candidates(a.file,a.db or LEARNING)

if __name__=='__main__':main()
