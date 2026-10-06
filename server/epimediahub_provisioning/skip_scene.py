"""EpiScene controller: Pi metadata/cache, Hetzner pixels and comparisons.

All provider reads run outside SQLite transactions. Successful 60-second
chunks survive a cancelled job; reviewed markers and measured runtimes are
checked again in the publication transaction. Existing decisions are retained.
"""
from __future__ import annotations

import hashlib
import json
import time

from skip_visual import POLICY, VisualWindow, validate_result

CACHE_SECONDS = 3600
CACHE_ROWS = 512
STEP_MS = 500
CHUNK_MS = 60_000
JOB_SECONDS = 180
FIRST_SEARCH_MS = 180_000


def migrate(con):
    con.executescript('''
      CREATE TABLE IF NOT EXISTS skip_scene_windows(
        id INTEGER PRIMARY KEY,asset_key TEXT NOT NULL REFERENCES skip_assets(asset_key) ON DELETE CASCADE,
        kind TEXT NOT NULL,offset_ms INTEGER NOT NULL,length_ms INTEGER NOT NULL,step_ms INTEGER NOT NULL,
        duration_ms INTEGER NOT NULL,policy TEXT NOT NULL,frames_json TEXT NOT NULL,created_at INTEGER NOT NULL,
        UNIQUE(asset_key,kind,offset_ms,length_ms,step_ms,duration_ms,policy));
      CREATE INDEX IF NOT EXISTS skip_scene_recent ON skip_scene_windows(created_at DESC,id DESC);
      CREATE INDEX IF NOT EXISTS skip_scene_asset ON skip_scene_windows(asset_key,kind,step_ms,length_ms DESC);
      CREATE TABLE IF NOT EXISTS skip_scene_state(
        asset_key TEXT NOT NULL REFERENCES skip_assets(asset_key) ON DELETE CASCADE,
        kind TEXT NOT NULL,detail TEXT NOT NULL,updated_at INTEGER NOT NULL,
        PRIMARY KEY(asset_key,kind));
    ''')


def enabled(con):
    row = con.execute("SELECT value FROM skip_auto_metadata_config WHERE name='episcene_enabled'").fetchone()
    return bool(row and row[0] == '1')


def _cache(con, asset, kind, offset, length):
    return con.execute('''SELECT * FROM skip_scene_windows WHERE asset_key=? AND kind=?
      AND offset_ms=? AND length_ms=? AND step_ms=? AND duration_ms=? AND policy=? AND created_at>=?''',
      (asset['asset_key'], kind, offset, length, STEP_MS, asset['duration_ms'], POLICY,
       int(time.time()) - CACHE_SECONDS)).fetchone()


def _window(row, asset, markers=()):
    bounds = [[m['start_ms'], m['end_ms']] for m in markers
              if row['offset_ms'] <= m['start_ms'] < m['end_ms'] <= row['offset_ms'] + row['length_ms']]
    return VisualWindow(json.loads(row['frames_json']), row['offset_ms'], row['step_ms'],
                        row['length_ms'], row['duration_ms'], asset['asset_key'], asset['episode'], bounds)


def _save(con, asset, kind, offset, length, frames):
    # Validate even mocked or future extraction results before persisting them.
    VisualWindow(frames, offset, STEP_MS, length, asset['duration_ms'], asset['asset_key'], asset['episode'])
    text = json.dumps(frames, separators=(',', ':'))
    con.execute('''INSERT INTO skip_scene_windows(asset_key,kind,offset_ms,length_ms,step_ms,duration_ms,
      policy,frames_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)
      ON CONFLICT(asset_key,kind,offset_ms,length_ms,step_ms,duration_ms,policy)
      DO UPDATE SET frames_json=excluded.frames_json,created_at=excluded.created_at''',
      (asset['asset_key'], kind, offset, length, STEP_MS, asset['duration_ms'], POLICY, text, int(time.time())))
    con.execute('''DELETE FROM skip_scene_windows WHERE id NOT IN
      (SELECT id FROM skip_scene_windows ORDER BY created_at DESC,id DESC LIMIT ?)''', (CACHE_ROWS,))
    return _cache(con, asset, kind, offset, length)


