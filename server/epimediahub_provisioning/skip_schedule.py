"""Persistent playlist/series order for the single, sequential analysis worker."""
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


def current_playlist(con):
    rows = playlists(con)
    def pending(identifier):
        return bool(con.execute("""SELECT 1 FROM skip_jobs j JOIN skip_assets a USING(asset_key)
              WHERE a.playlist_id=? AND ((j.status='queued' AND j.attempts<3)
                OR j.status='running') LIMIT 1""", (identifier,)).fetchone()
                    or inventory_pending(con, identifier) or legacy_discovery_pending(con, identifier))
    focus = con.execute('SELECT playlist_id FROM skip_schedule_focus WHERE id=1').fetchone()
    if focus and any(row['id']==focus['playlist_id'] for row in rows) and pending(focus['playlist_id']):
        return focus['playlist_id']
    for row in rows:
        if pending(row['id']):
            return row['id']
    return None


def ready(con, playlist_id):
    from skip_catalogue import preferred_inventory_pending
    if con.execute("""SELECT 1 FROM skip_schedule_focus f JOIN skip_assets a
      ON a.playlist_id=f.playlist_id AND a.source_key=f.source_key
      JOIN skip_jobs j USING(asset_key) WHERE f.id=1 AND f.playlist_id=?
        AND j.status='queued' AND j.attempts<3 LIMIT 1""", (playlist_id,)).fetchone():
        return True
    row = con.execute("""SELECT MIN(CASE WHEN a.media_type='episode'
      THEN COALESCE(l.priority,1) ELSE 1 END) FROM skip_jobs j
      JOIN skip_assets a USING(asset_key) LEFT JOIN skip_language_priority l USING(asset_key)
      WHERE a.playlist_id=? AND j.status='queued' AND j.attempts<3""", (playlist_id,)).fetchone()
    return bool(row[0] is not None and (row[0] == 0 or not preferred_inventory_pending(con, playlist_id)))


def select_job(con, playlist_id, excluded=()):
    """Keep the chosen series across batches, restarts and playback pauses."""
    from skip_catalogue import preferred_inventory_pending
    if playlist_id is None:
        return None, 'idle'
    best = con.execute("""SELECT j.*,a.source_key,a.media_type,
        CASE WHEN a.media_type='episode' THEN COALESCE(l.priority,1) ELSE 1 END language
      FROM skip_jobs j JOIN skip_assets a USING(asset_key)
      LEFT JOIN skip_language_priority l USING(asset_key)
      LEFT JOIN skip_catalogue_priority p USING(asset_key)
      WHERE a.playlist_id=? AND j.status='queued' AND j.attempts<3
      ORDER BY language,COALESCE(p.priority,1),j.updated_at,j.id LIMIT 1""", (playlist_id,)).fetchone()
    if best is None:
        return None, 'catalogue_pending' if inventory_pending(con, playlist_id) else 'playlist_pending'
    focus = con.execute('SELECT * FROM skip_schedule_focus WHERE id=1 AND playlist_id=?',
                        (playlist_id,)).fetchone()
    source_key = best['source_key']
    continuing = focus and con.execute("""SELECT 1 FROM skip_jobs j JOIN skip_assets a USING(asset_key)
      WHERE a.playlist_id=? AND a.source_key=? AND a.media_type='episode'
        AND j.status='queued' AND j.attempts<3 LIMIT 1""",
                            (playlist_id, focus['source_key'])).fetchone()
    if continuing:
        source_key = focus['source_key']
    elif best['language'] != 0 and preferred_inventory_pending(con, playlist_id):
        return None, 'preferred_pending'
    params = [playlist_id, source_key, *excluded]
    exclusion = ' AND j.id NOT IN (' + ','.join('?' for _ in excluded) + ')' if excluded else ''
    job = con.execute("""SELECT j.* FROM skip_jobs j JOIN skip_assets a USING(asset_key)
      WHERE a.playlist_id=? AND a.source_key=? AND j.status='queued' AND j.attempts<3"""
                      + exclusion + ' ORDER BY a.season,a.episode,j.id LIMIT 1', params).fetchone()
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
    for position, row in enumerate(rows, 1):
        row['position'] = position
    running = con.execute("""SELECT a.* FROM skip_jobs j JOIN skip_assets a USING(asset_key)
      JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
      JOIN customer_playlists p ON p.id=a.playlist_id
      JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      WHERE j.status='running' ORDER BY j.id LIMIT 1""").fetchone()
    playlist_id = running['playlist_id'] if running else current_playlist(con)
    current = None
    if playlist_id is not None:
        current = dict(playlist_id=playlist_id, playlist_name=next(r['name'] for r in rows if r['id']==playlist_id))
        job, _ = select_job(con, playlist_id)
        asset = running or (con.execute('SELECT * FROM skip_assets WHERE asset_key=?',
                                       (job['asset_key'],)).fetchone() if job else None)
        if asset:
            counts = con.execute("""SELECT COUNT(*) files,
              SUM(j.status NOT IN ('queued','running','disabled')) processed,
              SUM(j.status IN ('failed','unmatched','no_reference')) problems,
              SUM(j.status='review') review FROM skip_assets a JOIN skip_jobs j USING(asset_key)
              WHERE a.playlist_id=? AND a.source_key=?""", (playlist_id, asset['source_key'])).fetchone()
            current.update(dict(asset), **dict(counts))
    return dict(playlists=rows,current=current)
