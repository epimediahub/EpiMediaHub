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
}


def safe_error(error):
    if isinstance(error, (DiagnosticFailure, ValueError)):
        code = str(error)
        if code in SAFE_CODES or re.fullmatch(r"http_[1-5][0-9]{2}", code):
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


def diagnose(app_dir, db_path, season=None, episode=None, job_id=None):
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

        original_run = analysis.run
        original_probe, original_fp = worker.probe, worker.fingerprint
        original_busy = worker.busy_check
        probes = [0]

        def probe(source, busy=lambda: False):
            probes[0] += 1
            stage[0] = ("Videodatei der Ziel-Folge prüfen" if probes[0] == 1
                        else "Videodatei der Referenzfolge prüfen")
            print("SCHRITT:", stage[0], flush=True)
            result = original_probe(source, busy)
            print("Dateiprüfung erfolgreich.", flush=True)
            return result

        def fingerprint(source, start_ms, length_ms, busy=lambda: False):
            stage[0] = ("Ton der Ziel-Folge auswerten" if start_ms == 0
                        else "Ton der freigegebenen Referenz auswerten")
            print("SCHRITT:", stage[0], flush=True)
            result = original_fp(source, start_ms, length_ms, busy)
            print("Audio-Fingerabdruck erstellt.", flush=True)
            return result

        analysis.run = diagnostic_run
        worker.probe, worker.fingerprint = probe, fingerprint
        # Playback is checked against the LIVE database, not the test snapshot.
        worker.busy_check = lambda _db, playlists: original_busy(live_db, playlists)
        try:
            stage[0] = "Playlist und Wiedergabestatus prüfen"
            with observe_provider(analysis, events):
                status, _detail = worker.analyze(test_db, job)
            result = status if status in allowed_states else "unbekannt"
            print("DIAGNOSE_ERGEBNIS:", result, flush=True)
            print("Die echte Datenbank wurde nicht verändert.", flush=True)
            return 0
        finally:
            analysis.run = original_run
            worker.probe, worker.fingerprint = original_probe, original_fp
            worker.busy_check = original_busy
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
                            args.season, args.episode, args.job_id)
    except Exception as error:
        print("FEHLERCODE:", safe_error(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
