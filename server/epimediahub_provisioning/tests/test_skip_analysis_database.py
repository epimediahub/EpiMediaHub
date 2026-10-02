"""Actual concurrent SQLite requests, lifecycle and large catalogue regression."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_skip_analysis_references import ReferenceFixture, REAL_FLASK
from skip_database import connect, enable_wal
from skip_progress import overview

ROOT = Path(__file__).resolve().parents[1]


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "db.sqlite"
        with connect(self.path) as con:
            enable_wal(con)
            con.execute("CREATE TABLE data(value TEXT UNIQUE)")

    def test_commit_closes_connection_and_retained_cursor(self):
        with connect(self.path) as con:
            con.execute("INSERT INTO data VALUES('saved')")
            cursor = con.execute("SELECT * FROM data")
        with self.assertRaises(sqlite3.ProgrammingError):
            cursor.fetchone()
        with self.assertRaises(sqlite3.ProgrammingError):
            con.execute("SELECT 1")
        with connect(self.path) as con:
            self.assertEqual(con.execute("SELECT value FROM data").fetchone()[0], "saved")

    def test_failed_transaction_rolls_back_and_closes(self):
        with self.assertRaises(ValueError):
            with connect(self.path) as con:
                con.execute("INSERT INTO data VALUES('discarded')")
                raise ValueError("abort")
        with self.assertRaises(sqlite3.ProgrammingError):
            con.execute("SELECT 1")
        with connect(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM data").fetchone()[0], 0)

    def test_commit_failure_rolls_back_releases_writer_and_closes(self):
        with connect(self.path) as con:
            con.execute("CREATE TABLE parent(id INTEGER PRIMARY KEY)")
            con.execute("CREATE TABLE child(id INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED)")
        with self.assertRaises(sqlite3.IntegrityError):
            with connect(self.path) as con:
                con.execute("INSERT INTO child VALUES(99)")
        with self.assertRaises(sqlite3.ProgrammingError):
            con.execute("SELECT 1")
        with connect(self.path) as con:
            con.execute("INSERT INTO parent VALUES(1)")
            self.assertEqual(con.execute("SELECT COUNT(*) FROM child").fetchone()[0], 0)

    def test_two_writers_wait_for_commit_without_losing_either_write(self):
        attempted = threading.Event()
        def second():
            with connect(self.path, timeout=2) as con:
                attempted.set()
                con.execute("INSERT INTO data VALUES('second')")
        with ThreadPoolExecutor(max_workers=1) as pool:
            with connect(self.path) as first:
                first.execute("INSERT INTO data VALUES('first')")
                future = pool.submit(second)
                self.assertTrue(attempted.wait(1))
            future.result(timeout=3)
        with connect(self.path) as con:
            self.assertEqual([r[0] for r in con.execute("SELECT * FROM data ORDER BY value")], ["first", "second"])

    def test_locked_worker_exits_before_application_import_or_migration(self):
        with (Path(self.directory.name) / "skip-analysis.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = subprocess.run([sys.executable, str(ROOT / "skip_analysis_worker.py"), "--once"],
                                    env=os.environ | {"EPIMEDIAHUB_DATA_DIR": self.directory.name},
                                    capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((Path(self.directory.name) / "provisioning.db").exists())


@unittest.skipUnless(REAL_FLASK, "Flask required for concurrent HTTP requests")
class DatabaseRequestsTests(ReferenceFixture, unittest.TestCase):
    def db(self):
        return connect(self.db_path, timeout=.2)

    def setUp(self):
        super().setUp()
        with self.db() as con:
            enable_wal(con)
            con.execute("ALTER TABLE customers ADD COLUMN name TEXT NOT NULL DEFAULT 'Test customer'")
        self.site = REAL_FLASK("concurrent-db-fixture", template_folder=str(ROOT / "templates"))
        self.site.secret_key = "fixture"
        self.site.testing = True
        self.site.add_url_rule("/dashboard", "dashboard", lambda: "Dashboard")
        self.site.add_url_rule("/health", "health", lambda: self.site.response_class('{"status":"ok"}', mimetype="application/json"))
        backend = types.ModuleType("app")
        backend.digest = lambda value: value
        backend.web_auth = lambda: None
        from skip_markers import install
        with mock.patch.dict(sys.modules, {"app": backend}):
            install(self.site, self.db)

    def test_presence_commits_while_dashboard_reader_holds_old_snapshot(self):
        with self.db() as reader:
            reader.execute("BEGIN")
            self.assertEqual(reader.execute("SELECT COUNT(*) FROM skip_presence").fetchone()[0], 0)
            with ThreadPoolExecutor(max_workers=2) as pool:
                presence = pool.submit(lambda: self.site.test_client().post("/v1/device/skip/presence", json={"playlist_id": 1}, headers={"Authorization": "Bearer fixture-token"}))
                dashboard = pool.submit(lambda: self.site.test_client().get("/admin/skip"))
                self.assertEqual(presence.result(timeout=3).status_code, 200)
                self.assertEqual(dashboard.result(timeout=3).status_code, 200)
            self.assertEqual(reader.execute("SELECT COUNT(*) FROM skip_presence").fetchone()[0], 0)
        with self.db() as con:
            self.assertEqual(con.execute("SELECT playlist_id FROM skip_presence WHERE device_id=1").fetchone()[0], 1)

    def test_large_catalogue_progress_uses_bounded_database_work(self):
        self.waiting()
        with self.db() as con:
            asset = dict(con.execute("SELECT * FROM skip_assets").fetchone())
            keys = list(asset)
            rows = [tuple((asset | {"asset_key": f"{n:064x}", "episode": n + 1})[k] for k in keys) for n in range(6000)]
            con.executemany("INSERT INTO skip_assets (" + ",".join(keys) + ") VALUES(" + ",".join("?" for k in keys) + ")", rows)
            con.execute("INSERT INTO skip_catalogue_series VALUES(1,'501','{}','sig',0,1,0,0,'ok','')")
            con.executemany("INSERT INTO skip_catalogue_episodes VALUES(1,'501',?,'sig',1)", [(f"{n:064x}",) for n in range(6000)])
        with self.db() as con:
            calls = 0
            def budget():
                nonlocal calls
                calls += 1
                return calls > 2000  # Two million operations; old lookup needs >100 million.
            con.set_progress_handler(budget, 1000)
            result = overview(con)
            con.set_progress_handler(None, 0)
            self.assertEqual(result["totals"]["files"], 6001)
            self.assertEqual(result["totals"]["series"], 1)

    def test_installer_checks_real_dashboard_without_changing_live_markers(self):
        from deploy.check_skip_dashboard import check
        self.waiting()
        record = self.marker()
        with self.db() as con:
            before = tuple(con.execute("SELECT * FROM skip_records WHERE id=?", (record,)).fetchone())
        check(self.db_path, ROOT / "templates")
        with self.db() as con:
            self.assertEqual(tuple(con.execute("SELECT * FROM skip_records WHERE id=?", (record,)).fetchone()), before)

    def test_installer_detects_dashboard_failure_with_healthy_health_endpoint(self):
        from deploy.check_skip_dashboard import check
        with self.db() as con:
            con.execute("DROP TABLE skip_release_settings")
        with self.assertRaises(sqlite3.OperationalError):
            check(self.db_path, ROOT / "templates")


if __name__ == "__main__":
    unittest.main()
