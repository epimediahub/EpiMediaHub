"""Synthetic preflight checks: no real server files or credentials used."""
from pathlib import Path
import hashlib
import importlib.util
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "readonly_server_snapshot", Path(__file__).with_name("readonly_server_snapshot.py"))
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class ReadonlyServerSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.db = self.folder / "prod.sqlite3"
        self.fb = self.folder / "feedback.sqlite3"
        with sqlite3.connect(self.db) as con:
            con.executescript("""
              CREATE TABLE skip_assets (
                asset_key TEXT PRIMARY KEY,playlist_id INTEGER
              );
              CREATE TABLE skip_jobs(
                asset_key TEXT,status TEXT,updated_at TEXT
              );
              CREATE TABLE skip_records(
                asset_key TEXT,source TEXT,status TEXT
              );
              INSERT INTO skip_assets VALUES
                ('p8',8),('p10',10),('customer',42);
              INSERT INTO skip_jobs VALUES
                ('p8','queued','2026-10-23T19:00:00+00:00'),
                ('p10','done','2026-10-23T19:00:00+00:00'),
                ('customer','queued','2026-10-23T19:00:00+00:00');
              INSERT INTO skip_records VALUES
                ('customer','device','approved'),('p8','device','pending');
            """)
        with sqlite3.connect(self.fb) as con:
            con.executescript("""
              CREATE TABLE feedback_versions(
                decision TEXT,active INTEGER,provenance TEXT,playlist_id INTEGER
              );
              INSERT INTO feedback_versions VALUES
                ('positive',1,'device_authenticated_direct',42),
                ('positive',1,'unverified_source_status',8);
            """)

    def tearDown(self):
        self.tmp.cleanup()

    def test_aggregate_excludes_customer_job_and_names(self):
        value = snapshot.db_snapshot(self.db, snapshot.aggregate_jobs)
        self.assertEqual(value["state"], "ok")
        self.assertEqual(value["data"]["8"]["counts"]["queued"], 1)
        self.assertEqual(value["data"]["10"]["counts"]["done"], 1)
        self.assertNotIn("42", str(value))

    def test_feedback_from_nonanalysis_source_is_counted(self):
        feedback = snapshot.db_snapshot(self.fb, snapshot.feedback_aggregate)
        self.assertEqual(feedback["data"]["other_playlists"], 1)
        self.assertNotIn("analysis", feedback["data"])

    def test_manual_summaries_are_aggregated(self):
        value = snapshot.db_snapshot(self.db, snapshot.manual_feedback_aggregate)
        self.assertEqual(value["data"]["other_playlists"]["approved"], 1)
        self.assertEqual(value["data"]["analysis"]["pending"], 1)

    def test_only_allowlisted_files_and_hash_no_source(self):
        file = self.folder / "worker.py"
        raw = "API_TOKEN = 'synthetic-fake-secret'\ndef work(): return 1\n"
        file.write_text(raw)
        out = snapshot.module_snapshot({"worker": file})
        self.assertEqual(out["worker"]["sha256"],
                         hashlib.sha256(raw.encode()).hexdigest())
        self.assertNotIn("synthetic-fake-secret", str(out))

    def test_symlink_not_read(self):
        original = self.folder / "source.py"
        original.write_text("def run(): return 1")
        link = self.folder / "link.py"
        link.symlink_to(original)
        self.assertEqual(snapshot.module_snapshot({"worker": link})["worker"]["state"],
                         "missing_or_symlink")

    def test_service_parser_filters_arbitrary_output(self):
        def fake(args):
            return "ActiveState=active\nSubState=running\nUnitFileState=enabled\nEnvironment=PASSWORD=SECRET\n"
        states = snapshot.services_snapshot(("worker.service",), call=fake)
        self.assertEqual(states["worker.service"],
                         {"ActiveState": "active", "SubState": "running",
                          "UnitFileState": "enabled"})
        self.assertNotIn("PASSWORD", str(states))

    def test_missing_database_does_not_create_it(self):
        absent = self.folder / "absent.db"
        value = snapshot.db_snapshot(absent, snapshot.aggregate_jobs)
        self.assertEqual(value["state"], "unavailable")
        self.assertFalse(absent.exists())


if __name__ == "__main__":
    unittest.main()
