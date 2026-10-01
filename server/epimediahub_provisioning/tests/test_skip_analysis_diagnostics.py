"""Tests for bounded diagnosis, secret-safe output and database isolation."""
from __future__ import annotations

import contextlib
import ctypes.util
import hashlib
import importlib.util
import io
import json
import math
import random
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import time
import types
import unittest
from unittest import mock
import urllib.error
import wave

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))
# Framework functions are never used by these standalone worker tests.
try:
    import flask
except ModuleNotFoundError:
    flask = types.ModuleType("flask")
    def forbidden(*_, **__):
        raise AssertionError("Unexpected web-framework call in standalone diagnosis")
    for name in ("abort", "jsonify", "redirect", "render_template", "url_for"):
        setattr(flask, name, forbidden)
    flask.request = flask.session = None
    sys.modules["flask"] = flask

import skip_analysis
import skip_analysis_worker
import skip_markers

spec = importlib.util.spec_from_file_location(
    "diagnosis", SERVER / "deploy/diagnose_skip_analysis.py")
diagnosis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnosis)


class DiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.database = self.path / "provisioning.db"
        self.secret = "TEST_SECRET_DO_NOT_PRINT"
        con = sqlite3.connect(self.database)
        con.row_factory = sqlite3.Row
        con.executescript("""
        CREATE TABLE customers(id INTEGER PRIMARY KEY);
        CREATE TABLE devices(id INTEGER PRIMARY KEY, customer_id INTEGER, display_name TEXT);
        CREATE TABLE customer_playlists(id INTEGER PRIMARY KEY,customer_id INTEGER,name TEXT,config_json TEXT);
        INSERT INTO customers VALUES(1);
        INSERT INTO devices VALUES(1,1,'Test device');
        """)
        skip_markers.migrate(con)
        cfg = {"playlist_type": "XTREAM", "xtream_server": "https://provider.invalid",
               "xtream_username": "test-account", "xtream_password": self.secret}
        con.execute("INSERT INTO customer_playlists VALUES(1,1,'Test',?)",
                    (json.dumps(cfg),))
        con.execute("INSERT INTO skip_analysis_sources VALUES(1,1,'now')")
        self.asset = "a" * 64
        self.source = "b" * 64
        data = dict(asset_key=self.asset, source_key=self.source, media_type="episode",
                    title="Test series", year="2009", season=2, episode=12,
                    duration_ms=60_000, imdb_id="", tmdb_id=0)
        con.execute("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (self.asset, self.source, 1, "123", "mkv", "episode",
                     60_000, 2, 12, "Test series", "2009", "now"))
        record = skip_markers.add_record(con, data, "intro", 10_000, 40_000, False)
        con.execute("UPDATE skip_records SET status='approved' WHERE id=?",
                    (record["id"],))
        con.execute("INSERT INTO skip_jobs(asset_key,status,created_at,updated_at) "
                    "VALUES(?,'failed','now','now')", (self.asset,))
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def diagnose(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = diagnosis.diagnose(SERVER, self.database, 2, 12)
        self.assertNotIn(self.secret, output.getvalue())
        return code, output.getvalue()

    def test_raw_errors_are_never_printed(self):
        cases = [ValueError("https://provider.invalid/" + self.secret),
                 OSError("credentials=" + self.secret),
                 urllib.error.URLError(self.secret)]
        for error in cases:
            with self.subTest(error_type=type(error).__name__):
                with mock.patch.object(skip_analysis_worker, "analyze", side_effect=error):
                    code, output = self.diagnose()
                self.assertEqual(code, 1)
                self.assertIn("FEHLERCODE:", output)

    def test_provider_http_error_category_does_not_expose_url(self):
        error = urllib.error.HTTPError("https://provider.invalid/" + self.secret,
                                       403, self.secret, {}, None)
        self.assertEqual(diagnosis.safe_error(error), "http_403")
        opener = types.SimpleNamespace(open=mock.Mock(side_effect=error))
        events = []
        with mock.patch.object(skip_analysis.urllib.request, "build_opener",
                               return_value=opener):
            with diagnosis.observe_provider(skip_analysis, events):
                observed = skip_analysis.urllib.request.build_opener()
                with self.assertRaises(urllib.error.HTTPError):
                    observed.open("unused")
        self.assertEqual(events, ["http_403"])

    def test_live_playback_defers_without_opening_provider(self):
        con = sqlite3.connect(self.database)
        con.execute("INSERT INTO skip_presence VALUES(1,1,?)", (int(time.time()) + 60,))
        con.commit()
        con.close()
        with mock.patch.object(skip_analysis_worker, "provider_proxy",
                               side_effect=AssertionError("Provider must not open")):
            code, output = self.diagnose()
        self.assertEqual(code, 0)
        self.assertIn("DIAGNOSE_ERGEBNIS: queued", output)

    def test_writes_use_snapshot_but_playback_reads_live_database(self):
        def analysis(db, _job):
            # Reproduce a new heartbeat arriving after the snapshot was taken.
            live = sqlite3.connect(self.database)
            live.execute("INSERT INTO skip_presence VALUES(1,1,?)",
                         (int(time.time()) + 60,))
            live.commit()
            live.close()
            with db() as test:
                self.assertEqual(test.execute("SELECT COUNT(*) FROM skip_presence")
                                 .fetchone()[0], 0)
                test.execute("UPDATE skip_jobs SET status='done'")
                playlist = test.execute("SELECT * FROM customer_playlists").fetchone()
            self.assertTrue(skip_analysis_worker.busy_check(db, [playlist])())
            return "queued", "unused"
        with mock.patch.object(skip_analysis_worker, "analyze", side_effect=analysis):
            code, _ = self.diagnose()
        self.assertEqual(code, 0)
        with sqlite3.connect(self.database) as live:
            self.assertEqual(live.execute("SELECT status FROM skip_jobs").fetchone()[0],
                             "failed")

    @unittest.skipUnless(ctypes.util.find_library("chromaprint"), "Chromaprint required")
    def test_actual_audio_analysis_does_not_modify_source_database(self):
        fixture = self.path / "reference.wav"
        with wave.open(str(fixture), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(11025)
            samples = bytearray()
            for i in range(60 * 11025):
                t = i / 11025
                frequency = 180 + 17 * int(t) % 490
                value = int(9000 * math.sin(2 * math.pi * frequency * t)
                            + 3500 * math.sin(2 * math.pi * frequency * 1.5 * t))
                samples.extend(struct.pack("<h", value))
            wav.writeframes(samples)
        digest_before = hashlib.sha256(self.database.read_bytes()).digest()
        @contextlib.contextmanager
        def local_fixture(_url, busy=lambda: False):
            yield str(fixture)
        with mock.patch.object(skip_analysis_worker, "provider_proxy", local_fixture):
            code, output = self.diagnose()
        self.assertEqual(code, 0, output)
        self.assertIn("DIAGNOSE_ERGEBNIS: done", output)
        self.assertIn("Audio-Fingerabdruck erstellt.", output)
        self.assertEqual(digest_before, hashlib.sha256(self.database.read_bytes()).digest())
        with sqlite3.connect(self.database) as live:
            self.assertEqual(live.execute("SELECT COUNT(*) FROM skip_fingerprints")
                             .fetchone()[0], 0)

    def test_invalid_media_is_categorized_without_raw_decoder_output(self):
        fixture = self.path / "invalid.mkv"
        fixture.write_text(self.secret)
        @contextlib.contextmanager
        def local_fixture(_url, busy=lambda: False):
            yield str(fixture)
        with mock.patch.object(skip_analysis_worker, "provider_proxy", local_fixture):
            code, output = self.diagnose()
        self.assertEqual(code, 1)
        self.assertIn("ABBRUCH_SCHRITT: Videodatei der Ziel-Folge prüfen", output)
        self.assertIn("FEHLERCODE: invalid_media", output)

    def test_decoder_output_limit_is_enforced(self):
        with self.assertRaisesRegex(diagnosis.DiagnosticFailure, "^output_limit$"):
            diagnosis.diagnostic_run([sys.executable, "-c",
                                      "import sys; sys.stdout.write('x'*4096)"],
                                     max_bytes=1024)

    def test_existing_worker_lock_is_respected(self):
        lock_path = self.path / "skip-analysis.lock"
        with lock_path.open("a") as lock:
            diagnosis.fcntl.flock(lock, diagnosis.fcntl.LOCK_EX)
            with mock.patch.object(sys, "argv", ["diagnose", "--data-dir", str(self.path)]):
                with mock.patch.object(diagnosis, "diagnose") as run:
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(diagnosis.main(), 2)
                    run.assert_not_called()

    def test_comparison_reports_ambiguity_and_restores_worker_without_live_writes(self):
        rng = random.Random(219)
        reference = [rng.getrandbits(32) for _ in range(80)]
        target = reference + [rng.getrandbits(32) for _ in range(40)] + reference
        original = skip_analysis_worker.matching_offset
        before = hashlib.sha256(self.database.read_bytes()).digest()
        def analyze(db, _job):
            self.assertIsNone(skip_analysis_worker.matching_offset(reference, target, 125))
            with db() as con:
                con.execute("UPDATE skip_jobs SET status='done'")
            return "no_match", "unused"
        with mock.patch.object(skip_analysis_worker, "analyze", side_effect=analyze):
            code, output = self.diagnose()
        self.assertEqual(code, 0, output)
        self.assertIn("Mehrere ähnlich gute Positionen", output)
        self.assertIn("BESTE_AEHNLICHKEIT: 100.00%", output)
        self.assertIs(skip_analysis_worker.matching_offset, original)
        self.assertEqual(before, hashlib.sha256(self.database.read_bytes()).digest())

    def test_uniform_reference_reports_insufficient_features(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            diagnosis.report_match([123456789] * 80, [123456789] * 200, 125)
        self.assertIn("zu wenig unterschiedliche Merkmale", output.getvalue())
        self.assertNotIn("123456789", output.getvalue())

    def test_unrelated_reference_reports_distance_with_a_bounded_detail_budget(self):
        rng = random.Random(814)
        reference = [rng.getrandbits(32) for _ in range(80)]
        target = [rng.getrandbits(32) for _ in range(200)]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            diagnosis.report_match(reference, target, 125)
        self.assertIn("stimmen nicht ausreichend überein", output.getvalue())
        limited = io.StringIO()
        with contextlib.redirect_stdout(limited):
            diagnosis.report_match(reference, target, 125, max_pairs=1)
        self.assertIn("Rechenlimit", limited.getvalue())

    def test_fresh_reference_replaces_only_the_snapshot_cache(self):
        con = sqlite3.connect(self.database)
        con.execute("INSERT INTO skip_fingerprints VALUES(1,'[1,2,3]',125,2000,30000,'now')")
        con.commit()
        con.close()
        before = hashlib.sha256(self.database.read_bytes()).digest()
        def analyze(db, _job):
            with db() as snapshot:
                self.assertEqual(snapshot.execute("SELECT COUNT(*) FROM skip_fingerprints").fetchone()[0], 0)
            return "no_match", "unused"
        output = io.StringIO()
        with mock.patch.object(skip_analysis_worker, "analyze", side_effect=analyze):
            with contextlib.redirect_stdout(output):
                code = diagnosis.diagnose(SERVER, self.database, 2, 12, fresh_reference=True)
        self.assertEqual(code, 0)
        self.assertEqual(before, hashlib.sha256(self.database.read_bytes()).digest())


if __name__ == "__main__":
    unittest.main()
