"""Synthetic tests for redacted failed-service triage; no real journal required."""
from pathlib import Path
import importlib.util
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "diagnose_unified_sync", Path(__file__).with_name("diagnose_unified_sync.py"))
unit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(unit)


class UnifiedSyncDiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.db = self.base / "prod.sqlite3"
        self.feedback = self.base / "feedback.sqlite3"
        self.knowledge = self.base / "knowledge.sqlite3"
        with sqlite3.connect(self.db) as db:
            db.executescript("""
               CREATE TABLE skip_records(asset_key TEXT,source TEXT,status TEXT);
               CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER);
               CREATE TABLE skip_jobs(asset_key TEXT,status TEXT);
               INSERT INTO skip_assets VALUES ('a',8),('b',10),('c',42);
               INSERT INTO skip_records VALUES ('a','device','approved'),
                                               ('c','device','pending');
               INSERT INTO skip_jobs VALUES ('a','queued'),('b','done'),('a','UNEXPECTED_PRIVATE');
            """)
        with sqlite3.connect(self.feedback) as db:
            db.executescript("""
              CREATE TABLE feedback_versions(
                playlist_id INTEGER,active INTEGER,decision TEXT,provenance TEXT);
              INSERT INTO feedback_versions VALUES
                (8,1,'positive','device_authenticated_direct'),
                (42,1,'positive','device_authenticated_direct'),
                (42,1,'positive','unverified_source_status');
            """)
        with sqlite3.connect(self.knowledge) as db:
            db.executescript("""
              CREATE TABLE verified_markers(playlist_id INTEGER);
              INSERT INTO verified_markers VALUES(8),(10);
            """)

    def tearDown(self):
        self.temp.cleanup()

    def test_all_outputs_are_aggregate_and_redacted(self):
        a = unit.db_report(self.db, unit.scan_marker_counts)
        self.assertEqual(a["data"]["other_playlists"]["pending"], 1)
        b = unit.db_report(self.db, unit.scan_job_states)
        self.assertEqual(b["data"]["8"]["unrecognized"], 1)
        self.assertNotIn("UNEXPECTED_PRIVATE", str(b))
        c = unit.db_report(self.feedback, unit.scan_feedback)
        self.assertEqual(c["data"]["other_playlists"]["verified_positive"], 1)
        d = unit.db_report(self.knowledge, unit.scan_knowledge)
        self.assertEqual(d["data"]["analysis"], 2)
        self.assertEqual(d["data"]["other_playlists"], 0)

    def test_journal_exposes_counts_not_secrets(self):
        def fake(args, **kwargs):
            return 0, ("ERROR permission denied password=SECRETPASS\n"
                       "FileNotFoundError private_url=SECRETURL\n"
                       "sqlite3.OperationalError: no such table xyz\n")
        data = unit.journal_error_categories(call=fake)
        self.assertEqual(data["error_categories"]["permission_denied"], 1)
        self.assertEqual(data["error_categories"]["database_schema_mismatch"], 1)
        self.assertFalse(data["raw_logs_exported"])
        self.assertNotIn("SECRETPASS", str(data))
        self.assertNotIn("SECRETURL", str(data))

    def test_service_output_filter(self):
        def fake(args, **kwargs):
            return 0, ("ActiveState=failed\nSubState=failed\nResult=exit-code\n"
                       "ExecMainStatus=1\nEnvironment=PASSWORD_SUPER_SECRET\n")
        r = unit.unit_states(call=fake)
        self.assertEqual(r["episcene-unified-sync.service"]["Result"], "exit-code")
        self.assertEqual(r["episcene-unified-sync.service"]["ExecMainStatus"], 1)
        self.assertNotIn("PASSWORD_SUPER_SECRET", str(r))

    def test_missing_data_never_created(self):
        file = self.base / "missing.db"
        self.assertEqual(unit.db_report(file, unit.scan_knowledge)["state"], "unavailable")
        self.assertFalse(file.exists())


if __name__ == "__main__":
    unittest.main()
