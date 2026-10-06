"""Automatic acceptance of detected times, with durable manual corrections."""
from __future__ import annotations

import json
import hashlib
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
    from skip_automation import proposal_rank
    return max(rows, key=lambda r: (r['human_review'] or r['source'] == 'device',
                                   proposal_rank(r)[0],
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
                    if human or (row['source'] in MACHINE_SOURCES and not row['human_review']):
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
        if settings[row['playlist_id']] and current_reference(con, row) and reviewed_release_ready(row) and detector_release_ready(con, row):
            rows.append(row)
    # Do not bypass consensus() by independently accepting two disagreeing
    # strong reference matches after the consensus deliberately returned None.
    reviewed = defaultdict(list)
    for row in rows:
        try:
            evidence = json.loads(row['evidence_json'] or '{}')
        except (ValueError, TypeError):
            continue
        if isinstance(evidence, dict) and evidence.get('method') == 'reviewed_audio_match':
            reviewed[(row['asset_key'], row['segment_type'])].append(row)
    from skip_automation import BOUNDARY_TOLERANCE
    disputed = {key for key, versions in reviewed.items()
                if max(r['start_ms'] for r in versions)-min(r['start_ms'] for r in versions)>BOUNDARY_TOLERANCE
                or max(r['end_ms'] for r in versions)-min(r['end_ms'] for r in versions)>BOUNDARY_TOLERANCE}
    rows = [r for r in rows if (r['asset_key'], r['segment_type']) not in disputed]
    # A device proposal represents a correction in progress, not a machine competitor.
    rows = [r for r in rows if not con.execute('''SELECT 1 FROM skip_records d
      LEFT JOIN skip_auto_evidence e ON e.record_id=d.id WHERE d.asset_key=? AND d.segment_type=?
      AND ABS(d.duration_ms-?)<=2000 AND d.status='pending'
      AND (d.source='device' OR e.human_review=1) LIMIT 1''',
      (r['asset_key'], r['segment_type'], r['duration_ms'])).fetchone()]
    return approve_rows(con, rows)['approved']


def reviewed_release_ready(row):
    try:
        evidence = json.loads(row['evidence_json'] or '{}')
    except (ValueError, TypeError):
        return True
    if not isinstance(evidence, dict) or evidence.get('method') != 'reviewed_audio_match':
        return True
    from skip_automation import AUTO_CONFIDENCE
    vote = evidence.get('vote')
    return (isinstance(vote, dict) and vote.get('boundaries_confirmed') is True
            and type(vote.get('confidence')) in (float, int)
            and AUTO_CONFIDENCE <= vote['confidence'] <= 1
            and AUTO_CONFIDENCE <= row['confidence'] <= 1)


def detector_release_ready(con, row):
    """Allow automatic publication only from reproducible V2/V3 detector evidence."""
    from skip_detector_v2 import POLICY as v2_policy
    v3_policy = 'chromaprint_fft_v3_1'
    try:
        evidence = json.loads(row['evidence_json'] or '{}')
    except (ValueError, TypeError):
        evidence = {}
    if not isinstance(evidence, dict):
        return True

    policy = evidence.get('policy')
    method = evidence.get('method')
    if policy not in (v2_policy, v3_policy) and method not in ('episode_consensus', 'episode_consensus_v3'):
        return True

    if policy == v2_policy:
        if (method != 'episode_consensus' or evidence.get('status') != 'AUTO_CONFIRMED'
                or not .92 <= row['confidence'] <= 1):
            return False
        for name, low, high in (('min_pair_quality', .92, 1), ('min_match_ratio', .90, 1),
                                ('boundary_spread_sec', 0, 1)):
            value = evidence.get(name)
            if type(value) not in (int, float) or not low <= value <= high:
                return False
        windows = evidence.get('windows')
        support = evidence.get('support')
        if type(support) is not int or not 3 <= support <= 4 or not isinstance(windows, list) or len(windows) != support + 1:
            return False

    elif policy == v3_policy:
        if (method != 'episode_consensus_v3' or evidence.get('status') != 'AUTO_CONFIRMED'
                or not .92 <= row['confidence'] <= 1 or evidence.get('truncated') is True):
            return False
        if evidence.get('precision_policy') == 'audio_consensus_precision_v1':
            if evidence.get('ambiguous') is not False or evidence.get('boundaries_consistent') is not True:
                return False
            markers=evidence.get('trusted_markers')
            if not isinstance(markers,list):
                return False
            for marker in markers:
                if not isinstance(marker, dict):
                    return False
                if not con.execute('''SELECT 1 FROM skip_records r
                  LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
                  WHERE r.id=? AND r.asset_key=? AND r.start_ms=? AND r.end_ms=?
                  AND r.reviewed_at IS ? AND r.status='approved' AND r.disabled=0
                  AND (r.source='device' OR COALESCE(e.human_review,0)=1)''',
                  (marker.get('id'),marker.get('asset_key'),marker.get('start_ms'),
                   marker.get('end_ms'),marker.get('reviewed_at'))).fetchone():
                    return False
        mean_q = evidence.get('mean_pair_quality')
        spread = evidence.get('boundary_spread_sec')
        position = evidence.get('position_plausibility')
        support = evidence.get('support')
        attempted = evidence.get('attempted_partners')
        windows = evidence.get('windows')
        trusted = evidence.get('trusted_episodes', [])
        if (type(mean_q) not in (int, float) or not .90 <= mean_q <= 1
                or type(spread) not in (int, float) or not 0 <= spread <= 2.0
                or type(position) not in (int, float) or not 0 <= position <= 1
                or type(support) is not int or not 2 <= support <= 4
                or type(attempted) is not int or not support <= attempted <= 4
                or not isinstance(windows, list) or len(windows) != attempted + 1
                or not isinstance(trusted, list)
                or len(trusted) != len(set(trusted))
                or any(type(x) is not int for x in trusted)
                or (support == 2 and not trusted)):
            return False
    else:
        return False

    used, own, cached_by_episode = set(), False, {}
    for item in windows:
        if not isinstance(item, dict):
            return False
        if item.get('origin') == 'app' and policy == v3_policy:
            from skip_app_capture import windows as app_windows
            cached = next((w for w in app_windows(con, row, row['segment_type'])
                           if w['asset_key'] == item.get('asset_key')), None)
        elif item.get('origin', 'server') == 'server':
            cached = con.execute('''SELECT w.*,a.source_key,a.season,a.episode,a.duration_ms current_duration
          FROM skip_auto_windows w JOIN skip_assets a ON a.asset_key=w.asset_key
          JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
          JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
          JOIN customer_playlists p ON p.id=a.playlist_id JOIN customers c ON c.id=p.customer_id AND c.enabled=1
          WHERE w.asset_key=? AND w.kind=? AND NOT EXISTS (
            SELECT 1 FROM skip_auto_blocks b WHERE b.asset_key=a.asset_key AND b.kind=w.kind
            AND ABS(b.duration_ms-a.duration_ms)<=2000)''', (item.get('asset_key'), row['segment_type'])).fetchone()
        else:
            return False
        if (not cached or cached['source_key'] != row['source_key'] or cached['season'] != row['season']
                or cached['episode'] in used or abs(cached['duration_ms'] - cached['current_duration']) > 2000
                or any(cached[k] != item.get(k) for k in ('episode','duration_ms','offset_ms','length_ms','step_ms'))
                or hashlib.sha256(cached['words_json'].encode()).hexdigest() != item.get('fingerprint_sha256')):
            return False
        used.add(cached['episode'])
        cached_by_episode[cached['episode']] = cached
        own |= cached['asset_key'] == row['asset_key'] and cached['episode'] == row['episode']

    if policy == v3_policy:
        for episode in evidence.get('trusted_episodes', []):
            cached = cached_by_episode.get(episode)
            if not cached:
                return False
            if evidence.get('precision_policy') == 'audio_consensus_precision_v1' and not any(
                    item['asset_key']==cached['asset_key'] for item in evidence['trusted_markers']):
                return False
            human = con.execute('''SELECT 1 FROM skip_records r
              LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
              WHERE r.asset_key=? AND r.segment_type=? AND r.status='approved' AND r.disabled=0
              AND ABS(r.duration_ms-?)<=2000 AND (r.source='device' OR COALESCE(e.human_review,0)=1)
              LIMIT 1''', (cached['asset_key'], row['segment_type'], cached['duration_ms'])).fetchone()
            if not human:
                return False
    return own

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
