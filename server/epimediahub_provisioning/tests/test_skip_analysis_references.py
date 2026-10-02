"""Registration and late reference availability against real SQLite state."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import flask
except ModuleNotFoundError:
    flask = types.ModuleType("flask")
    for name in ("abort", "jsonify", "redirect", "render_template", "url_for", "request", "session"):
        setattr(flask, name, None)
    sys.modules["flask"] = flask
REAL_FLASK = getattr(flask, "Flask", None)

from skip_analysis import provider_asset_key, register_asset, source_url
from skip_analysis_worker import process_one, reference_detail
from skip_markers import add_record, install, migrate, now


class ReferenceFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "references.db"
        self.config = dict(playlist_type="XTREAM", xtream_server="https://provider.example",
                           xtream_username="account", xtream_password="TEST_PROVIDER_SECRET")
        with self.db() as con:
            con.executescript("""
              CREATE TABLE customers(id INTEGER PRIMARY KEY,enabled INTEGER NOT NULL);
              CREATE TABLE devices(id INTEGER PRIMARY KEY,customer_id INTEGER,enabled INTEGER,
                session_token_hash TEXT);
              CREATE TABLE customer_playlists(id INTEGER PRIMARY KEY,customer_id INTEGER,
                name TEXT,config_json TEXT);
              INSERT INTO customers VALUES(1,1),(2,1);
              INSERT INTO devices VALUES(1,1,1,'fixture-token'),(2,2,1,'foreign-token');
            """)
            for playlist, customer in ((1, 1), (2, 2), (3, 1)):
                con.execute("INSERT INTO customer_playlists VALUES(?,?,?,?)",
                            (playlist, customer, "Fixture", json.dumps(self.config)))
            migrate(con)
            con.executemany("INSERT INTO skip_analysis_sources VALUES(?,?,?)",
                            [(1, 1, now()), (2, 1, now()), (3, 0, now())])
            # Existing tests exercise the optional manual-review policy.
            # Automatic acceptance has separate integration coverage.
            con.executemany('INSERT INTO skip_release_settings VALUES(?,0,?)', [(1,now()),(2,now())])
        self.device = dict(id=1, customer_id=1)
        self.seed = self.descriptor("81", 12)
        self.target = self.descriptor("82", 13)

    def tearDown(self):
        self.temp.cleanup()

    @contextlib.contextmanager
    def db(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            with con:
                yield con
        finally:
            con.close()

    def descriptor(self, stream, episode, **changes):
        data = dict(source_key="b" * 64, media_type="episode", title="Lie to Me", year="2009",
                    season=2, episode=episode, duration_ms=2_640_325, imdb_id="", tmdb_id=0,
                    playlist_id=1, stream_id=stream, extension="mkv")
        data.update(changes)
        data["asset_key"] = provider_asset_key(
            source_url({"config_json": json.dumps(self.config)}, data), "episode")
        return data

    def marker(self, data=None, status="approved", disabled=False, length=26530):
        data = data or self.seed
        with self.db() as con:
            row = add_record(con, data, "intro", 283043, 283043 + length, disabled, self.device)
            con.execute("UPDATE skip_records SET status=?,reviewed_at=? WHERE id=?",
                        (status, now(), row["id"]))
        return row["id"]

    def waiting(self, data=None, status="no_reference"):
        data = data or self.target
        with self.db() as con:
            self.assertTrue(register_asset(con, data, data, self.device))
            con.execute("UPDATE skip_jobs SET status=?,attempts=2,detail='previous' WHERE asset_key=?",
                        (status, data["asset_key"]))

    def job(self, data=None):
        with self.db() as con:
            return con.execute("SELECT * FROM skip_jobs WHERE asset_key=?",
                               ((data or self.target)["asset_key"],)).fetchone()


class ReferenceRegistrationTest(ReferenceFixture, unittest.TestCase):
    def test_opening_approved_reference_wakes_waiting_episode_without_new_approval(self):
        record_id = self.marker()
        self.waiting()
        with self.db() as con:
            self.assertIn("Referenzfolge S2 E12", reference_detail(con, self.target))
            self.assertTrue(register_asset(con, self.seed, self.seed, self.device))
            marker = con.execute("SELECT * FROM skip_records WHERE id=?", (record_id,)).fetchone()
        job = self.job()
        self.assertEqual((job["status"], job["attempts"], job["detail"]), ("queued", 0, ""))
        self.assertEqual((marker["status"], marker["start_ms"], marker["end_ms"]),
                         ("approved", 283043, 309573))

    def test_waiting_episode_can_learn_existing_approved_marker_and_propose_match(self):
        self.marker()
        self.waiting(status="queued")
        with mock.patch("skip_analysis_worker.provider_proxy", side_effect=lambda *_: contextlib.nullcontext("fixture")), \
             mock.patch("skip_analysis_worker.probe", return_value=(self.target["duration_ms"], [])):
            self.assertEqual(process_one(self.db), "no_reference")
        self.assertIn("Referenzfolge S2 E12", self.job()["detail"])
        with self.db() as con:
            register_asset(con, self.seed, self.seed, self.device)
        rng = random.Random(987)
        words = [rng.getrandbits(32) for _ in range(80)]
        target_words = [rng.getrandbits(32) for _ in range(240)] + words + [rng.getrandbits(32) for _ in range(80)]
        def fingerprint(_source, start, _length, _busy):
            return (target_words if start == 0 else words), 125.0
        with mock.patch("skip_analysis_worker.provider_proxy", side_effect=lambda *_: contextlib.nullcontext("fixture")), \
             mock.patch("skip_analysis_worker.probe", return_value=(self.target["duration_ms"], [])), \
             mock.patch("skip_analysis_worker.fingerprint", side_effect=fingerprint):
            self.assertEqual(process_one(self.db), "done")
            self.assertEqual(process_one(self.db), "review")
        with self.db() as con:
            proposal = con.execute("SELECT * FROM skip_records WHERE asset_key=? AND source='audio'",
                                   (self.target["asset_key"],)).fetchone()
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal["status"], "pending")
        self.assertGreaterEqual(proposal["confidence"], .9)

    def test_unapproved_disabled_short_or_wrong_runtime_marker_does_not_wake_jobs(self):
        self.waiting()
        cases = [dict(status="pending"), dict(status="rejected"), dict(disabled=True),
                 dict(length=18000), dict(duration_ms=self.seed["duration_ms"] + 5000)]
        for index, options in enumerate(cases):
            with self.subTest(options=options):
                data = self.descriptor(str(90 + index), 12)
                marker_data = data | ({"duration_ms": options["duration_ms"]} if "duration_ms" in options else {})
                self.marker(marker_data, **{key: value for key, value in options.items() if key != "duration_ms"})
                with self.db() as con:
                    register_asset(con, data, data, self.device)
                self.assertEqual(self.job()["status"], "no_reference")

    def test_foreign_disabled_or_unverified_source_never_registers_reference(self):
        self.marker()
        self.waiting()
        cases = [self.seed | {"playlist_id": 2}, self.seed | {"playlist_id": 3},
                 self.seed | {"asset_key": "c" * 64}, self.seed | {"stream_id": "not-numeric"}]
        for data in cases:
            with self.subTest(data=data):
                with self.db() as con:
                    self.assertFalse(register_asset(con, data, data, self.device))
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_assets").fetchone()[0], 1)
                self.assertEqual(self.job()["status"], "no_reference")

    def test_other_series_seasons_and_active_or_failed_jobs_are_untouched(self):
        self.marker()
        self.waiting()
        others = [self.descriptor("83", 14, source_key="c" * 64),
                  self.descriptor("84", 1, season=3),
                  self.descriptor("85", 15), self.descriptor("86", 16)]
        states = ["no_reference", "no_reference", "running", "failed"]
        for data, state in zip(others, states):
            self.waiting(data, state)
        with self.db() as con:
            register_asset(con, self.seed, self.seed, self.device)
        self.assertEqual(self.job()["status"], "queued")
        for data, state in zip(others, states):
            self.assertEqual(self.job(data)["status"], state)

    def test_reference_inspection_is_read_only_and_does_not_expose_credentials(self):
        self.marker()
        self.waiting()
        path = Path(__file__).resolve().parents[1] / "deploy/inspect_skip_references.py"
        spec = importlib.util.spec_from_file_location("inspect_references_fixture", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        before = self.db_path.read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.inspect(self.db_path, 2, 13)
        self.assertIn("Referenzdatei für Analyse registriert: nein", output.getvalue())
        self.assertIn("S2 E12", output.getvalue())
        self.assertNotIn("TEST_PROVIDER_SECRET", output.getvalue())
        self.assertNotIn("provider.example", output.getvalue())
        self.assertEqual(self.db_path.read_bytes(), before)


@unittest.skipUnless(REAL_FLASK, "Flask required for HTTP route checks")
class ReferenceRouteTest(ReferenceFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.site = REAL_FLASK("references-fixture")
        self.site.secret_key = "fixture-session-only"
        @self.site.get("/health", endpoint="health")
        def health():
            return flask.jsonify(status="ok", api_version="0.8.2")
        backend = types.ModuleType("app")
        backend.digest = lambda value: value
        backend.web_auth = lambda: None
        with mock.patch.dict(sys.modules, {"app": backend}):
            install(self.site, self.db)
        self.client = self.site.test_client()
        self.headers = {"Authorization": "Bearer fixture-token"}

    def test_marker_submission_registers_file_without_previous_lookup(self):
        mark = self.seed | dict(segment_type="intro", start_ms=283043, end_ms=309573, disabled=False)
        response = self.client.post("/v1/device/skip/submit", json=mark, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "pending")
        with self.db() as con:
            self.assertIsNotNone(con.execute("SELECT * FROM skip_assets WHERE asset_key=?",
                                            (self.seed["asset_key"],)).fetchone())

    def test_lookup_of_existing_reference_wakes_followup_without_reapproval(self):
        self.marker()
        self.waiting()
        response = self.client.post("/v1/device/skip/lookup", json=self.seed, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["segments"]), 1)
        self.assertEqual(self.job()["status"], "queued")

    def test_manual_markers_without_valid_analysis_source_remain_usable(self):
        for index, playlist in enumerate((0, 2, 3)):
            data = self.descriptor(str(100 + index), 12, playlist_id=playlist)
            mark = data | dict(segment_type="intro", start_ms=283043, end_ms=309573, disabled=False)
            response = self.client.post("/v1/device/skip/submit", json=mark, headers=self.headers)
            self.assertEqual(response.status_code, 200)
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records").fetchone()[0], 3)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_assets").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
