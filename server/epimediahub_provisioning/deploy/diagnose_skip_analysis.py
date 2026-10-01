#!/usr/bin/env python3
"""Bounded analysis diagnosis; database changes stay in an in-memory snapshot.

Run with the provisioning virtualenv. Only enabled sources and an existing job
are used, through the installed worker's network and playback safeguards.
Raw exceptions, decoder output, commands and provider URLs are never printed.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib
import os
import re
import shutil
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
from contextlib import contextmanager
from pathlib import Path


class DiagnosticFailure(Exception):
    pass


SAFE_CODES = {
    "not_analyzable", "credentials_missing", "unsafe_source",
    "analysis_deferred", "analysis_limit", "analysis_failed",
    "duration_unknown", "fingerprint_window", "chromaprint_unavailable",
    "fingerprint_failed", "decoder_timeout", "output_limit", "decoder_missing",
    "audio_missing", "format_blocked", "protocol_blocked", "invalid_media",
    "seek_failed", "database_too_large", "database_snapshot_timeout",
    "redirect_limit", "redirect_downgrade", "provider_timeout", "provider_dns",
    "provider_tls", "provider_connection", "analysis_input_limit",
}


def safe_error(error):
    if isinstance(error, (DiagnosticFailure, ValueError)):
        code = str(error)
        if code in SAFE_CODES or re.fullmatch(r"(?:provider_)?http_[1-5][0-9]{2}", code):
            return code
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "network_timeout"
    if isinstance(reason, socket.gaierror):
        return "dns_failed"
    if isinstance(reason, ssl.SSLError):
        return "tls_failed"
    if isinstance(error, urllib.error.HTTPError):
        return "http_" + str(error.code) if 100 <= error.code <= 599 else "http_error"
    if isinstance(error, sqlite3.Error):
        return "database_error"
    if isinstance(error, FileNotFoundError):
        return "file_or_program_missing"
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return "python_dependency_missing"
    if isinstance(error, OSError):
        return "operating_system_error"
    if isinstance(error, (KeyError, TypeError, OverflowError, AttributeError)):
        return "metadata_or_library_error"
    return "analysis_error"


def decoder_error(raw):
    # Return fixed categories, never the decoder's potentially sensitive text.
    text = raw.lower()
    http = re.search(r"(?:http error|server returned)\s+([1-5][0-9]{2})", text)
    if http:
        return "http_" + http.group(1)
    if "matches no streams" in text or "does not contain any stream" in text:
        return "audio_missing"
    if "protocol" in text and "whitelist" in text:
        return "protocol_blocked"
    if "format" in text and "whitelist" in text:
        return "format_blocked"
    if "unknown decoder" in text or "decoder not found" in text:
        return "decoder_missing"
    if "invalid data" in text or "moov atom not found" in text:
        return "invalid_media"
    if "could not seek" in text or "unable to seek" in text:
        return "seek_failed"
    return "analysis_failed"


def diagnostic_run(command, max_bytes=20_000_000, timeout=180, busy=lambda: False):
    """Keep the installed decoder's bounds and categorize its discarded stderr."""
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=errors)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if busy():
                    raise DiagnosticFailure("analysis_deferred")
                if time.monotonic() - started > timeout:
                    raise DiagnosticFailure("decoder_timeout")
                if (os.fstat(output.fileno()).st_size > max_bytes
                        or os.fstat(errors.fileno()).st_size > 131_072):
                    raise DiagnosticFailure("output_limit")
                time.sleep(.2)
            if os.fstat(output.fileno()).st_size > max_bytes:
                raise DiagnosticFailure("output_limit")
            if process.returncode:
                errors.seek(0)
                raise DiagnosticFailure(decoder_error(
                    errors.read(65_536).decode("utf-8", errors="replace")))
            output.seek(0)
            return output.read(max_bytes + 1)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)


