"""Language stages and interactive series priority for one sequential worker."""
from __future__ import annotations

import re
import time

from skip_markers import now


def migrate(con):
    con.executescript("""
      CREATE TABLE IF NOT EXISTS skip_schedule_order(
        playlist_id INTEGER PRIMARY KEY REFERENCES customer_playlists(id) ON DELETE CASCADE,
        position INTEGER NOT NULL CHECK(position BETWEEN 0 AND 999));
      CREATE TABLE IF NOT EXISTS skip_schedule_focus(
        id INTEGER PRIMARY KEY CHECK(id=1),
        playlist_id INTEGER NOT NULL REFERENCES customer_playlists(id) ON DELETE CASCADE,
        source_key TEXT NOT NULL,updated_at TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS idx_skip_schedule_assets
        ON skip_assets(playlist_id,source_key,media_type,season,episode);
      CREATE TABLE IF NOT EXISTS skip_schedule_requests(
        playlist_id INTEGER NOT NULL REFERENCES customer_playlists(id) ON DELETE CASCADE,
        source_key TEXT NOT NULL,season INTEGER NOT NULL,episode INTEGER NOT NULL,
        reference_asset TEXT NOT NULL DEFAULT '',reason TEXT NOT NULL,
        requested_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,
        PRIMARY KEY(playlist_id,source_key));
    """)


def default_priority(name):
    tokens = set(re.findall(r'[a-z0-9]+', str(name).casefold()))
    if '4k' in tokens:
        return 0
    if {'the', 'best'} <= tokens:
        return 1
    if 'fe' in tokens and tokens & {'iptv', 'tv'}:
        return 2
    return 3


def playlists(con):
    rows = con.execute("""SELECT p.id,p.name,o.position FROM customer_playlists p
      JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      JOIN skip_analysis_sources s ON s.playlist_id=p.id AND s.enabled=1
      LEFT JOIN skip_schedule_order o ON o.playlist_id=p.id""").fetchall()
    return sorted((dict(row) for row in rows), key=lambda r: (
        r['position'] if r['position'] is not None else 1000 + default_priority(r['name']), r['id']))


def save_order(con, identifiers):
    expected = {row['id'] for row in playlists(con)}
    if len(identifiers) != len(expected) or set(identifiers) != expected:
        raise ValueError('invalid_playlist_order')
    con.execute('DELETE FROM skip_schedule_order')
    con.executemany('INSERT INTO skip_schedule_order VALUES(?,?)',
                    ((identifier, position) for position, identifier in enumerate(identifiers)))
    # Apply an explicit change at the next job; never interrupt an active decoder.
    con.execute('DELETE FROM skip_schedule_focus')


def inventory_pending(con, playlist_id, timestamp=None):
    timestamp = int(time.time()) if timestamp is None else timestamp
    row = con.execute("""SELECT r.full_done,r.phase,r.next_due,COALESCE(f.checked_at,1) language_checked
      FROM skip_catalogue_settings x
      JOIN skip_auto_settings a ON a.playlist_id=x.playlist_id AND a.enabled=1
      LEFT JOIN skip_catalogue_runs r ON r.playlist_id=x.playlist_id
      LEFT JOIN skip_catalogue_language_refresh f ON f.playlist_id=x.playlist_id
      WHERE x.playlist_id=? AND x.enabled=1""", (playlist_id,)).fetchone()
    return bool(row and (row['full_done'] is None or not row['full_done']
                         or row['phase'] != 'idle' or row['next_due'] <= timestamp
                         or row['language_checked'] == 0))


def legacy_discovery_pending(con, playlist_id):
    return bool(con.execute("""SELECT 1 FROM skip_assets a
      JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
      LEFT JOIN skip_auto_assets d ON d.asset_key=a.asset_key
      LEFT JOIN skip_auto_series z ON z.source_key=a.source_key
        AND z.playlist_id=a.playlist_id AND z.season=a.season
      WHERE a.playlist_id=? AND a.media_type='episode' AND d.asset_key IS NULL
        AND NOT EXISTS(SELECT 1 FROM skip_catalogue_settings cs
          WHERE cs.playlist_id=a.playlist_id AND cs.enabled=1)
        AND COALESCE(z.checked_at,0)<? LIMIT 1""", (playlist_id, int(time.time()) - 86400)).fetchone())


