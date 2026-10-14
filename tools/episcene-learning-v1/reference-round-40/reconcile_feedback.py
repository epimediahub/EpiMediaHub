#!/usr/bin/env python3
"""Read-only recovery of orphaned EpiScene reference markers after round 40.

Does not change original DB, baseline, training labels, or approved markers.
"""
from __future__ import annotations
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

STATE = Path('/var/lib/episcene-learning/reference-round-40')
DB = Path('/var/lib/epimediahub/provisioning.db')
ORIGINS = {'device', 'manual', 'app', 'user'}
KINDS = {'intro', 'recap', 'outro'}


def norm(text):
    return ' '.join(str(text or '').casefold().split())


def parse_utc(text):
    try:
        dt = datetime.fromisoformat(str(text).replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (TypeError, ValueError):
        return None


def inspect(db, plan, baseline):
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    for table, required in {
        'skip_records': {'id', 'asset_key', 'title', 'season', 'episode', 'segment_type', 'source',
                         'status', 'start_ms', 'end_ms', 'created_at'},
        'skip_assets': {'asset_key', 'playlist_id', 'title', 'season', 'episode'}
    }.items():
        actual = {x[1] for x in db.execute('PRAGMA table_info(' + table + ')')}
        if not required.issubset(actual):
            raise RuntimeError('Schema changed: ' + table)
    plan_index = {}
    for e in plan['episodes']:
        key = (norm(e['series']), int(e['season']), int(e['episode']))
        plan_index.setdefault(key, []).append(e)
    old = parse_utc(baseline['recorded_utc'])
    if old is None:
        raise RuntimeError('Invalid baseline timestamp')
    result = []
    rows = db.execute('''
        SELECT r.id, r.title AS marker_title, r.season AS marker_season,
          r.episode AS marker_episode, r.segment_type, r.source, r.status,
          r.start_ms, r.end_ms, r.created_at,
          a.title AS asset_title, a.playlist_id, a.season AS asset_season,
          a.episode AS asset_episode, a.asset_key AS linked_asset
        FROM skip_records r LEFT JOIN skip_assets a ON r.asset_key=a.asset_key
        WHERE a.asset_key IS NULL
          AND lower(r.source) IN ('device','manual','app','user')
          AND lower(r.segment_type) IN ('intro','recap','outro')
    ''')
    for r in rows:
        try:
            start, end = int(r['start_ms']), int(r['end_ms'])
            season, episode = int(r['marker_season']), int(r['marker_episode'])
            rid = int(r['id'])
        except (ValueError, TypeError):
            continue
        if not 0 <= start < end <= 86400000:
            continue
        key = (norm(r['marker_title']), season, episode)
        matching = plan_index.get(key, [])
        if len(matching) != 1:  # no playlist evidence; do not guess
            continue
        created = parse_utc(r['created_at'])
        if created is None or created < old:
            continue
        result.append({
            'ref': matching[0]['id'], 'playlist_inferred': None, 'record_id': rid,
            'kind': norm(r['segment_type']), 'start_ms': start, 'end_ms': end,
            'source': str(r['source']), 'status': str(r['status']),
            'created_at': str(r['created_at']),
        })
    return sorted(result, key=lambda x: (x['ref'], x['record_id']))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--state', type=Path, default=STATE)
    p.add_argument('--db', type=Path, default=DB)
    opts = p.parse_args()
    if opts.db.is_symlink() or not opts.db.is_file():
        p.error('Original database missing or unexpected symlink')
    plan = json.loads((opts.state/'plan.json').read_text(encoding='utf-8'))
    baseline = json.loads((opts.state/'baseline.json').read_text(encoding='utf-8'))
    status = json.loads((opts.state/'status.json').read_text(encoding='utf-8'))
    if len(plan.get('episodes', [])) != 40 or status.get('planned_episodes') != 40:
        raise RuntimeError('Unexpected reference plan')
    with sqlite3.connect(opts.db.resolve().as_uri()+'?mode=ro', uri=True, timeout=10) as db:
        orphans = inspect(db, plan, baseline)
    linked = {e['id'] for e in status['episodes'] if e['new_or_changed']}
    orphaned_episodes = {e['ref'] for e in orphans}
    recovered = orphaned_episodes - linked
    remaining = sorted({e['id'] for e in plan['episodes']} - linked - orphaned_episodes)
    print('=== EPISCENE RUNDE 40: ERGAENZENDE AUSWERTUNG (NUR LESEN) ===')
    print('Bereits zugeordnete Episoden:', len(linked))
    print('Zusaetzlich gefundene Episoden mit neuen Markern ohne Asset:', len(recovered))
    print('Gefundene unverbundene Marker:', len(orphans))
    print('Folgen mit neuen/veranderten Markern gesamt:', len(linked | orphaned_episodes), '/ 40')
    for x in orphans:
        print(f"{x['ref']} | ID #{x['record_id']} | {x['kind']} | "
              f"{x['start_ms']/1000:.3f}-{x['end_ms']/1000:.3f}s | "
              f"{x['source']}/{x['status']} | OHNE PLAYLIST-ZUORDNUNG")
    print('Ohne neue Marker nach der Baseline:', ', '.join(remaining) or 'keine')
    print('Korrekturhinweis: Berlino S1E2 #2283 bestaetigt, #2282 verworfen.')
    print('Bridgerton S1E1 #2291, S1E2 #2293, S1E3 #2295: vom Nutzer bestaetigte Intros.')
    print('ACHTUNG: Keine Playlistzuordnung fuer verwaiste Marker erfunden.')
    print('Keine Trainingslabels freigegeben; die Datenbank blieb unveraendert.')


if __name__ == '__main__':
    main()
