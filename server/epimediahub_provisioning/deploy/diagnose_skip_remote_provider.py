#!/usr/bin/env python3
"""Compare two enabled episodes on Hetzner and the Pi without changing app data.

Only one provider read runs at a time. The normal worker lock and live playback
gate apply. URLs, credentials, raw exceptions and fingerprint words stay private.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import io
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import sys
import threading
import time
import wave
from unittest import mock


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


@contextlib.contextmanager
def relay_observation(audio, emit):
    """Count traffic without retaining peer addresses, tokens or provider URLs."""
    server_class = audio.ThreadingHTTPServer
    lock = threading.Lock()
    stats = dict(requests=0, ranges=0, bytes=0, statuses={})

    def add(key, amount=1):
        with lock:
            stats[key] += amount

    class BodyWriter:
        def __init__(self, writer): self.writer = writer
        def __getattr__(self, name): return getattr(self.writer, name)
        def write(self, data):
            result = self.writer.write(data)
            add('bytes', len(data))
            return result

    def server(address, handler, *args, **kwargs):
        class Observed(handler):
            def relay(self, method):
                add('requests')
                if self.headers.get('Range'): add('ranges')
                return super().relay(method)
            def send_response(self, code, message=None):
                self.media_body = code in (200,206)
                with lock:
                    stats['statuses'][code] = stats['statuses'].get(code, 0) + 1
                return super().send_response(code, message)
            def end_headers(self):
                super().end_headers()
                if self.media_body: self.wfile = BodyWriter(self.wfile)
        return server_class(address, Observed, *args, **kwargs)

    try:
        with mock.patch.object(audio, 'ThreadingHTTPServer', server):
            yield stats
    finally:
        statuses = ','.join(f'{code}:{count}' for code,count in sorted(stats['statuses'].items())) or '-'
        emit(f"PRIVATER ABRUF: Anfragen={stats['requests']}, Range={stats['ranges']}, "
             f"Medienbytes={stats['bytes']}, HTTP={statuses}")


def relay_test(audio, remote, emit, *, timeout=45):
    """Real reverse-tunnel decode, with no provider connection or local decoder."""
    import numpy as np
    import secrets
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from skip_remote_protocol import CLIENT_IP, SERVER_IP, PROVIDER_RELAY_PORT

    rate = 11025
    t = np.arange(rate * 24) / rate
    pcm = (12000*np.sin(2*np.pi*(220+40*(np.floor(t/3)%5))*t)).astype('<i2')
    data = io.BytesIO()
    with wave.open(data, 'wb') as writer:
        writer.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        writer.writeframes(pcm.tobytes())
    blob = data.getvalue()
    token = '/' + secrets.token_urlsafe(24)
    stats = dict(requests=0, denied=0, bytes=0)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)
        def log_message(self, *_): pass
        def do_HEAD(self): self.relay(False)
        def do_GET(self): self.relay(True)
        def relay(self, body):
            stats['requests'] += 1
            if self.client_address[0] != SERVER_IP or self.path != token:
                stats['denied'] += 1
                self.send_error(403); return
            start,end = 0,len(blob)-1
            header = self.headers.get('Range')
            if header:
                match = re.fullmatch(r'bytes=(\d+)-(\d*)', header)
                if not match: self.send_error(400); return
                start = int(match[1]); end = min(int(match[2]) if match[2] else end,end)
                if not 0 <= start <= end:
                    self.send_error(416); return
            self.send_response(206 if header else 200)
            self.send_header('Content-Type','audio/wav')
            self.send_header('Accept-Ranges','bytes')
            self.send_header('Content-Length',str(end-start+1))
            if header: self.send_header('Content-Range',f'bytes {start}-{end}/{len(blob)}')
            self.end_headers()
            if body:
                try:
                    self.wfile.write(blob[start:end+1])
                    stats['bytes'] += end-start+1
                except (BrokenPipeError,ConnectionResetError): pass
    server = ThreadingHTTPServer((CLIENT_IP,PROVIDER_RELAY_PORT),Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    phase = 'Laufzeit'
    deadline = time.monotonic()+timeout
    busy = lambda: time.monotonic() >= deadline
    code = 'ok'
    try:
        source = remote.RemoteSource(f'http://{CLIENT_IP}:{PROVIDER_RELAY_PORT}{token}',busy,via_pi=True)
        duration,_ = audio.probe(source,busy)
        if duration != 24000: raise ValueError('duration_unknown')
        phase = 'Audio'
        fp,step = audio.fingerprint(source,0,20000,busy,require_complete=True)
        if not fp or not 0 < step <= 1000: raise ValueError('fingerprint_failed')
    except Exception as error:
        code = safe_error(error)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
    emit(f"TUNNEL-TEST: {phase}={code}, Anfragen={stats['requests']}, "
         f"Abgewiesen={stats['denied']}, Testbytes={stats['bytes']}")
    if code != 'ok' and stats['requests'] == 0:
        emit('Am privaten Raspberry-Abrufport kam keine Hetzner-Anfrage an')
    if code == 'ok':
        emit('Privater Medien-Rückweg und Audiodekodierung auf Hetzner: OK')
    return code == 'ok'


def read_episode(audio, remote, asset, playlist, busy, local, emit):
    started = time.monotonic()
    phase = 'Laufzeit'
    name = 'RASPBERRY' if local else 'HETZNER'
    observe = not local and remote.provider_path() == 'raspberry'
    try:
        execution = remote.local_execution() if local else contextlib.nullcontext()
        observation = relay_observation(audio,emit) if observe else contextlib.nullcontext()
        with execution, observation:
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
    if remote.provider_path() == 'raspberry':
        emit('Hetzner liest die echten Folgen über den privaten Raspberry-Abruf')
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
        path = 'privaten Medienabruf' if remote.provider_path() == 'raspberry' else 'Anbieterzugriff'
        emit('ERGEBNIS: Raspberry liest die Folge; Hetzner scheitert am '+path)
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
    parser.add_argument('--provider-via-raspberry', action='store_true',
                        help='Rückweg mit Testaudio prüfen, anschließend echte Folgen über den Raspberry lesen')
    args = parser.parse_args()
    emit = lambda text: print(text, flush=True)
    if os.geteuid()!=0:
        emit('Bitte mit sudo ausführen')
        return 2
    stage = args.app_dir / 'remote-analysis-stage'
    if not (stage / 'skip_remote_client.py').is_file():
        emit('Vorbereiteter Remote-Analysecode fehlt')
        return 2
    # After activation the installed role also preserves the provider path.
    primary = args.app_dir if not args.provider_via_raspberry and (args.app_dir / 'skip_remote_role.json').exists() else stage
    sys.path[:0] = [str(primary), str(args.app_dir)]
    os.environ['SKIP_ANALYSIS_REMOTE_URL'] = 'http://10.87.26.1:8790'
    if args.provider_via_raspberry:
        os.environ['SKIP_ANALYSIS_PROVIDER_PATH'] = 'raspberry'
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
            if args.provider_via_raspberry:
                import skip_analysis as audio
                import skip_remote_client as remote
                remote.health()
                remote_idle(remote,lambda:False)
                emit('Zuerst Testaudio über den privaten Rückweg; kein Anbieterzugriff')
                if not relay_test(audio,remote,emit): return 2
                remote_idle(remote,lambda:False)
            return compare(db, emit)
    except Exception as error:
        emit('DIAGNOSE_ABBRUCH: '+safe_error(error))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