ACTIVE_JOBS = """ FROM skip_jobs j JOIN skip_assets a USING(asset_key)
  JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
  JOIN customer_playlists p ON p.id=a.playlist_id
  JOIN customers c ON c.id=p.customer_id AND c.enabled=1
  LEFT JOIN skip_language_priority l USING(asset_key) """


def language_stage(con):
    """Global DE/IT, then Turkish, then remaining/unknown audio languages."""
    # The first available rank is enough. MIN used to join every queued asset,
    # even when the first row already proved that DE/IT is active.
    known_jobs = ACTIVE_JOBS.replace('LEFT JOIN skip_language_priority l USING(asset_key)',
                                     'JOIN skip_language_priority l USING(asset_key)')
    job_rank = next((rank for rank in (0,1) if con.execute('SELECT 1' + known_jobs +
        " WHERE ((j.status='queued' AND j.attempts<3) OR j.status='running')"
        " AND l.priority=? LIMIT 1", (rank,)).fetchone()), None)
    if job_rank == 0:
        return 0
    if job_rank is None and con.execute('SELECT 1' + ACTIVE_JOBS.replace(
            'LEFT JOIN skip_language_priority l USING(asset_key)','') +
            " WHERE (j.status='queued' AND j.attempts<3) OR j.status='running' LIMIT 1").fetchone():
        job_rank = 2
    ranks = [job_rank]
    ranks.append(con.execute("""SELECT MIN(COALESCE(l.priority,2)) FROM skip_app_tasks t
      JOIN skip_assets a USING(asset_key)
      JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
      JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
      JOIN customer_playlists p ON p.id=a.playlist_id
      JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      LEFT JOIN skip_language_priority l USING(asset_key) WHERE t.attempts<3""").fetchone()[0])
    if ranks[-1] == 0:
        return 0
    ranks.append(con.execute("""SELECT MIN(CASE WHEN (r.phase='idle' AND r.full_done=0) OR COALESCE(f.checked_at,1)=0
        THEN 0 ELSE COALESCE(l.priority,2) END) FROM skip_catalogue_runs r
      JOIN skip_catalogue_settings x ON x.playlist_id=r.playlist_id AND x.enabled=1
      JOIN skip_auto_settings u ON u.playlist_id=r.playlist_id AND u.enabled=1
      JOIN skip_analysis_sources s ON s.playlist_id=r.playlist_id AND s.enabled=1
      JOIN customer_playlists p ON p.id=r.playlist_id
      JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      LEFT JOIN skip_catalogue_language_refresh f ON f.playlist_id=r.playlist_id
      LEFT JOIN skip_catalogue_series z ON z.playlist_id=r.playlist_id AND z.pending_generation=r.generation AND z.pending_generation>0
      LEFT JOIN skip_catalogue_languages l ON l.playlist_id=z.playlist_id AND l.series_id=z.series_id
      WHERE r.retry_at<=? AND ((r.phase='idle' AND r.next_due<=?)
        OR z.series_id IS NOT NULL OR (f.checked_at=0 AND f.retry_at<=?))""",
      (int(time.time()),)*3).fetchone()[0])
    return min((rank for rank in ranks if rank is not None), default=2)


