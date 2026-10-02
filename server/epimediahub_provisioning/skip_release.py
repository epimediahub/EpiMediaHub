"""Automatic acceptance of detected times, with durable manual corrections."""
from __future__ import annotations

import json
from collections import defaultdict

from skip_markers import now, valid_range

MACHINE_SOURCES = ('audio', 'chapter', 'theintrodb', 'audio_repetition', 'auto_audio')
POLICY = 'automatic_acceptance_v1'


def migrate(con):
    con.executescript('''
      CREATE TABLE IF NOT EXISTS skip_release_settings(
        playlist_id INTEGER PRIMARY KEY REFERENCES customer_playlists(id) ON DELETE CASCADE,
        enabled INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_auto_reference_checks(
        record_id INTEGER PRIMARY KEY REFERENCES skip_records(id) ON DELETE CASCADE,
        fingerprint_created_at TEXT NOT NULL,checked_at INTEGER NOT NULL);
    ''')
    if not con.execute('SELECT 1 FROM skip_auto_maintenance WHERE name=?', (POLICY,)).fetchone():
        accept_pending(con)
        con.execute('INSERT OR IGNORE INTO skip_auto_maintenance VALUES(?,?)', (POLICY, now()))


def enabled(con, playlist_id):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='skip_release_settings'").fetchone():
        return False  # Older read-only diagnostic snapshots have no new setting.
    row = con.execute('''SELECT COALESCE(r.enabled,1) FROM skip_analysis_sources s
      JOIN customer_playlists p ON p.id=s.playlist_id
      JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      LEFT JOIN skip_release_settings r ON r.playlist_id=p.id
      WHERE s.playlist_id=? AND s.enabled=1''', (playlist_id,)).fetchone()
    return bool(row and row[0])


def choose(rows):
    from skip_automation import PROPOSAL_RANK
    return max(rows, key=lambda r: (r['human_review'] or r['source'] == 'device',
                                   PROPOSAL_RANK.get(r['source'], 5 if r['source'] == 'auto_audio' else 0),
                                   r['confidence'], r['id']))


def approve_rows(con, rows, human=False):
    """Resolve alternatives per actual file/kind/runtime, without leaving duplicates pending."""
    from skip_markers import review_record, wake_reference_jobs
    buckets = defaultdict(list)
    for row in rows:
        buckets[(row['asset_key'], row['segment_type'])].append(row)
    counts = dict(approved=0, duplicates=0, conflicts=0, protected=0, invalid=0)
    wake = set()
    for versions in buckets.values():
        batches = []
        for row in sorted(versions, key=lambda r: (r['duration_ms'], r['id'])):
            if not batches or row['duration_ms'] - batches[-1][0]['duration_ms'] > 2000:
                batches.append([])
            batches[-1].append(row)
        for batch in batches:
            first = batch[0]
            decided = con.execute('''SELECT r.source,r.status,COALESCE(e.human_review,0) human_review
              FROM skip_records r LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
              WHERE r.asset_key=? AND r.segment_type=?
              AND ABS(r.duration_ms-?)<=2000 AND r.status IN ('approved','rejected')''',
              (first['asset_key'], first['segment_type'], first['duration_ms'])).fetchall()
            blocked = con.execute('''SELECT 1 FROM skip_auto_blocks WHERE asset_key=? AND kind=?
              AND ABS(duration_ms-?)<=2000 LIMIT 1''',
              (first['asset_key'], first['segment_type'], first['duration_ms'])).fetchone()
            if (human and any(r['source']=='device' or r['human_review'] for r in batch)
                    and all(r['status']=='approved' and r['source'] in MACHINE_SOURCES and not r['human_review'] for r in decided)):
                decided = []  # An explicit pending correction replaces a machine mark.
            if decided or blocked:
                # Already decided markers stay authoritative. Old generated
                # proposals disappear from the review queue instead of looking stuck.
                for row in batch:
                    if row['source'] in MACHINE_SOURCES and not row['human_review']:
                        con.execute("UPDATE skip_records SET status='superseded' WHERE id=? AND status='pending'", (row['id'],))
                counts['protected'] += len(batch)
                continue
            valid = [r for r in batch if valid_range(r['segment_type'], r['start_ms'], r['end_ms'],
                                                     r['duration_ms'], bool(r['disabled']))]
            counts['invalid'] += len(batch) - len(valid)
            if not valid:
                continue
            winner = choose(valid)
            if human:
                review_record(con, winner, 'approve', winner['start_ms'], winner['end_ms'], bool(winner['disabled']), wake=False)
            else:
                try:
                    evidence = json.loads(winner['evidence_json'] or '{}')
                    if not isinstance(evidence, dict):
                        evidence = {}
                except (ValueError, TypeError):
                    evidence = {}
                evidence['automatic_acceptance'] = True
                con.execute('INSERT OR REPLACE INTO skip_auto_evidence VALUES(?,?,0)',
                            (winner['id'], json.dumps(evidence)))
                con.execute("UPDATE skip_records SET status='approved',reviewed_at=? WHERE id=? AND status='pending'", (now(), winner['id']))
            for row in valid:
                if row['id'] != winner['id']:
                    con.execute("UPDATE skip_records SET status='superseded',reviewed_at=? WHERE id=? AND status='pending'", (now(), row['id']))
            counts['approved'] += 1
            counts['duplicates'] += len(valid) - 1
            if any((r['start_ms'], r['end_ms'], r['disabled']) != (winner['start_ms'], winner['end_ms'], winner['disabled']) for r in valid):
                counts['conflicts'] += 1
            if not winner['disabled']:
                wake.add((winner['source_key'], winner['season']))
    for source_key, season in wake:
        wake_reference_jobs(con, source_key, season)
    return counts


