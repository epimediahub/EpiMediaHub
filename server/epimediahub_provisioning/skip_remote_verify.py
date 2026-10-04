"""Read-only migration check against a real enabled, idle provider episode."""
from __future__ import annotations

import argparse
import contextlib
import sqlite3
from pathlib import Path

from skip_analysis import source_url, provider_proxy, probe, fingerprint
from skip_analysis_worker import busy_check
from skip_remote_client import configured, health
from skip_automation import provider_api


def verify(db):
    if not configured():
        raise ValueError('remote_not_configured')
    health()
    with db() as con:
        candidates = con.execute("""SELECT a.* FROM skip_assets a
          JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
          JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
          JOIN customer_playlists p ON p.id=a.playlist_id
          JOIN customers c ON c.id=p.customer_id AND c.enabled=1
          LEFT JOIN skip_language_priority l ON l.asset_key=a.asset_key
          WHERE a.media_type='episode'
          ORDER BY COALESCE(l.priority,1),a.updated_at DESC LIMIT 32""").fetchall()
        playlists = {row['playlist_id']: con.execute('SELECT * FROM customer_playlists WHERE id=?',
                                                    (row['playlist_id'],)).fetchone() for row in candidates}
    if not candidates:
        raise ValueError('no_enabled_episode')
    for asset in candidates:
        playlist = playlists[asset['playlist_id']]
        busy = busy_check(db, [playlist])
        if busy():
            continue
        # Exercise the catalogue path under the remote role before installing
        # it. A media-only check cannot detect a JSON fetch using RemoteSource.
        listing = provider_api(playlist, 'get_series', busy, _limit=24_000_000)
        if not isinstance(listing, list):
            raise ValueError('catalogue_response_invalid')
        del listing
        with provider_proxy(source_url(playlist, asset), busy) as source:
            duration, _ = probe(source, busy)
            if asset['duration_ms'] and abs(duration - asset['duration_ms']) > 2000:
                continue
            words, step = fingerprint(source, 0, min(20_000, duration), busy, require_complete=True)
        if not words or not 0 < step <= 1000:
            raise ValueError('fingerprint_failed')
        return
    raise ValueError('no_idle_matching_episode')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    args = parser.parse_args()
    @contextlib.contextmanager
    def db():
        connection = sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()
    try:
        verify(db)
    except (ValueError, OSError, sqlite3.Error) as error:
        reason = getattr(error, 'reason', str(error))
        # All ValueErrors from the analysis layer are fixed codes, not URLs.
        if isinstance(error, sqlite3.Error):
            reason = 'database_check_failed'
        raise SystemExit('Anbieterprüfung vor Umstellung fehlgeschlagen: ' + reason) from None
    print('Anbieterkatalog auf Raspberry geprüft; echte Folge auf Hetzner gelesen und Audio-Fingerprint berechnet; zentrale Daten unverändert')


if __name__ == '__main__':
    main()
