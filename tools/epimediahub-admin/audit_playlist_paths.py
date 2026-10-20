#!/usr/bin/env python3
"""Read-only source/DB shape report for EpiScene playlist credential rotation.

Emits ONLY schema column names, row counts, and source file/line numbers.
Never selects URL/credential values, imports production modules, prints code
lines or changes files/services. No network access or side effects.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sqlite3

TABLES = (
    'customer_playlists', 'skip_analysis_sources', 'skip_assets',
    'skip_jobs', 'skip_catalogue',
)
SOURCE_FILES = (
    'skip_catalogue.py', 'skip_automation.py', 'skip_analysis_worker.py',
    'skip_analysis.py', 'skip_schedule.py', 'skip_remote_client.py',
    'skip_provider.py', 'skip_sources.py',
)
RELEVANT = re.compile(
    r'(username|password|stream_url|source_url|base_url|playlist_id|provider_url|'
    r'playlist_url|skip_assets|customer_playlists|probe\()', re.I,
)


def _columns(con, table: str) -> list[str]:
    # Identifiers only originate from the fixed allowlist above.
    return [row[1] for row in con.execute(f'PRAGMA table_info("{table}")')]


def audit_database(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        return {'status': 'SOURCE_UNAVAILABLE'}
    result = {'status': 'READ_ONLY', 'tables': {}}
    uri = path.resolve().as_uri() + '?mode=ro'
    with sqlite3.connect(uri, uri=True, timeout=10) as con:
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')
        for table in TABLES:
            cols = _columns(con, table)
            if not cols:
                result['tables'][table] = {'present': False}
                continue
            names = {x.lower() for x in cols}
            candidate = [x for x in cols if any(t in x.lower() for t in
                         ('url', 'uri', 'username', 'password', 'auth', 'secret', 'token',
                          'stream', 'source', 'host', 'server', 'credential'))]
            info: dict = {
                'present': True,
                'possible_url_or_access_columns': candidate,
                'has_playlist_id': 'playlist_id' in names,
            }
            if 'playlist_id' in names:
                records = con.execute(f'''SELECT playlist_id, COUNT(*)
                    FROM "{table}" WHERE playlist_id IN (8,10)
                    GROUP BY playlist_id''').fetchall()
                info['records_per_analysis_playlist'] = {
                    str(id_): count for id_, count in records
                }
            elif table == 'customer_playlists' and 'id' in names:
                records = con.execute('''SELECT id FROM "customer_playlists"
                    WHERE id IN (8,10)''').fetchall()
                info['existing_analysis_playlist_ids'] = [x[0] for x in records]
            result['tables'][table] = info
    return result


def audit_source_locations(base: Path) -> dict:
    result = {}
    for filename in SOURCE_FILES:
        source = base / filename
        if source.is_symlink() or not source.is_file():
            continue
        # Regex only yields bounded line numbers, never production code.
        matches = [n for n, line in enumerate(
            source.read_text(encoding='utf-8', errors='replace').splitlines(), 1
        ) if RELEVANT.search(line)]
        result[filename] = {
            'matching_lines': len(matches),
            'first_line_numbers': matches[:20],
        }
    return result


def report(db_path: Path, code_root: Path) -> dict:
    return {
        'diagnostic': 'episcene_playlist_source_reference_shape_v1',
        'safety': 'read_only_no_values_no_credentials',
        'analysis_playlist_ids': [8, 10],
        'database': audit_database(db_path),
        'source_references': audit_source_locations(code_root),
        'interpretation':
            'This report shows candidate locations and row counts, NOT proof '
            'that saved URLs are stale.',
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', type=Path,
                   default=Path('/var/lib/epimediahub/provisioning.db'))
    p.add_argument('--app', type=Path,
                   default=Path('/opt/epimediahub/provisioning'))
    args = p.parse_args()
    print(json.dumps(report(args.db, args.app), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