def accept_pending(con, asset_key=None, playlist_id=None):
    if not con.in_transaction:
        con.execute('BEGIN IMMEDIATE')
    sql = '''SELECT r.*,COALESCE(e.human_review,0) human_review,e.evidence_json,a.playlist_id
      FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
      LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
      WHERE r.status='pending' AND r.source IN ('audio','chapter','theintrodb','audio_repetition','auto_audio')
      AND COALESCE(e.human_review,0)=0 AND a.source_key=r.source_key AND a.media_type=r.media_type
      AND a.season=r.season AND a.episode=r.episode AND a.duration_ms>0 AND ABS(a.duration_ms-r.duration_ms)<=2000'''
    params = []
    if asset_key is not None:
        sql += ' AND a.asset_key=?'
        params.append(asset_key)
    if playlist_id is not None:
        sql += ' AND a.playlist_id=?'
        params.append(playlist_id)
    settings = {}
    rows = []
    for row in con.execute(sql, params).fetchall():
        if row['playlist_id'] not in settings:
            settings[row['playlist_id']] = enabled(con, row['playlist_id'])
        if settings[row['playlist_id']] and current_reference(con, row):
            rows.append(row)
    # A device proposal represents a correction in progress, not a machine competitor.
    rows = [r for r in rows if not con.execute('''SELECT 1 FROM skip_records d
      LEFT JOIN skip_auto_evidence e ON e.record_id=d.id WHERE d.asset_key=? AND d.segment_type=?
      AND ABS(d.duration_ms-?)<=2000 AND d.status='pending'
      AND (d.source='device' OR e.human_review=1) LIMIT 1''',
      (r['asset_key'], r['segment_type'], r['duration_ms'])).fetchone()]
    return approve_rows(con, rows)['approved']


def current_reference(con, row):
    """Do not publish a result computed from a reference corrected in the meantime."""
    try:
        evidence = json.loads(row['evidence_json'] or '{}')
    except (ValueError,TypeError):
        evidence = {}
    if not isinstance(evidence,dict) or evidence.get('method')!='reviewed_audio_match':
        return True
    vote = evidence.get('vote',{})
    ref = con.execute('''SELECT r.* FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
      JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
      JOIN customer_playlists p ON p.id=a.playlist_id JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      WHERE r.id=? AND r.status='approved' AND r.disabled=0 AND r.source_key=a.source_key
      AND r.season=a.season AND r.episode=a.episode AND ABS(r.duration_ms-a.duration_ms)<=2000''',
      (vote.get('record_id'),)).fetchone() if isinstance(vote,dict) else None
    valid = (ref and ref['source_key']==row['source_key'] and ref['season']==row['season']
             and ref['segment_type']==row['segment_type'] and ref['reviewed_at']==vote.get('reviewed_at')
             and ref['start_ms']==vote.get('ref_start') and ref['end_ms']==vote.get('ref_end'))
    if not valid:
        con.execute("UPDATE skip_records SET status='superseded' WHERE id=? AND status='pending'",(row['id'],))
    return bool(valid)


def approve_scope(con, source_key, season=None):
    if not con.in_transaction:
        con.execute('BEGIN IMMEDIATE')
    sql = '''SELECT r.*,COALESCE(e.human_review,0) human_review,e.evidence_json FROM skip_records r
      LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
      WHERE r.status='pending' AND r.media_type='episode' AND r.source_key=?'''
    params = [source_key]
    if season is not None:
        sql += ' AND r.season=?'
        params.append(season)
    return approve_rows(con, con.execute(sql, params).fetchall(), human=True)
