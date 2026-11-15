"""Synthetic scoped customer smart-priority tests. No network or worker writes."""
from pathlib import Path
import importlib.util
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

spec=importlib.util.spec_from_file_location(
    "scoped_customer_priority",Path(__file__).with_name("scoped_customer_priority.py"))
priority=importlib.util.module_from_spec(spec)
spec.loader.exec_module(priority)


class CustomerPriorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"synthetic.db"
        with sqlite3.connect(self.path) as c:
            c.executescript("""
                CREATE TABLE skip_customer_marker_provenance(
                  record_id INTEGER, customer_id INTEGER, playlist_id INTEGER,
                  account_key TEXT, asset_key TEXT, source_key TEXT,
                  media_type TEXT, season INTEGER, episode INTEGER,duration_ms INTEGER);
                CREATE TABLE skip_customer_asset_claims(
                  customer_id INTEGER,playlist_id INTEGER,account_key TEXT,
                  asset_key TEXT,source_key TEXT,media_type TEXT,season INTEGER,
                  episode INTEGER,duration_ms INTEGER,stream_id TEXT,extension TEXT);
                CREATE TABLE skip_records(
                  id INTEGER PRIMARY KEY,asset_key TEXT,source_key TEXT,media_type TEXT,
                  title TEXT,season INTEGER,episode INTEGER,duration_ms INTEGER,
                  segment_type TEXT,start_ms INTEGER,end_ms INTEGER,disabled INTEGER,
                  status TEXT,source TEXT,device_id INTEGER,customer_id INTEGER,
                  reviewed_at TEXT);
                CREATE TABLE devices(id INTEGER,customer_id INTEGER,enabled INTEGER);
                CREATE TABLE customers(id INTEGER,enabled INTEGER);
                CREATE TABLE customer_playlists(id INTEGER,customer_id INTEGER);
                CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER,
                    title TEXT,season INTEGER,episode INTEGER,media_type TEXT);
                CREATE TABLE skip_jobs(id INTEGER,asset_key TEXT,status TEXT);
                INSERT INTO customers VALUES(100,1),(200,1);
                INSERT INTO devices VALUES(9,100,1),(10,200,1);
                INSERT INTO customer_playlists VALUES(55,100),(77,200);
                INSERT INTO skip_customer_asset_claims VALUES
                    (100,55,'account-A','customer1','show1','episode',4,1,3000000,'10007','mkv');
                INSERT INTO skip_customer_marker_provenance VALUES
                    (1,100,55,'account-A','customer1','show1','episode',4,1,3000000);
                INSERT INTO skip_records VALUES
                    (1,'customer1','show1','episode','The Lincoln Lawyer',4,1,3000000,
                     'intro',10000,65000,0,'approved','device',9,100,
                     '2026-10-23T20:00:00+00:00');
                INSERT INTO skip_assets VALUES
                  ('analysis8-2',8,'The Lincoln Lawyer',4,2,'episode'),
                  ('analysis8-3',8,'The Lincoln Lawyer',4,3,'episode'),
                  ('analysis10-2',10,'The Lincoln Lawyer',4,2,'episode'),
                  ('analysis10-other',10,'Another series',4,3,'episode'),
                  ('done',10,'The Lincoln Lawyer',4,3,'episode');
                INSERT INTO skip_jobs VALUES
                  (1001,'analysis8-2','queued'),(1002,'analysis8-3','queued'),
                  (1003,'analysis10-2','queued'),
                  (1004,'analysis10-other','queued'),
                  (1005,'done','done');
            """)
        self.now=datetime(2026,10,23,21,tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def fetch(self):
        with priority.read_only(self.path) as db:
            return priority.propose(db,now=self.now)

    def test_customer_mark_recommends_next_episodes_without_another_stream(self):
        before=self.path.read_bytes()
        result=self.fetch()
        self.assertEqual(result["eligible_scoped_approved_markers"],1)
        self.assertEqual([x["job_id"] for x in result["candidate_jobs"]],
                         [1001,1003,1002])
        self.assertEqual(result["queue_mutations"],0)
        self.assertEqual(result["provider_connections"],0)
        self.assertFalse(result["production_scheduler_hook_enabled"])
        self.assertEqual(before,self.path.read_bytes())

    def test_inconsistent_playlist_account_excluded(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE skip_customer_marker_provenance SET account_key='wrong'")
        self.assertEqual(self.fetch()["candidate_jobs"],[])

    def test_unapproved_disabled_or_foreign_owner_excluded(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE skip_records SET status='pending'")
        self.assertEqual(self.fetch()["candidate_jobs"],[])
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE skip_records SET status='approved',disabled=1")
        self.assertEqual(self.fetch()["candidate_jobs"],[])
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE skip_records SET disabled=0,customer_id=200")
        self.assertEqual(self.fetch()["candidate_jobs"],[])

    def test_wrong_episode_runtime_cut_or_disabled_device_excluded(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE skip_records SET duration_ms=3100000")
        self.assertEqual(self.fetch()["candidate_jobs"],[])
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE skip_records SET duration_ms=3000000")
            db.execute("UPDATE devices SET enabled=0 WHERE id=9")
        self.assertEqual(self.fetch()["candidate_jobs"],[])

    def test_no_database_creation_or_new_connection(self):
        missing=Path(self.tmp.name)/"missing.db"
        with self.assertRaises(RuntimeError):
            priority.read_only(missing)
        self.assertFalse(missing.exists())


if __name__=="__main__":
    unittest.main()
