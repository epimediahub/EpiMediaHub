"""Small, authenticated Chromaprint uploads; never PCM or another provider stream."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import struct
import time

STEP_MS = 1365 * 1000 / 11025
MAX_UPLOAD = 64_000


def migrate(con):
    con.executescript('''
      CREATE TABLE IF NOT EXISTS skip_app_windows(
        asset_key TEXT PRIMARY KEY REFERENCES skip_assets(asset_key) ON DELETE CASCADE,
        words_json TEXT NOT NULL,step_ms REAL NOT NULL,offset_ms INTEGER NOT NULL,
        length_ms INTEGER NOT NULL,duration_ms INTEGER NOT NULL,audio_key TEXT NOT NULL,
        revision TEXT NOT NULL,device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
        received_at INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_app_tasks(
        asset_key TEXT PRIMARY KEY REFERENCES skip_app_windows(asset_key) ON DELETE CASCADE,
        revision TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0);
    ''')


def validate(raw):
    if (not isinstance(raw, dict) or raw.get('algorithm') != 'chromaprint-1'
            or raw.get('media_type') != 'episode' or raw.get('kind') != 'intro'):
        raise ValueError('invalid_fingerprint')
    offset, length = raw.get('offset_ms'), raw.get('length_ms')
    audio_key = raw.get('audio_key')
    if (type(offset) is not int or type(length) is not int
            or not 0 <= offset < 720_000 or not 30_000 <= length <= 720_000
            or offset + length > min(720_000, raw['duration_ms']) + 250
            or not isinstance(audio_key, str) or len(audio_key) != 64
            or any(c not in '0123456789abcdef' for c in audio_key)):
        raise ValueError('invalid_fingerprint')
    encoded = raw.get('fingerprint')
    if not isinstance(encoded, str) or not 100 <= len(encoded) <= 40_000:
        raise ValueError('invalid_fingerprint')
    try:
        packed = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('invalid_fingerprint') from None
    if len(packed) % 4:
        raise ValueError('invalid_fingerprint')
    words = list(struct.unpack('<' + str(len(packed) // 4) + 'I', packed))
    if (not 200 <= len(words) <= 6000 or not length - 8000 <= len(words) * STEP_MS <= length + 250
            or len(set(words)) < 15):
        raise ValueError('invalid_fingerprint')
    revision = hashlib.sha256(packed + str((offset, length, raw['duration_ms'], audio_key)).encode()).hexdigest()
    return words, offset, length, audio_key, revision


def receive(con, device, raw, data):
    from skip_analysis import authorized_playlist, register_asset
    from skip_automation import enabled
    playlist_id = raw.get('playlist_id')
    if type(playlist_id) is not int or authorized_playlist(con, device, playlist_id) is None:
        return 'unavailable'
    if not enabled(con, playlist_id):
        return 'unavailable'
    words, offset, length, audio_key, revision = validate(raw)
    asset = con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (data['asset_key'],)).fetchone()
    if asset:
        # Keep catalogue identity authoritative. A player may use a different
        # spelling of the series title, but it must name this exact file/version.
        if (asset['playlist_id'] != playlist_id
                or any(asset[k] != data[k] for k in ('media_type', 'season', 'episode'))
                or abs(asset['duration_ms'] - data['duration_ms']) > 2000):
            return 'unavailable'
    elif not register_asset(con, raw, data, device):
        return 'unavailable'
    from skip_schedule import request_series
    request_series(con, data['asset_key'])
    previous = con.execute('SELECT * FROM skip_app_windows WHERE asset_key=?', (data['asset_key'],)).fetchone()
    if previous and previous['duration_ms'] == data['duration_ms']:
        if previous['revision'] == revision or previous['length_ms'] > length:
            return 'cached'
    con.execute('INSERT OR REPLACE INTO skip_app_windows VALUES(?,?,?,?,?,?,?,?,?,?)',
                (data['asset_key'], json.dumps(words), STEP_MS, offset, length,
                 data['duration_ms'], audio_key, revision, device['id'], int(time.time())))
    con.execute('INSERT OR REPLACE INTO skip_app_tasks VALUES(?,?,0)', (data['asset_key'], revision))
    con.execute('DELETE FROM skip_app_windows WHERE received_at<?', (int(time.time()) - 7 * 86400,))
    con.execute('''DELETE FROM skip_app_windows WHERE rowid NOT IN
      (SELECT rowid FROM skip_app_windows ORDER BY received_at DESC LIMIT 512)''')
    return 'accepted'


def windows(con, asset, kind):
    if kind != 'intro':
        return []
    return con.execute('''SELECT w.*, 'intro' kind,a.episode,a.source_key,a.season,a.playlist_id,a.duration_ms current_duration,
      w.received_at created_at,'app' origin FROM skip_app_windows w JOIN skip_assets a USING(asset_key)
      JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
      JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
      JOIN customer_playlists p ON p.id=a.playlist_id
      JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      WHERE a.source_key=? AND a.season=? AND a.media_type='episode'
      AND ABS(w.duration_ms-a.duration_ms)<=2000 AND w.received_at>=?
      AND NOT EXISTS (SELECT 1 FROM skip_auto_blocks b WHERE b.asset_key=a.asset_key AND b.kind='intro'
        AND ABS(b.duration_ms-a.duration_ms)<=2000)
      ORDER BY ABS(a.episode-?),w.received_at DESC LIMIT 32''',
      (asset['source_key'], asset['season'], int(time.time()) - 7 * 86400, asset['episode'])).fetchall()


def complete_window(con, asset, kind, offset, length):
    if kind != 'intro':
        return None
    row = con.execute('SELECT * FROM skip_app_windows WHERE asset_key=?', (asset['asset_key'],)).fetchone()
    if (not row or abs(row['duration_ms'] - asset['duration_ms']) > 250
            or abs(row['offset_ms'] - offset) > 20 or abs(row['length_ms'] - length) > 250
            or row['received_at'] < int(time.time()) - 86400):
        return None
    return json.loads(row['words_json']), row['step_ms'], row['offset_ms'], row['length_ms']


def process_one(db, cancelled=lambda: False):
    """Compare uploads even during playback. This never reads from the provider."""
    from skip_automation import bootstrap, detector_windows, enabled
    from skip_release import accept_pending
    from skip_schedule import language_stage, should_pause
    with db() as con:
        row = con.execute('''SELECT t.*,a.playlist_id FROM skip_app_tasks t
          JOIN skip_assets a USING(asset_key)
          JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
          JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
          JOIN customer_playlists p ON p.id=a.playlist_id
          JOIN customers c ON c.id=p.customer_id AND c.enabled=1
          LEFT JOIN skip_language_priority l USING(asset_key)
          WHERE t.attempts<3 AND COALESCE(l.priority,2)=? ORDER BY t.rowid LIMIT 1''',
          (language_stage(con),)).fetchone()
        if not row:
            return False
        asset = con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (row['asset_key'],)).fetchone()
        keys = [asset['asset_key']] + [w['asset_key'] for w in detector_windows(con, asset, 'intro')
                                     if w['asset_key'] != asset['asset_key']][:4]
    cache = [0.0,False]
    def paused():
        if cancelled():
            return True
        if time.monotonic()-cache[0]>=2:
            with db() as con:
                cache[:] = [time.monotonic(),should_pause(con,asset['asset_key'])]
        return cache[1]
    try:
        for key in keys:
            if paused():
                raise ValueError('analysis_deferred')
            with db() as con:
                current = con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (key,)).fetchone()
                if current and enabled(con, current['playlist_id']) and bootstrap(con, current, 'intro', paused):
                    accept_pending(con, asset_key=key)
        with db() as con:
            con.execute('DELETE FROM skip_app_tasks WHERE asset_key=? AND revision=?',
                        (row['asset_key'], row['revision']))
        return True
    except ValueError as error:
        if str(error) != 'analysis_deferred':
            with db() as con:
                con.execute('UPDATE skip_app_tasks SET attempts=attempts+1 WHERE asset_key=? AND revision=?',
                            (row['asset_key'], row['revision']))
        return False