def _state(db, asset, kind, detail):
    with db() as con:
        con.execute('''INSERT INTO skip_scene_state VALUES(?,?,?,?) ON CONFLICT(asset_key,kind)
          DO UPDATE SET detail=excluded.detail,updated_at=excluded.updated_at''',
          (asset['asset_key'], kind, detail, int(time.time())))


def capture(db, asset, kind, start, end, busy, *, verified=False):
    from skip_analysis import probe, provider_proxy, source_url
    from skip_remote_client import visual_fingerprint
    start = max(0, int(start) // STEP_MS * STEP_MS)
    end = min(asset['duration_ms'], ((int(end) + STEP_MS - 1) // STEP_MS) * STEP_MS)
    length = end - start
    if not 15000 <= length <= 720000:
        raise ValueError('visual_window')
    with db() as con:
        cached = _cache(con, asset, kind, start, length)
    if cached:
        return cached
    frames, cursor = [], start
    measured = verified
    while cursor < end:
        if busy():
            raise ValueError('analysis_deferred')
        part = min(CHUNK_MS, end - cursor)
        if 0 < end - cursor - part < 5000:
            part -= 5000
        with db() as con:
            row = _cache(con, asset, kind, cursor, part)
            playlist = con.execute('SELECT * FROM customer_playlists WHERE id=?', (asset['playlist_id'],)).fetchone()
        if row:
            chunk = _window(row, asset).frames
        else:
            from skip_analysis_worker import busy_check
            provider_busy = busy_check(db, [playlist])
            def protected_read():
                return busy() or provider_busy()
            if protected_read():
                raise ValueError('analysis_deferred')
            with provider_proxy(source_url(playlist, asset), protected_read) as source:
                if not measured:
                    duration, _ = probe(source, protected_read)
                    if abs(duration - asset['duration_ms']) > 500:
                        raise ValueError('visual_runtime_changed')
                    measured = True
                chunk = visual_fingerprint(source, cursor, part, STEP_MS, protected_read)
            with db() as con:
                _save(con, asset, kind, cursor, part, chunk)
        frames.extend(chunk)
        cursor += part
    with db() as con:
        return _save(con, asset, kind, start, length, frames)


def _human_markers(con, asset, kind):
    return [dict(r) for r in con.execute('''SELECT r.id,r.asset_key,r.start_ms,r.end_ms,r.reviewed_at
      FROM skip_records r LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
      WHERE r.asset_key=? AND r.source_key=? AND r.season=? AND r.episode=?
      AND r.segment_type=? AND r.status='approved' AND r.disabled=0
      AND ABS(r.duration_ms-?)<=500 AND (r.source='device' OR COALESCE(e.human_review,0)=1)
      ORDER BY r.reviewed_at DESC,r.id DESC LIMIT 3''',
      (asset['asset_key'], asset['source_key'], asset['season'], asset['episode'], kind, asset['duration_ms']))]


def _cached_rows(con, asset, kind):
    rows = con.execute('''SELECT w.*,a.episode,a.source_key,a.season,a.playlist_id,
      a.duration_ms current_duration FROM skip_scene_windows w JOIN skip_assets a ON a.asset_key=w.asset_key
      JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
      JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
      JOIN customer_playlists p ON p.id=a.playlist_id JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      WHERE a.source_key=? AND a.season=? AND a.media_type='episode' AND w.kind=? AND w.policy=?
      AND w.step_ms=? AND w.duration_ms=a.duration_ms AND w.created_at>=?
      AND NOT EXISTS (SELECT 1 FROM skip_auto_blocks b WHERE b.asset_key=a.asset_key AND b.kind=w.kind
        AND ABS(b.duration_ms-a.duration_ms)<=2000)
      ORDER BY ABS(a.episode-?),w.length_ms DESC,w.created_at DESC,w.id DESC LIMIT 64''',
      (asset['source_key'], asset['season'], kind, POLICY, STEP_MS, int(time.time()) - CACHE_SECONDS, asset['episode'])).fetchall()
    chosen, episodes = [], set()
    for row in rows:
        if row['episode'] not in episodes:
            chosen.append(row); episodes.add(row['episode'])
    return chosen[:8]


def _snapshot(row, asset):
    return dict(id=row['id'], asset_key=asset['asset_key'], episode=asset['episode'],
                offset_ms=row['offset_ms'], length_ms=row['length_ms'], step_ms=row['step_ms'],
                duration_ms=row['duration_ms'], policy=row['policy'],
                frames_sha256=hashlib.sha256(row['frames_json'].encode()).hexdigest())


def _audio_candidates(con, asset, kind):
    from skip_automation import pending_proposals
    from skip_release import current_reference, reviewed_release_ready, detector_release_ready
    good, candidates, seen = [], [], set()
    for row in pending_proposals(con, asset, kind):
        try:
            evidence = json.loads(row['evidence_json'] or '{}')
        except (ValueError, TypeError):
            continue
        if not isinstance(evidence, dict):
            continue
        if row['source'] == 'episcene':
            # Preserve a strong audio disagreement across later cache/partner
            # updates, even when consolidation replaced its original DB row.
            embedded = evidence.get('audio', [])
            if isinstance(embedded, list):
                candidates.extend(item['record'] for item in embedded[:8]
                                  if isinstance(item,dict) and isinstance(item.get('record'),dict))
        else:
            candidates.append(dict(row))
    for row in candidates:
        if (row.get('source') not in ('audio','audio_repetition','auto_audio')
                or any(row.get(k) != asset[k] for k in ('asset_key','source_key','season','episode','duration_ms'))
                or row.get('segment_type') != kind or type(row.get('confidence')) not in (float,int)):
            continue
        try:
            evidence=json.loads(row['evidence_json'] or '{}')
        except (KeyError,ValueError,TypeError):
            continue
        if not isinstance(evidence,dict):
            continue
        vote = evidence.get('vote', {})
        strong = (evidence.get('method') == 'reviewed_audio_match' and isinstance(vote, dict)
                  and vote.get('boundaries_confirmed') is True and vote.get('confidence', 0) >= .92)
        strong |= evidence.get('method') == 'episode_consensus_v3' and evidence.get('status') == 'AUTO_CONFIRMED'
        identity=(row['id'],row['start_ms'],row['end_ms'],row['evidence_json'])
        if (strong and row['confidence'] >= .92 and identity not in seen
                and current_reference(con,row) and reviewed_release_ready(row) and detector_release_ready(con,row)):
            seen.add(identity)
            good.append(dict(id=row['id'], start_ms=row['start_ms'], end_ms=row['end_ms'],
                             record=dict(row)))
    return good


def _hint(con, asset, kind):
    return con.execute('''SELECT r.start_ms,r.end_ms,r.duration_ms FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
      LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
      WHERE r.source_key=? AND r.season=? AND r.segment_type=? AND r.disabled=0
      AND a.source_key=r.source_key AND a.season=r.season AND a.episode=r.episode
      AND ABS(a.duration_ms-r.duration_ms)<=500 AND r.asset_key<>?
      AND ((r.status='approved' AND (r.source IN ('device','episcene') OR COALESCE(e.human_review,0)=1))
        OR (r.status='pending' AND r.source='episcene' AND r.confidence>=.955 AND json_valid(e.evidence_json)
          AND json_extract(e.evidence_json,'$.decision.ambiguous')=0
          AND json_extract(e.evidence_json,'$.decision.boundaries_confirmed')=1))
      ORDER BY ABS(r.episode-?),r.reviewed_at DESC LIMIT 1''',
      (asset['source_key'], asset['season'], kind, asset['asset_key'], asset['episode'])).fetchone()


def _compare(db, asset, kind, own, selected, busy):
    from skip_remote_client import visual_detect
    with db() as con:
        windows, markers, snapshots = [_window(own, asset)], [], [_snapshot(own, asset)]
        used = {asset['episode']}
        for row, partner in selected:
            if partner['episode'] in used or partner['asset_key'] == asset['asset_key']:
                continue
            trusted = _human_markers(con, partner, kind)
            window = _window(row, partner, trusted)
            windows.append(window)
            markers.extend(m for m in trusted if [m['start_ms'], m['end_ms']] in window.trusted_ranges)
            snapshots.append(_snapshot(row, partner)); used.add(partner['episode'])
            if len(windows) == 5:
                break
    if len(windows) < 2:
        return None
    decision = visual_detect(windows[0], windows[1:], kind, busy)
    if decision['status'] == 'NO_MATCH':
        return None
    with db() as con:
        audio = _audio_candidates(con, asset, kind)
    disagreement = any(abs(c['start_ms'] - decision['start_ms']) > 2000
                       or abs(c['end_ms'] - decision['end_ms']) > 2000 for c in audio)
    if disagreement:
        decision = dict(decision, status='REVIEW')
    evidence = dict(policy=POLICY, method='episcene_consensus', episcene_required=True,
                    decision=decision, windows=snapshots, trusted_markers=markers,
                    audio=audio, audio_visual_disagreement=disagreement,
                    precision='500ms_grid_conservative_end')
    from skip_automation import store_proposal
    from skip_release import accept_pending
    with db() as con:
        saved = store_proposal(con, asset, kind, decision['start_ms'], decision['end_ms'],
                               'episcene', decision['confidence'], evidence)
        accepted = accept_pending(con, asset_key=asset['asset_key']) if saved else 0
    return dict(proposals=int(bool(saved)), approvals=accepted, decision=decision, disagreement=disagreement)


def analyze(db, asset, kind, references, busy):
    with db() as con:
        if not enabled(con):
            return 0, 0
        audio = _audio_candidates(con, asset, kind)
        hint = _hint(con, asset, kind)
        manual = []
        for record in references:
            parent = con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (record['asset_key'],)).fetchone()
            if parent and _human_markers(con, parent, kind):
                manual.append(dict(parent))
    deadline = time.monotonic() + JOB_SECONDS
    def check():
        if busy():
            return True
        if time.monotonic() >= deadline:
            from skip_remote_client import RemoteDeferred
            raise RemoteDeferred('EpiScene setzt die begrenzte Bildsuche aus gespeicherten Abschnitten fort')
        return False
    if audio:
        begin, end = audio[0]['start_ms'] - 6000, audio[0]['end_ms'] + 6000
    elif hint:
        shift = asset['duration_ms'] - hint['duration_ms'] if kind == 'outro' else 0
        begin, end = hint['start_ms'] + shift - 45000, hint['end_ms'] + shift + 45000
    else:
        begin = 0 if kind == 'intro' else max(0, asset['duration_ms'] - FIRST_SEARCH_MS)
        end = min(asset['duration_ms'], begin + FIRST_SEARCH_MS)
    if kind == 'intro':
        begin, end = max(0, begin), min(asset['duration_ms'], end, 720000)
    else:
        begin, end = max(asset['duration_ms'] - 720000, begin, 0), min(asset['duration_ms'], end)
    _state(db, asset, kind, 'EpiScene: Bildfingerabdrücke auf Hetzner vergleichen')
    try:
        own = capture(db, asset, kind, begin, end, check, verified=True)
        selected = []
        for parent in manual[:2]:
            with db() as con:
                marker = _human_markers(con, parent, kind)[0]
            row = capture(db, parent, kind, marker['start_ms'] - 6000, marker['end_ms'] + 6000, check)
            selected.append((row, parent))
        with db() as con:
            for row in _cached_rows(con, asset, kind):
                parent = con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (row['asset_key'],)).fetchone()
                selected.append((row, dict(parent)))
        outcome = _compare(db, asset, kind, own, selected, check)
        # Do not read twelve minutes of every seed before trying a comparison.
        # Begin with three minutes, then expand only if an independent partner
        # exists and no useful sequence was found. A short cached partner can
        # be expanded alongside the target to find a late cold-open intro.
        if outcome is None and any(p['episode']!=asset['episode'] for _,p in selected):
            for limit in (360000,540000,720000):
                first = 0 if kind=='intro' else max(0,asset['duration_ms']-limit)
                last = min(asset['duration_ms'],limit) if kind=='intro' else asset['duration_ms']
                if first==begin and last==end:
                    continue
                own = capture(db,asset,kind,first,last,check,verified=True)
                for i,(cached,parent) in enumerate(selected):
                    if parent['episode']==asset['episode']:
                        continue
                    with db() as con:
                        human = _human_markers(con,parent,kind)
                    if human:
                        continue  # Reviewed reference already supplies exact bounds.
                    partner_start = 0 if kind=='intro' else max(0,parent['duration_ms']-limit)
                    partner_end = min(parent['duration_ms'],limit) if kind=='intro' else parent['duration_ms']
                    if cached['length_ms'] < partner_end-partner_start:
                        cached=capture(db,parent,kind,partner_start,partner_end,check)
                        selected[i]=(cached,parent)
                    break  # At most one additional provider file per expansion.
                outcome = _compare(db,asset,kind,own,selected,check)
                if outcome is not None:
                    break
        detail = ('EpiScene: Bild und Ton widersprechen sich; Zeitgrenzen prüfen' if outcome and outcome['disagreement']
                  else 'EpiScene: Weitere unabhängige Folgen oder eindeutigere Grenzen benötigt' if outcome and outcome['decision']['status'] == 'REVIEW'
                  else 'EpiScene: Bildvergleich abgeschlossen' if outcome else 'EpiScene: Bilder für weitere Staffelvergleiche gespeichert')
        _state(db, asset, kind, detail)
        if time.monotonic() < deadline:
            refresh_neighbours(db, asset, kind, check)
        return (outcome['proposals'], outcome['approvals']) if outcome else (0, 0)
    except ValueError as error:
        if str(error) == 'analysis_deferred':
            raise
        _state(db, asset, kind, 'EpiScene: Bildprüfung unvollständig; vorhandene Vorschläge bleiben zur Prüfung erhalten')
        return 0, 0


def refresh_neighbours(db, asset, kind, busy):
    from skip_automation import protected
    with db() as con:
        rows = _cached_rows(con, asset, kind)
        parents = {r['asset_key']: dict(con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (r['asset_key'],)).fetchone()) for r in rows}
    for own in rows[:5]:
        parent = parents[own['asset_key']]
        if parent['asset_key'] == asset['asset_key']:
            continue
        if busy():
            raise ValueError('analysis_deferred')
        with db() as con:
            if protected(con, parent, kind):
                continue
        # No provider access here: a new independent episode can complete an
        # earlier consensus using only the existing small visual fingerprints.
        outcome = _compare(db, parent, kind, own,
                           [(r, parents[r['asset_key']]) for r in rows], busy)
        if outcome and outcome['approvals']:
            from skip_markers import now
            with db() as con:
                con.execute('''UPDATE skip_jobs SET status='done',detail=?,updated_at=?
                  WHERE asset_key=? AND status IN ('no_reference','no_match','review')''',
                  ('EpiScene: Abschnitt aus unabhängigen Bildsequenzen freigegeben', now(), parent['asset_key']))