def request_series(con, asset_key, reason='playback'):
    """Events use registered files only; language priority always wins."""
    from skip_catalogue import language_priority, set_asset_language
    asset = con.execute("SELECT * FROM skip_assets WHERE asset_key=? AND media_type='episode'", (asset_key,)).fetchone()
    if not asset:
        return
    if not con.execute('SELECT 1 FROM skip_language_priority WHERE asset_key=?', (asset_key,)).fetchone():
        set_asset_language(con, asset_key, language_priority({'name': asset['title']}))
    stamp = int(time.time())
    con.execute('DELETE FROM skip_schedule_requests WHERE expires_at<=?', (stamp,))
    # Repeated lookups retain a reference request and its anchor.
    con.execute("""INSERT INTO skip_schedule_requests VALUES(?,?,?,?,?,?,?,?)
      ON CONFLICT(playlist_id,source_key) DO UPDATE SET
        season=CASE WHEN excluded.reason='reference' OR skip_schedule_requests.reason<>'reference' THEN excluded.season ELSE skip_schedule_requests.season END,
        episode=CASE WHEN excluded.reason='reference' OR skip_schedule_requests.reason<>'reference' THEN excluded.episode ELSE skip_schedule_requests.episode END,
        reference_asset=CASE WHEN excluded.reason='reference' THEN excluded.reference_asset ELSE skip_schedule_requests.reference_asset END,
        reason=CASE WHEN excluded.reason='reference' THEN 'reference' ELSE skip_schedule_requests.reason END,
        expires_at=MAX(skip_schedule_requests.expires_at,excluded.expires_at)""",
        (asset['playlist_id'], asset['source_key'], asset['season'], asset['episode'],
         asset_key if reason=='reference' else '', reason, stamp, stamp+7*86400))
    if reason == 'reference':
        needs_learning = con.execute("""SELECT 1 FROM skip_records r
          LEFT JOIN skip_fingerprints f ON f.record_id=r.id
          LEFT JOIN skip_auto_reference_checks k ON k.record_id=r.id
          WHERE r.asset_key=? AND r.source_key=? AND r.season=? AND r.episode=?
            AND r.media_type='episode' AND r.segment_type='intro' AND r.status='approved'
            AND r.disabled=0 AND ABS(r.duration_ms-?)<=2000 AND r.end_ms-r.start_ms BETWEEN 19000 AND 300000
            AND (f.record_id IS NULL OR f.length_ms<>r.end_ms-r.start_ms OR f.offset_ms<>2000
              OR f.created_at<r.reviewed_at OR k.fingerprint_created_at IS NOT f.created_at
              OR k.checked_at<?) LIMIT 1""", (asset_key,asset['source_key'],asset['season'],asset['episode'],asset['duration_ms'],stamp-3600)).fetchone()
        if needs_learning:
            con.execute("""UPDATE skip_jobs SET status='queued',attempts=0,detail='',updated_at=?
              WHERE asset_key=? AND status NOT IN ('queued','running')""", (now(), asset_key))


def requests(con, stage):
    return con.execute("""SELECT q.*,CASE WHEN q.reason='reference' THEN CASE WHEN EXISTS(
        SELECT 1 FROM skip_jobs r WHERE r.asset_key=q.reference_asset AND r.status IN ('queued','running'))
        THEN 3 ELSE 2 END ELSE 1 END priority FROM skip_schedule_requests q
      JOIN skip_analysis_sources s ON s.playlist_id=q.playlist_id AND s.enabled=1
      JOIN customer_playlists p ON p.id=q.playlist_id
      JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      WHERE q.expires_at>? AND EXISTS(SELECT 1 FROM skip_jobs j
        JOIN skip_assets a USING(asset_key) LEFT JOIN skip_language_priority l USING(asset_key)
        WHERE a.playlist_id=q.playlist_id AND a.source_key=q.source_key
          AND j.status='queued' AND j.attempts<3 AND COALESCE(l.priority,2)=?)
      ORDER BY priority DESC,EXISTS(SELECT 1 FROM skip_schedule_focus f WHERE f.id=1
        AND f.playlist_id=q.playlist_id AND f.source_key=q.source_key) DESC,
        q.requested_at,q.playlist_id,q.source_key""",
      (int(time.time()), stage)).fetchall()