@contextmanager
def observe_provider(analysis, events):
    original = analysis.urllib.request.build_opener

    def build(*args, **kwargs):
        opener = original(*args, **kwargs)
        real_open = opener.open

        def open_request(*open_args, **open_kwargs):
            try:
                return real_open(*open_args, **open_kwargs)
            except Exception as error:
                if len(events) < 20:
                    events.append(safe_error(error))
                raise
        opener.open = open_request
        return opener

    analysis.urllib.request.build_opener = build
    try:
        yield
    finally:
        analysis.urllib.request.build_opener = original


def report_match(reference, target, step_ms, busy=lambda: False, max_pairs=12_000_000):
    """Only bounded aggregate scores; no fingerprint words or raw audio."""
    print("REFERENZ_WERTE:", len(reference), "| unterschiedliche:", len(set(reference)), flush=True)
    print("ZIEL_WERTE:", len(target), flush=True)
    if not 40 <= len(reference) <= len(target) <= 10_000:
        print("VERGLEICH_GRUND: Fingerabdruck zu kurz oder außerhalb der erlaubten Länge", flush=True)
        return
    minimum = max(15, len(reference) // 5)
    if len(set(reference)) < minimum:
        print("VERGLEICH_GRUND: Referenzton enthält zu wenig unterschiedliche Merkmale", flush=True)
        return
    windows = len(target) - len(reference) + 1
    if windows * len(reference) > max_pairs:
        print("VERGLEICH_GRUND: Zusätzliche Detailprüfung erreicht ihr Rechenlimit", flush=True)
        return
    best = (1.0, 0)
    accepted = []
    started = time.monotonic()
    for offset in range(windows):
        if offset % 32 == 0:
            if busy():
                raise DiagnosticFailure("analysis_deferred")
            if time.monotonic() - started > 10:
                print("VERGLEICH_GRUND: Zusätzliche Detailprüfung erreicht ihr Zeitlimit", flush=True)
                return
        distance = sum((a ^ b).bit_count() for a, b in
                       zip(reference, target[offset:offset + len(reference)])) / (32 * len(reference))
        best = min(best, (distance, offset))
        if distance <= .10:
            accepted.append((distance, offset))
    score, offset = best
    print(f"BESTE_AEHNLICHKEIT: {(1 - score) * 100:.2f}% | benötigt: mindestens 90% und eindeutig", flush=True)
    print(f"BESTE_POSITION_SEKUNDEN: {offset * step_ms / 1000:.3f}", flush=True)
    alternatives = sum(abs(index - offset) * step_ms > 2000 and distance <= score + .025
                       for distance, index in accepted)
    print("AUSREICHEND_AEHNLICHE_POSITIONEN:", len(accepted), "| weitere ähnlich gute:", alternatives, flush=True)
    if not accepted:
        reason = "Ton der Referenz und Zielfolge stimmen nicht ausreichend überein"
    elif alternatives:
        reason = "Mehrere ähnlich gute Positionen; das Intro ist nicht eindeutig zuzuordnen"
    else:
        reason = "Ausreichend ähnlicher und eindeutiger Audiotreffer"
    print("VERGLEICH_GRUND:", reason, flush=True)


def diagnose(app_dir, db_path, season=None, episode=None, job_id=None, fresh_reference=False):
    print("EpiMediaHub Introanalyse: Diagnose", flush=True)
    print("FFmpeg:", "vorhanden" if shutil.which("ffmpeg") else "fehlt", flush=True)
    print("FFprobe:", "vorhanden" if shutil.which("ffprobe") else "fehlt", flush=True)
    stage = ["Module laden"]
    events = []
    snapshot = None
    try:
        sys.path.insert(0, str(app_dir.resolve()))
        analysis = importlib.import_module("skip_analysis")
        worker = importlib.import_module("skip_analysis_worker")

        @contextmanager
        def live_db():
            con = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True,
                                  timeout=5)
            con.row_factory = sqlite3.Row
            try:
                yield con
            finally:
                con.close()

        snapshot = sqlite3.connect(":memory:", check_same_thread=False,
                                   isolation_level=None)
        snapshot.row_factory = sqlite3.Row
        guard = threading.RLock()
        stage[0] = "Datenbank lesen"
        with live_db() as source:
            size = (source.execute("PRAGMA page_count").fetchone()[0]
                    * source.execute("PRAGMA page_size").fetchone()[0])
            if size > 64 * 1024 * 1024:
                raise DiagnosticFailure("database_too_large")
            started = time.monotonic()
            def progress(*_):
                if time.monotonic() - started > 15:
                    raise DiagnosticFailure("database_snapshot_timeout")
            source.backup(snapshot, pages=128, progress=progress, sleep=.05)

        @contextmanager
        def test_db():
            with guard:
                yield snapshot

        filters, parameters = [], []
        for field, value in (("j.id", job_id), ("a.season", season),
                             ("a.episode", episode)):
            if value is not None:
                filters.append(field + "=?")
                parameters.append(value)
        where = " WHERE " + " AND ".join(filters) if filters else ""
        job = snapshot.execute(
            "SELECT j.*,a.season,a.episode FROM skip_jobs j "
            "JOIN skip_assets a ON a.asset_key=j.asset_key" + where
            + " ORDER BY j.id DESC LIMIT 1", parameters).fetchone()
        if job is None:
            print("Kein passender Analyseauftrag vorhanden.", flush=True)
            return 2
        allowed_states = {"queued", "running", "failed", "disabled", "unmatched",
                          "no_reference", "no_match", "done", "review"}
        state = job["status"] if job["status"] in allowed_states else "unbekannt"
        print(f"Auftrag {job['id']} | S{job['season']} E{job['episode']} | {state}",
              flush=True)
        asset = snapshot.execute("SELECT * FROM skip_assets WHERE asset_key=?",
                                 (job["asset_key"],)).fetchone()
        print("GEMELDETE_ZIEL_LAUFZEIT_MS:", asset["duration_ms"], flush=True)
        references = snapshot.execute("""SELECT r.season,r.episode,r.duration_ms,r.start_ms,r.end_ms
          FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
          JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
          WHERE r.source_key=? AND r.season=? AND r.segment_type='intro'
          AND r.status='approved' AND r.disabled=0
          AND r.end_ms-r.start_ms BETWEEN 19000 AND 300000
          AND ABS(a.duration_ms-r.duration_ms)<=2000
          ORDER BY r.reviewed_at DESC LIMIT 3""",
          (asset["source_key"], asset["season"])).fetchall()
        print("PASSENDE_REGISTRIERTE_REFERENZEN:", len(references), flush=True)
        for reference in references:
            print(f"REFERENZ: S{reference['season']} E{reference['episode']} | "
                  f"Laufzeit_ms: {reference['duration_ms']} | "
                  f"Intro_ms: {reference['start_ms']} bis {reference['end_ms']}", flush=True)
        if fresh_reference:
            # Only the disposable in-memory snapshot is changed.
            snapshot.execute("""DELETE FROM skip_fingerprints WHERE record_id IN (
              SELECT id FROM skip_records WHERE source_key=? AND season=?
              AND segment_type='intro' AND status='approved')""",
              (asset["source_key"], asset["season"]))
            print("Referenzfingerabdruck wird für diese Diagnose frisch berechnet.", flush=True)

        original_run = analysis.run
        original_probe, original_fp = worker.probe, worker.fingerprint
        original_busy = worker.busy_check
        original_match = worker.matching_offset
        probes = [0]
        comparisons = [0]
        live_busy = [lambda: False]

        def probe(source, busy=lambda: False):
            probes[0] += 1
            stage[0] = ("Videodatei der Ziel-Folge prüfen" if probes[0] == 1
                        else "Videodatei der Referenzfolge prüfen")
            print("SCHRITT:", stage[0], flush=True)
            result = original_probe(source, busy)
            print("Dateiprüfung erfolgreich.", flush=True)
            print("GEMESSENE_LAUFZEIT_MS:", result[0], flush=True)
            return result

        def fingerprint(source, start_ms, length_ms, busy=lambda: False):
            stage[0] = ("Ton der Ziel-Folge auswerten" if start_ms == 0
                        else "Ton der freigegebenen Referenz auswerten")
            print("SCHRITT:", stage[0], flush=True)
            result = original_fp(source, start_ms, length_ms, busy)
            print("Audio-Fingerabdruck erstellt.", flush=True)
            print("AUDIO_WERTE:", len(result[0]), "| Zeitschritt_ms:", round(result[1], 6), flush=True)
            if start_ms == 0:
                print("ZIEL_SUCHFENSTER_SEKUNDEN:", round(length_ms / 1000, 3), flush=True)
            return result

        def matching(reference, target, step_ms):
            comparisons[0] += 1
            stage[0] = "Audio der Referenz mit Zielfolge vergleichen"
            if live_busy[0]():
                raise DiagnosticFailure("analysis_deferred")
            result = original_match(reference, target, step_ms)
            report_match(reference, target, step_ms, live_busy[0])
            print("INSTALLIERTER_VERGLEICH:", "Treffer" if result else "kein eindeutiger Treffer", flush=True)
            return result

        def live_busy_check(_db, playlists):
            live_busy[0] = original_busy(live_db, playlists)
            return live_busy[0]

        analysis.run = diagnostic_run
        worker.probe, worker.fingerprint = probe, fingerprint
        worker.matching_offset = matching
        # Playback is checked against the LIVE database, not the test snapshot.
        worker.busy_check = live_busy_check
        try:
            stage[0] = "Playlist und Wiedergabestatus prüfen"
            with observe_provider(analysis, events):
                status, _detail = worker.analyze(test_db, job)
            result = status if status in allowed_states else "unbekannt"
            if status == "no_match" and comparisons[0] == 0:
                print("VERGLEICH_GRUND: Kein Referenzpaar verglichen; Referenzlaufzeit oder Zeitschritt passen nicht", flush=True)
            print("DIAGNOSE_ERGEBNIS:", result, flush=True)
            print("Die echte Datenbank wurde nicht verändert.", flush=True)
            return 0
        finally:
            analysis.run = original_run
            worker.probe, worker.fingerprint = original_probe, original_fp
            worker.busy_check = original_busy
            worker.matching_offset = original_match
    except KeyboardInterrupt:
        print("Diagnose beendet.", flush=True)
        return 130
    except Exception as error:
        print("ABBRUCH_SCHRITT:", stage[0], flush=True)
        print("FEHLERCODE:", safe_error(error), flush=True)
        if events:
            print("ANBIETER_ZUGRIFF:", ", ".join(sorted(set(events))), flush=True)
        return 1
    finally:
        if snapshot is not None:
            snapshot.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, default=Path("/opt/epimediahub/provisioning"))
    parser.add_argument("--data-dir", type=Path, default=Path(
        os.environ.get("EPIMEDIAHUB_DATA_DIR", "/var/lib/epimediahub")))
    parser.add_argument("--season", type=int)
    parser.add_argument("--episode", type=int)
    parser.add_argument("--job-id", type=int)
    parser.add_argument("--fresh-reference", action="store_true",
                        help="Recompute reference audio only in the diagnostic snapshot")
    args = parser.parse_args()
    try:
        # Share the worker's lock, so diagnosis never opens a parallel analysis.
        with (args.data_dir / "skip-analysis.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("Der reguläre Analysedienst arbeitet gerade. Später erneut ausführen.")
                return 2
            return diagnose(args.app_dir, args.data_dir / "provisioning.db",
                            args.season, args.episode, args.job_id, args.fresh_reference)
    except Exception as error:
        print("FEHLERCODE:", safe_error(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
