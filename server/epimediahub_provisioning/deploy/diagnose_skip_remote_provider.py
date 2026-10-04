#!/usr/bin/env python3
"""Compare two enabled episodes on Hetzner and the Pi without changing app data.

Only one provider read runs at a time. The normal worker lock and live playback
gate apply. URLs, credentials, raw exceptions and fingerprint words stay private.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import sys
import time


SAFE_CODES = {
    'analysis_deferred', 'analysis_limit', 'analysis_failed', 'analysis_input_limit',
    'provider_timeout', 'provider_dns', 'provider_tls', 'provider_connection',
    'unsafe_source', 'redirect_limit', 'redirect_downgrade', 'not_analyzable',
    'credentials_missing', 'duration_unknown', 'fingerprint_window',
    'fingerprint_failed', 'fingerprint_incomplete', 'chromaprint_unavailable',
    'remote_cleanup_pending', 'diagnosis_time_limit',
}


def safe_error(error):
    text = str(error)
    if text in SAFE_CODES or re.fullmatch(r'provider_http_[1-5][0-9]{2}', text):
        return text
    if isinstance(error, sqlite3.Error):
        return 'database_error'
    if isinstance(error, OSError):
        return 'system_error'
    return 'analysis_failed'


def read_episode(audio, remote, asset, playlist, busy, local, emit):
    started = time.monotonic()
    phase = 'Laufzeit'
    name = 'RASPBERRY' if local else 'HETZNER'
    try:
        execution = remote.local_execution() if local else contextlib.nullcontext()
        with execution:
            if busy():
                raise ValueError('analysis_deferred')
            with audio.provider_proxy(audio.source_url(playlist, asset), busy) as source:
                duration, _ = audio.probe(source, busy)
                if duration < 15_000:
                    raise ValueError('duration_unknown')
                emit(f'{name}: Laufzeit {duration/1000:.1f} s gelesen; jetzt Audio prüfen …')
                phase = 'Audio'
                fp, step = audio.fingerprint(source, 0, min(20_000, duration), busy,
                                             require_complete=True)
            if not fp or not 0 < step <= 1000:
                raise ValueError('fingerprint_failed')
        code = 'ok'
    except Exception as error:
        code = safe_error(error)
    elapsed = time.monotonic() - started
    emit(f'{name}: {phase} = {code} ({elapsed:.1f} s)')
    return dict(code=code, phase=phase)


def remote_idle(remote, busy, *, timeout=12, quiet=5):
    """Wait for cancellation cleanup, including an upstream socket read timeout."""
    deadline = time.monotonic() + timeout
    inactive_since = None
    while time.monotonic() < deadline:
        if busy():
            raise ValueError('analysis_deferred')
        if remote.health().get('active') is False:
            if inactive_since is None:
                inactive_since = time.monotonic()
            if time.monotonic() - inactive_since >= quiet:
                return
        else:
            inactive_since = None
        time.sleep(.25)
    raise ValueError('remote_cleanup_pending')


def compare(db, emit=print, *, limit=2, max_seconds=180):
    import skip_analysis as audio
    import skip_remote_client as remote
    from skip_analysis_worker import busy_check

    deadline = time.monotonic() + max_seconds
    with db() as con:
        assets = con.execute("""SELECT a.* FROM skip_assets a
          JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
          JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
          JOIN customer_playlists p ON p.id=a.playlist_id
          JOIN customers c ON c.id=p.customer_id AND c.enabled=1
          LEFT JOIN skip_language_priority l ON l.asset_key=a.asset_key
          WHERE a.media_type='episode'
          ORDER BY COALESCE(l.priority,1),a.updated_at DESC LIMIT 32""").fetchall()
        playlists = {a['playlist_id']: con.execute('SELECT * FROM customer_playlists WHERE id=?',
                      (a['playlist_id'],)).fetchone() for a in assets}
    # Reuse the exact installed protocol and source-version check first.
    remote.health()
    emit('Private Verbindung und Codeversionen: OK')
    results = []
    for asset in assets:
        playlist = playlists[asset['playlist_id']]
        playback = busy_check(db, [playlist])
        if playback():
            continue
        if time.monotonic() >= deadline:
            emit('Diagnose-Zeitlimit erreicht')
            break
        phase_deadline = [deadline]
        def busy():
            return playback() or time.monotonic() >= min(deadline, phase_deadline[0])
        # Do not open another source while an old remote operation is finishing.
        remote_idle(remote, busy)
        emit(f"Folge {len(results)+1}: Staffel {int(asset['season'])}, Folge {int(asset['episode'])}")
        phase_deadline[0] = time.monotonic() + 60
        distant = read_episode(audio, remote, asset, playlist, busy, False, emit)
        phase_deadline[0] = deadline
        remote_idle(remote, busy)
        phase_deadline[0] = time.monotonic() + 60
        local = read_episode(audio, remote, asset, playlist, busy, True, emit)
        results.append((distant, local))
        if playback():
            emit('Wiedergabe hat begonnen; Diagnose beendet')
            break
        if len(results) >= limit:
            break
    if not results:
        emit('Keine aktuell freie, aktivierte Anbieterfolge für den Vergleich vorhanden')
        return 2
    if any(d['code']=='ok' and p['code']=='ok' for d,p in results):
        emit('ERGEBNIS: Mindestens eine Folge funktioniert auf beiden Geräten')
    elif any(d['code']!='ok' and p['code']=='ok' for d,p in results):
        emit('ERGEBNIS: Raspberry liest die Folge; Hetzner scheitert am Anbieterzugriff')
    else:
        emit('ERGEBNIS: Auch vom Raspberry wurde keine vollständige Audioprobe gelesen')
    return 0


def data_directory(env_file):
    result = Path('/var/lib/epimediahub')
    for line in env_file.read_text().splitlines():
        key, sep, value = line.partition('=')
        if sep and key.strip()=='EPIMEDIAHUB_DATA_DIR':
            parts = shlex.split(value, comments=True)
            if len(parts)!=1 or not Path(parts[0]).is_absolute():
                raise ValueError('invalid_configuration')
            result = Path(parts[0])
    return result


@contextlib.contextmanager
def worker_pause(data_dir, emit):
    unit = 'epimediahub-skip-analysis.timer'
    active = subprocess.run(['systemctl','is-active','--quiet',unit], check=False).returncode==0
    try:
        if active:
            subprocess.run(['systemctl','stop',unit], check=True)
        with (data_dir / 'skip-analysis.lock').open('a') as lock:
            started = time.monotonic()
            reported = -1
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    elapsed = time.monotonic()-started
                    if elapsed >= 900:
                        raise ValueError('diagnosis_time_limit')
                    tick = int(elapsed//20)
                    if tick!=reported:
                        emit('Warte auf das Ende des laufenden lokalen Analyseauftrags …')
                        reported = tick
                    time.sleep(.25)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
    finally:
        if active:
            subprocess.run(['systemctl','start',unit], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-dir', type=Path, default=Path('/opt/epimediahub/provisioning'))
    parser.add_argument('--env-file', type=Path, default=Path('/etc/epimediahub/provisioning.env'))
    args = parser.parse_args()
    emit = lambda text: print(text, flush=True)
    if os.geteuid()!=0:
        emit('Bitte mit sudo ausführen')
        return 2
    stage = args.app_dir / 'remote-analysis-stage'
    if not (stage / 'skip_remote_client.py').is_file():
        emit('Vorbereiteter Remote-Analysecode fehlt')
        return 2
    sys.path[:0] = [str(stage), str(args.app_dir)]
    os.environ['SKIP_ANALYSIS_REMOTE_URL'] = 'http://10.87.26.1:8790'
    try:
        data_dir = data_directory(args.env_file)
        database = data_dir / 'provisioning.db'
        @contextlib.contextmanager
        def db():
            con = sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)
            con.row_factory = sqlite3.Row
            try:
                yield con
            finally:
                con.close()
        emit('Anbieter-Vergleich: maximal zwei Folgen, je 20 Sekunden Audio')
        with worker_pause(data_dir, emit):
            return compare(db, emit)
    except Exception as error:
        emit('DIAGNOSE_ABBRUCH: '+safe_error(error))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