def should_pause(con, asset_key):
    asset = con.execute("""SELECT a.*,COALESCE(l.priority,2) language,
      CASE WHEN q.source_key IS NULL OR q.expires_at<=? THEN 0
        WHEN q.reason='reference' THEN CASE WHEN q.reference_asset=a.asset_key THEN 3 ELSE 2 END
        ELSE 1 END priority
      FROM skip_assets a
      JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
      JOIN customer_playlists p ON p.id=a.playlist_id
      JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      LEFT JOIN skip_language_priority l USING(asset_key)
      LEFT JOIN skip_schedule_requests q ON q.playlist_id=a.playlist_id AND q.source_key=a.source_key
      WHERE a.asset_key=?""", (int(time.time()),asset_key)).fetchone()
    stage = language_stage(con)
    if asset is None or asset['language']>stage:
        return True
    preferred = requests(con,stage)
    return bool(preferred and preferred[0]['priority']>asset['priority'])


def blocked_playlists(con):
    from skip_analysis import source_account
    busy_accounts = set()
    for row in con.execute("SELECT DISTINCT p.* FROM skip_presence s JOIN customer_playlists p ON p.id=s.playlist_id WHERE s.expires_at>?", (int(time.time()),)):
        try:
            busy_accounts.add(source_account(row))
        except ValueError:
            continue
    blocked = set()
    for row in con.execute('SELECT * FROM customer_playlists'):
        try:
            if source_account(row) in busy_accounts:
                blocked.add(row['id'])
        except ValueError:
            continue
    return blocked


def current_playlist(con, excluded=(), *, stage=None):
    rows = playlists(con)
    stage = language_stage(con) if stage is None else stage
    for request in requests(con, stage):
        if request['playlist_id'] not in excluded:
            return request['playlist_id']
    def pending(identifier):
        return bool(identifier not in excluded and ready(con, identifier, stage=stage))
    focus = con.execute('SELECT playlist_id FROM skip_schedule_focus WHERE id=1').fetchone()
    if focus and any(row['id']==focus['playlist_id'] for row in rows) and pending(focus['playlist_id']):
        return focus['playlist_id']
    for row in rows:
        if pending(row['id']):
            return row['id']
    # Inventory before lower language stages, with playlist order as tie-breaker.
    inventory = []
    for position,row in enumerate(rows):
        if row['id'] not in excluded and (inventory_pending(con, row['id']) or legacy_discovery_pending(con, row['id'])):
            rank = con.execute("""SELECT MIN(CASE WHEN (r.phase='idle' AND r.full_done=0) OR COALESCE(f.checked_at,1)=0
              THEN 0 ELSE COALESCE(l.priority,2) END) FROM skip_catalogue_runs r
              LEFT JOIN skip_catalogue_language_refresh f ON f.playlist_id=r.playlist_id
              LEFT JOIN skip_catalogue_series z ON z.playlist_id=r.playlist_id AND z.pending_generation=r.generation AND z.pending_generation>0
              LEFT JOIN skip_catalogue_languages l ON l.playlist_id=z.playlist_id AND l.series_id=z.series_id
              WHERE r.playlist_id=?""", (row['id'],)).fetchone()[0]
            inventory.append((rank if rank is not None else 2, position, row['id']))
    if inventory:
        return min(inventory)[2]
    return None


def ready(con, playlist_id, *, stage=None):
    return bool(con.execute('SELECT 1' + ACTIVE_JOBS +
      " WHERE a.playlist_id=? AND j.status='queued' AND j.attempts<3 AND COALESCE(l.priority,2)=? LIMIT 1",
      (playlist_id, language_stage(con) if stage is None else stage)).fetchone())


