#!/usr/bin/env python3
"""EpiScene Knowledge First: count confirmed, already completed reuse jobs.

Read-only and privacy-preserving. In deployed EpiScene, jobs carry the
segment *kind* inside their exact detail message, not a skip_jobs.kind
column. Do not infer saved jobs from installed code or cache hits.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3

SOURCE = Path('/var/lib/epimediahub/provisioning.db')
PATTERN = re.compile(r'^EpiScene Knowledge First: (intro|recap|outro) aus (own|introdb|theintrodb) wiederverwendet$')
NEEDED_JOBS = {'id', 'asset_key', 'status', 'detail', 'updated_at'}
NEEDED_ASSETS = {'asset_key', 'playlist_id'}
PLAYLISTS = (8, 10)
KINDS = ('intro', 'recap', 'outro')
ORIGINS = ('own', 'introdb', 'theintrodb')


def _columns(conn, table):
    return {row[1] for row in conn.execute('PRAGMA table_info(' + table + ')')}


def report(path=SOURCE, *, hours=24, current=None):
    if type(hours) is not int or not (1 <= hours <= 720):
        return {'status': 'STOP_INVALID_WINDOW', 'mode': 'READ_ONLY'}
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        return {'status': 'STOP_SOURCE_MISSING', 'mode': 'READ_ONLY'}
    timestamp = current if current is not None else datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError('timestamp must contain timezone')
    since = (timestamp.astimezone(timezone.utc)-timedelta(hours=hours)).isoformat(timespec='seconds')[:19]
    counts = Counter()
    scanned = 0
    try:
        with sqlite3.connect(p.resolve().as_uri() + '?mode=ro', uri=True, timeout=6) as conn:
            conn.execute('PRAGMA query_only=ON')
            if not (NEEDED_JOBS <= _columns(conn, 'skip_jobs') and
                    NEEDED_ASSETS <= _columns(conn, 'skip_assets')):
                return {'status': 'STOP_UNEXPECTED_SCHEMA', 'mode': 'READ_ONLY',
                        'needs': 'skip_jobs(id,asset_key,status,detail,updated_at) and skip_assets(asset_key,playlist_id)',
                        'no_source_data_modified': True}
            query = '''SELECT j.detail,
                (SELECT MIN(a.playlist_id) FROM skip_assets a
                 WHERE a.asset_key=j.asset_key AND a.playlist_id IN (8,10)) playlist_id
                FROM skip_jobs j
                WHERE j.status='done' AND j.detail LIKE 'EpiScene Knowledge First:%'
                  AND j.updated_at>=?
                  AND EXISTS (SELECT 1 FROM skip_assets a WHERE a.asset_key=j.asset_key
                              AND a.playlist_id IN (8,10))
                ORDER BY j.id LIMIT 50000'''
            for detail, playlist in conn.execute(query, (since,)):
                scanned += 1
                if type(detail) is not str or playlist not in PLAYLISTS:
                    continue
                match = PATTERN.fullmatch(detail)
                if match:
                    kind, source = match.groups()
                    counts[(playlist, kind, source)] += 1
    except sqlite3.Error:
        return {'status':'STOP_DATABASE_READ_FAILED','mode':'READ_ONLY',
                'no_source_data_modified':True}

    return {'status':'MEASURED', 'mode':'READ_ONLY','window_hours':hours,
            'confirmed_completed_reuses':sum(counts.values()),
            'by_playlist':{str(playlist): {
                kind:{origin:counts[(playlist,kind,origin)] for origin in ORIGINS}
                for kind in KINDS} for playlist in PLAYLISTS},
            'candidate_details_checked':scanned,
            'note':'Only exact completed Knowledge First job messages are counted; 0 does not prove the worker has started.',
            'database_modified':False,'provider_requests':0,
            'customer_identifiers_exported':False}

if __name__=='__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--hours',type=int,default=24)
    args=ap.parse_args()
    print(json.dumps(report(hours=args.hours),ensure_ascii=False,indent=2))
