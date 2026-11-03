#!/usr/bin/env python3
"""EpiScene read-only release gate preflight; never imports production worker modules."""
import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

EXPECTED_POLICY = 'chromaprint_fft_v3_1'


def evidence(raw):
    try:
        e = json.loads(raw or '{}')
    except (ValueError, TypeError):
        return {}
    return e if isinstance(e, dict) else {}


def indicators(e):
    problems = []
    if e.get('policy') != EXPECTED_POLICY:
        problems.append('policy_not_v31')
    if type(e.get('support')) is not int or not 2 <= e['support'] <= 4:
        problems.append('support_not_2_to_4')
    if e.get('truncated') is not False:
        problems.append('truncated_or_unknown')
    if e.get('ambiguous') is not False:
        problems.append('ambiguous_or_unknown')
    if e.get('boundaries_consistent') is not True:
        problems.append('boundaries_not_consistent')
    spread = e.get('boundary_spread_sec')
    if type(spread) not in (int, float) or not 0 <= spread <= 2:
        problems.append('spread_outside_0_to_2s_or_unknown')
    if e.get('audio_visual_disagreement') is True:
        problems.append('audio_visual_disagreement')
    return problems


def analyze(db):
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    tables = {
        'skip_records': ('id', 'asset_key', 'status', 'source', 'source_key',
                         'media_type', 'season', 'episode', 'duration_ms', 'segment_type'),
        'skip_assets': ('asset_key', 'source_key', 'media_type', 'season',
                        'episode', 'duration_ms', 'playlist_id'),
        'skip_auto_evidence': ('record_id', 'human_review', 'evidence_json')
    }
    for name, fields in tables.items():
        found = {r[1] for r in db.execute('PRAGMA table_info(' + name + ')')}
        if not set(fields) <= found:
            raise RuntimeError('DB schema does not match expected table: ' + name)
    sql = """SELECT r.id, r.asset_key, r.segment_type, r.source, a.playlist_id,
                    e.evidence_json
       FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
       LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
       WHERE r.status='pending' AND a.playlist_id IN (8,10)
         AND r.source IN ('audio','chapter','theintrodb','audio_repetition','auto_audio','episcene')
         AND COALESCE(e.human_review,0)=0
         AND a.source_key=r.source_key AND a.media_type=r.media_type
         AND a.season=r.season AND a.episode=r.episode
         AND a.duration_ms>0 AND ABS(a.duration_ms-r.duration_ms)<=2000"""
    counts = {8: Counter(), 10: Counter()}
    unique = {8: set(), 10: set()}
    ready_unique = {8: set(), 10: set()}
    flagged = Counter()
    kinds = Counter()
    sources = Counter()
    for row in db.execute(sql):
        pid = row['playlist_id']
        c = counts[pid]
        c['pending'] += 1
        e = evidence(row['evidence_json'])
        # Exact early-return condition shown in active skip_scene.release_ready().
        forced = e.get('episcene_required') is True and e.get('method') != 'episcene_consensus'
        if not forced:
            c['not_forced_by_this_branch'] += 1
            continue
        c['blocked_by_visual_required_branch'] += 1
        if e.get('status') != 'AUTO_CONFIRMED':
            continue
        c['audio_auto_confirmed'] += 1
        key = (row['asset_key'], row['segment_type'])
        unique[pid].add(key)
        kinds[(pid, row['segment_type'])] += 1
        sources[(pid, row['source'])] += 1
        problems = indicators(e)
        if problems:
            c['audio_evidence_has_warnings'] += 1
            for item in problems:
                flagged[(pid, item)] += 1
        else:
            c['v31_indicators_no_warnings'] += 1
            ready_unique[pid].add(key)
    return counts, unique, ready_unique, flagged, kinds, sources


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--db', default='/var/lib/epimediahub/provisioning.db')
    args = ap.parse_args()
    path = Path(args.db)
    if not path.is_file() or path.is_symlink():
        ap.error('DB is missing, not a file, or a symlink')
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=30)
    try:
        counts, unique, ready_unique, flagged, kinds, sources = analyze(db)
    finally:
        db.close()
    print('EPISCENE NUR-LESEN FREIGABE-VORPRUEFUNG')
    print('KEINE Worker-Imports, DB-Schreibzugriffe, Freigaben oder Jobstarts.')
    for pid, name in ((8, '4K ANALYSE'), (10, 'THE BEST')):
        c = counts[pid]
        print('\n' + name)
        print('  Pending mit gueltiger Asset-Zuordnung:   ', c['pending'])
        print('  Sicher vom Bildpflicht-Early-Return:     ', c['blocked_by_visual_required_branch'])
        print('  Davon Audio AUTO_CONFIRMED:              ', c['audio_auto_confirmed'])
        print('  Davon V3.1-Indikatoren ohne Warnsignale: ', c['v31_indicators_no_warnings'])
        print('  Distinkte Folge/Segment-Paare (Audio):   ', len(unique[pid]))
        print('  Distinkte Folge/Segment-Paare (V3.1):    ', len(ready_unique[pid]))
        print('  Nach Segment: ', ', '.join(f'{kind}={n}' for (p, kind), n in sorted(kinds.items()) if p == pid) or '-')
        print('  Nach Quelle:  ', ', '.join(f'{source}={n}' for (p, source), n in sorted(sources.items()) if p == pid) or '-')
        print('  Warnsignale (Mehrfachnennung moeglich):')
        warnings = [(name, n) for (p, name), n in sorted(flagged.items()) if p == pid]
        if not warnings:
            print('    keine')
        for name, n in warnings:
            print('    %-39s %d' % (name, n))
    print('\nGESAMT')
    for key in ('pending', 'blocked_by_visual_required_branch',
                'audio_auto_confirmed', 'v31_indicators_no_warnings'):
        print('  %-40s %d' % (key, sum(counts[p][key] for p in (8, 10))))
    print('\nHINWEIS: Das ist KEIN vollstaendiger Produktions-Gate-Replay!')
    print('V3.1-Indikatoren sind kein Beweis, dass alle anderen Freigabegates bestehen.')


if __name__ == '__main__':
    main()