def release_ready(con, row, evidence):
    if not isinstance(evidence, dict):
        return False
    if evidence.get('method') != 'episcene_consensus':
        return row['source'] != 'episcene' and evidence.get('episcene_required') is not True
    decision = evidence.get('decision')
    items, markers = evidence.get('windows'), evidence.get('trusted_markers')
    if (evidence.get('policy') != POLICY or evidence.get('audio_visual_disagreement') is not False
            or not isinstance(items, list) or not 2 <= len(items) <= 5
            or not isinstance(markers, list) or len(markers) > 12
            or any(not isinstance(m,dict) for m in markers)):
        return False
    windows, episodes, identities = [], set(), set()
    for item in items:
        if not isinstance(item, dict):
            return False
        cached = con.execute('''SELECT w.*,a.source_key,a.season,a.episode,a.duration_ms current_duration
          FROM skip_scene_windows w JOIN skip_assets a ON a.asset_key=w.asset_key
          JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
          JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
          JOIN customer_playlists p ON p.id=a.playlist_id JOIN customers c ON c.id=p.customer_id AND c.enabled=1
          WHERE w.id=? AND NOT EXISTS (SELECT 1 FROM skip_auto_blocks b WHERE b.asset_key=w.asset_key
            AND b.kind=w.kind AND ABS(b.duration_ms-a.duration_ms)<=2000)''', (item.get('id'),)).fetchone()
        if (not cached or cached['source_key'] != row['source_key'] or cached['season'] != row['season']
                or cached['kind'] != row['segment_type'] or cached['duration_ms'] != cached['current_duration']
                or cached['policy'] != POLICY or cached['step_ms'] != STEP_MS
                or cached['episode'] in episodes or cached['asset_key'] in identities
                or cached['created_at'] < int(time.time()) - CACHE_SECONDS
                or any(cached[k] != item.get(k) for k in ('asset_key','episode','offset_ms','length_ms','step_ms','duration_ms','policy'))
                or hashlib.sha256(cached['frames_json'].encode()).hexdigest() != item.get('frames_sha256')):
            return False
        parent = dict(asset_key=cached['asset_key'], episode=cached['episode'])
        own_markers = [m for m in markers if isinstance(m, dict) and m.get('asset_key') == cached['asset_key']]
        for marker in own_markers:
            if not con.execute('''SELECT 1 FROM skip_records r LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
              WHERE r.id=? AND r.asset_key=? AND r.source_key=? AND r.season=? AND r.episode=?
              AND r.segment_type=? AND r.status='approved' AND r.disabled=0 AND r.start_ms=? AND r.end_ms=?
              AND r.reviewed_at IS ? AND ABS(r.duration_ms-?)<=500
              AND (r.source='device' OR COALESCE(e.human_review,0)=1)''',
              (marker.get('id'), cached['asset_key'], row['source_key'], row['season'], cached['episode'],
               row['segment_type'], marker.get('start_ms'), marker.get('end_ms'), marker.get('reviewed_at'), cached['duration_ms'])).fetchone():
                return False
        try:
            windows.append(_window(cached, parent, own_markers))
        except (ValueError, TypeError, KeyError):
            return False
        episodes.add(cached['episode']); identities.add(cached['asset_key'])
    if (windows[0].episode_id != row['asset_key'] or windows[0].episode != row['episode']
            or windows[0].duration_ms != row['duration_ms']):
        return False
    if any(m.get('asset_key') not in identities for m in markers):
        return False
    audio_items = evidence.get('audio', [])
    if not isinstance(audio_items, list) or len(audio_items) > 8:
        return False
    for item in audio_items:
        if not isinstance(item, dict) or not isinstance(item.get('record'), dict):
            return False
        audio = item['record']
        if (any(audio.get(k) != row[k] for k in ('asset_key','source_key','season','episode','segment_type','duration_ms'))
                or audio.get('start_ms') != item.get('start_ms') or audio.get('end_ms') != item.get('end_ms')
                or not isinstance(audio.get('evidence_json'), str)):
            return False
        from skip_release import current_reference, detector_release_ready, reviewed_release_ready
        if not (current_reference(con, audio) and detector_release_ready(con, audio) and reviewed_release_ready(audio)):
            return False
    try:
        validate_result(decision, windows[0], windows[1:], row['segment_type'])
    except (ValueError, TypeError, KeyError):
        return False
    return bool(decision['status'] == 'AUTO_CONFIRMED' and decision['start_ms'] == row['start_ms']
                and decision['end_ms'] == row['end_ms'] and row['confidence'] >= .955)


def learn_reference(db, asset, kind, busy):
    with db() as con:
        if not enabled(con):
            return False
        markers = _human_markers(con, asset, kind)
    if markers:
        capture(db, asset, kind, markers[0]['start_ms'] - 6000, markers[0]['end_ms'] + 6000, busy)
        with db() as con:
            current = _human_markers(con,asset,kind)
        if markers[0] not in current:
            from skip_remote_client import RemoteDeferred
            raise RemoteDeferred('EpiScene: Referenz wurde geändert; aktuelle Bildgrenzen werden erneut gelernt')
        return True
    return False


def has_completed_visual(con, asset_key):
    return bool(con.execute('''SELECT 1 FROM skip_scene_state WHERE asset_key=? AND detail IN
      ('EpiScene: Bildvergleich abgeschlossen','EpiScene: Bilder für weitere Staffelvergleiche gespeichert',
       'EpiScene: Weitere unabhängige Folgen oder eindeutigere Grenzen benötigt',
       'EpiScene: Bild und Ton widersprechen sich; Zeitgrenzen prüfen') LIMIT 1''',(asset_key,)).fetchone())