def select_job(con, playlist_id, excluded=(), *, stage=None):
    """Keep the chosen series across batches, restarts and playback pauses."""
    if playlist_id is None:
        return None, 'idle'
    stage = language_stage(con) if stage is None else stage
    best = con.execute("""SELECT j.*,a.source_key,a.media_type,
        COALESCE(l.priority,2) language
      FROM skip_jobs j JOIN skip_assets a USING(asset_key)
      LEFT JOIN skip_language_priority l USING(asset_key)
      LEFT JOIN skip_catalogue_priority p USING(asset_key)
      WHERE a.playlist_id=? AND j.status='queued' AND j.attempts<3 AND COALESCE(l.priority,2)=?
      ORDER BY COALESCE(p.priority,1),j.updated_at,j.id LIMIT 1""", (playlist_id,stage)).fetchone()
    if best is None:
        return None, 'preferred_pending'
    focus = con.execute('SELECT * FROM skip_schedule_focus WHERE id=1 AND playlist_id=?',
                        (playlist_id,)).fetchone()
    source_key = best['source_key']
    request = next((r for r in requests(con, stage) if r['playlist_id']==playlist_id), None)
    continuing = focus and con.execute("""SELECT 1 FROM skip_jobs j JOIN skip_assets a USING(asset_key)
      LEFT JOIN skip_language_priority l USING(asset_key)
      WHERE a.playlist_id=? AND a.source_key=? AND a.media_type='episode'
        AND j.status='queued' AND j.attempts<3 AND COALESCE(l.priority,2)=? LIMIT 1""",
                            (playlist_id, focus['source_key'],stage)).fetchone()
    if request:
        source_key = request['source_key']
    elif continuing:
        source_key = focus['source_key']
    params = [playlist_id, source_key, stage, *excluded]
    exclusion = ' AND j.id NOT IN (' + ','.join('?' for _ in excluded) + ')' if excluded else ''
    job = con.execute("""SELECT j.* FROM skip_jobs j JOIN skip_assets a USING(asset_key)
      LEFT JOIN skip_language_priority l USING(asset_key)
      WHERE a.playlist_id=? AND a.source_key=? AND j.status='queued' AND j.attempts<3 AND COALESCE(l.priority,2)=?"""
                      + exclusion + (" ORDER BY a.asset_key<>?,CASE WHEN a.season=? AND a.episode>=? THEN 0 WHEN a.season>? THEN 1 ELSE 2 END,a.season,a.episode,j.id LIMIT 1" if request
                                     else ' ORDER BY a.season,a.episode,j.id LIMIT 1'),
                      params + ([request['reference_asset'],request['season'],request['episode'],request['season']] if request else [])).fetchone()
    return job, 'series_pending' if job is None else ''


def remember(con, job):
    row = con.execute('SELECT playlist_id,source_key FROM skip_assets WHERE asset_key=?',
                      (job['asset_key'],)).fetchone()
    con.execute("""INSERT INTO skip_schedule_focus VALUES(1,?,?,?)
      ON CONFLICT(id) DO UPDATE SET playlist_id=excluded.playlist_id,
        source_key=excluded.source_key,updated_at=excluded.updated_at""",
                (row['playlist_id'], row['source_key'], now()))


def overview(con):
    rows = playlists(con)
    stage = language_stage(con)
    for position, row in enumerate(rows, 1):
        row['position'] = position
    running = con.execute("""SELECT a.* FROM skip_jobs j JOIN skip_assets a USING(asset_key)
      JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
      JOIN customer_playlists p ON p.id=a.playlist_id
      JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      WHERE j.status='running' ORDER BY j.id LIMIT 1""").fetchone()
    playlist_id = running['playlist_id'] if running else current_playlist(con,stage=stage)
    current = None
    if playlist_id is not None:
        current = dict(playlist_id=playlist_id, playlist_name=next(r['name'] for r in rows if r['id']==playlist_id))
        # A running job already identifies the actual series. Do not sort the
        # entire remaining queue merely to render a job that is not next yet.
        job = None if running else select_job(con, playlist_id,stage=stage)[0]
        asset = running or (con.execute('SELECT * FROM skip_assets WHERE asset_key=?',
                                       (job['asset_key'],)).fetchone() if job else None)
        if asset:
            counts = con.execute("""SELECT COUNT(*) files,
              SUM(j.status NOT IN ('queued','running','disabled')) processed,
              SUM(j.status IN ('failed','unmatched','no_reference')) problems,
              SUM(j.status='review') review FROM skip_assets a JOIN skip_jobs j USING(asset_key)
              WHERE a.playlist_id=? AND a.source_key=?""", (playlist_id, asset['source_key'])).fetchone()
            current.update(dict(asset), **dict(counts))
    return dict(playlists=rows,current=current,language_stage=stage)
