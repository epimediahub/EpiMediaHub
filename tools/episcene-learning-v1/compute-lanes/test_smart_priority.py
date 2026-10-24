"""Synthetic tests: no real user database, streams or scheduler writes."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import importlib.util
import sqlite3
import tempfile
import unittest

MOD = Path(__file__).with_name("smart_priority.py")
spec = importlib.util.spec_from_file_location("smart_priority", MOD)
smart = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smart)


class SmartPriorityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.prod_path, self.feedback_path = root / "prod.sqlite3", root / "feedback.sqlite3"
        with sqlite3.connect(self.prod_path) as db:
            db.executescript("""
              CREATE TABLE skip_records(id INTEGER PRIMARY KEY,asset_key TEXT,
                        segment_type TEXT,status TEXT);
              CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER,
                        title TEXT,season INTEGER,episode INTEGER,media_type TEXT);
              CREATE TABLE skip_jobs(id INTEGER PRIMARY KEY,asset_key TEXT,status TEXT);
              INSERT INTO skip_assets VALUES
                ('manual',55,'The Lincoln Lawyer',4,1,'episode'),
                ('a2',8,'The Lincoln Lawyer',4,2,'episode'),
                ('a3',8,'The Lincoln Lawyer',4,3,'episode'),
                ('a4',10,'The Lincoln Lawyer',4,2,'episode'),
                ('other',8,'A different series',4,2,'episode'),
                ('old',8,'The Lincoln Lawyer',4,4,'episode');
              INSERT INTO skip_records VALUES(1,'manual','intro','approved');
              INSERT INTO skip_jobs VALUES
                (11,'a2','queued'),(12,'a3','queued'),(13,'a4','queued'),
                (14,'other','queued'),(15,'old','done');
            """)
        with sqlite3.connect(self.feedback_path) as db:
            db.executescript("""
                CREATE TABLE feedback_versions (
                  marker_id INTEGER, asset_key TEXT, playlist_id INTEGER,
                  season INTEGER, episode INTEGER, kind TEXT, decision TEXT,
                  active INTEGER, reviewed_at TEXT, provenance TEXT
                );
            """)
            db.execute("INSERT INTO feedback_versions VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (1, "manual", 55, 4, 1, "intro", "positive", 1,
                        "2026-10-23T10:00:00+00:00",
                        "device_authenticated_direct"))
        self.now = datetime(2026, 10, 23, 11, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def execute(self):
        with smart.connect_readonly(self.prod_path) as prod, \
                smart.connect_readonly(self.feedback_path) as feedback:
            return smart.proposals(prod, feedback, now=self.now)

    def test_manual_on_nonanalysis_playlist_prioritizes_only_queued_analysis(self):
        value = self.execute()
        self.assertEqual([x["job_id"] for x in value["candidate_jobs"]], [11, 13, 12])
        self.assertEqual({x["playlist_id"] for x in value["candidate_jobs"]}, {8, 10})
        self.assertEqual(value["queue_mutations"], 0)
        self.assertEqual(value["analysis_streams_opened"], 0)
        with sqlite3.connect(self.prod_path) as db:
            self.assertEqual(db.execute("SELECT status FROM skip_jobs WHERE id=11").fetchone()[0], "queued")

    def test_unapproved_origin_never_triggers_priority(self):
        with sqlite3.connect(self.prod_path) as db:
            db.execute("UPDATE skip_records SET status='pending' WHERE id=1")
        self.assertEqual(self.execute()["candidate_jobs"], [])

    def test_stale_or_revoked_feedback_does_not_trigger_priority(self):
        with sqlite3.connect(self.feedback_path) as db:
            db.execute("UPDATE feedback_versions SET active=0")
        self.assertEqual(self.execute()["candidate_jobs"], [])
        with sqlite3.connect(self.feedback_path) as db:
            db.execute("UPDATE feedback_versions SET active=1,reviewed_at=?",
                       ((self.now-timedelta(days=31)).isoformat(),))
        self.assertEqual(self.execute()["candidate_jobs"], [])

    def test_untrusted_claim_does_not_trigger_priority(self):
        with sqlite3.connect(self.feedback_path) as db:
            db.execute("UPDATE feedback_versions SET provenance='unverified_source_status'")
        self.assertEqual(self.execute()["candidate_jobs"], [])

    def test_limits_fail_closed(self):
        with smart.connect_readonly(self.prod_path) as prod, \
                smart.connect_readonly(self.feedback_path) as feedback:
            with self.assertRaises(ValueError):
                smart.proposals(prod, feedback, now=self.now, max_per_playlist=3)
        with smart.connect_readonly(self.prod_path) as prod, \
                smart.connect_readonly(self.feedback_path) as feedback:
            with self.assertRaises(ValueError):
                smart.proposals(prod, feedback, now=self.now, max_distance=9)


if __name__ == "__main__":
    unittest.main()
