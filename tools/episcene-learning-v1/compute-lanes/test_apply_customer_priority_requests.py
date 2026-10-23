"""EpiScene bounded customer-triggered native priority: synthetic-only tests."""
import hashlib
import importlib.util
import sqlite3
from datetime import datetime,timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location(
    "apply_customer_priority_requests",
    Path(__file__).with_name("apply_customer_priority_requests.py"))
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class PriorityRequestsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name)
        self.db=root/"fixture.sqlite3"
        self.scheduler=root/"schedule.py";self.worker=root/"worker.py"
        self.scheduler.write_text("def select_job(): return 1")
        self.worker.write_text("def process_parallel(): return 1")
        self.paths={"scheduler":self.scheduler,"analysis_worker":self.worker}
        self.digests={key:hashlib.sha256(path.read_bytes()).hexdigest() for key,path in self.paths.items()}
        self.patch=patch.object(mod,"EXPECTED_SHA",self.digests)
        self.patch.start()
        self.now=datetime(2026,10,23,22,tzinfo=timezone.utc)
        with sqlite3.connect(self.db) as c:
            c.executescript("""
            CREATE TABLE skip_customer_marker_provenance(record_id INTEGER,customer_id INTEGER,
                playlist_id INTEGER,account_key TEXT,asset_key TEXT,source_key TEXT,
                media_type TEXT,season INTEGER,episode INTEGER,duration_ms INTEGER);
            CREATE TABLE skip_customer_asset_claims(customer_id INTEGER,playlist_id INTEGER,
                account_key TEXT,asset_key TEXT,source_key TEXT,media_type TEXT,
                season INTEGER,episode INTEGER,duration_ms INTEGER,stream_id TEXT,extension TEXT);
            CREATE TABLE skip_records(id INTEGER,asset_key TEXT,source_key TEXT,media_type TEXT,
                title TEXT,season INTEGER,episode INTEGER,duration_ms INTEGER,
                segment_type TEXT,start_ms INTEGER,end_ms INTEGER,disabled INTEGER,
                status TEXT,source TEXT,device_id INTEGER,customer_id INTEGER,reviewed_at TEXT);
            CREATE TABLE skip_jobs(id INTEGER,asset_key TEXT,status TEXT,attempts INTEGER);
            CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER,title TEXT,
                season INTEGER,episode INTEGER,media_type TEXT,source_key TEXT);
            CREATE TABLE skip_analysis_sources(playlist_id INTEGER,enabled INTEGER);
            CREATE TABLE skip_analysis_playlists(id INTEGER,archived INTEGER);
            CREATE TABLE skip_schedule_requests(playlist_id INTEGER,source_key TEXT,
                season INTEGER,episode INTEGER,reference_asset TEXT,reason TEXT,
                requested_at INTEGER,expires_at INTEGER,PRIMARY KEY(playlist_id,source_key));
            CREATE TABLE devices(id INTEGER,customer_id INTEGER,enabled INTEGER);
            CREATE TABLE customers(id INTEGER,enabled INTEGER);
            CREATE TABLE customer_playlists(id INTEGER,customer_id INTEGER);
            INSERT INTO devices VALUES(1,44,1);
            INSERT INTO customers VALUES(44,1);
            INSERT INTO customer_playlists VALUES(55,44);
            INSERT INTO skip_analysis_sources VALUES(8,1),(10,1);
            INSERT INTO skip_analysis_playlists VALUES(8,0),(10,0);
            INSERT INTO skip_customer_marker_provenance VALUES
                (1,44,55,'account','asset','series','episode',4,1,3200000);
            INSERT INTO skip_customer_asset_claims VALUES
                (44,55,'account','asset','series','episode',4,1,3200000,'1002','mkv');
            INSERT INTO skip_records VALUES
                (1,'asset','series','episode','The Lincoln Lawyer',4,1,3200000,
                 'intro',10000,50000,0,'approved','device',1,44,
                 '2026-10-23T21:30:00Z');
            INSERT INTO skip_assets VALUES
                ('job2',8,'The Lincoln Lawyer',4,2,'episode','analysis-show'),
                ('job3',10,'The Lincoln Lawyer',4,3,'episode','analysis-show-b'),
                ('foreign',55,'The Lincoln Lawyer',4,2,'episode','other'),
                ('older',8,'The Lincoln Lawyer',4,1,'episode','analysis-show');
            INSERT INTO skip_jobs VALUES
                (20,'job2','queued',0),(30,'job3','queued',0),
                (40,'foreign','queued',0),(50,'older','queued',0);
            """)

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def run(self,apply=False):
        return mod.run(apply=apply,database=self.db,paths=self.paths,now=self.now)

    def test_check_does_not_touch_database_or_priorities(self):
        original=self.db.read_bytes()
        r=self.run()
        self.assertEqual(r["priority_requests_proposed"],2)
        self.assertEqual(r["changes_made"],0)
        self.assertEqual(self.db.read_bytes(),original)
        self.assertEqual(r["provider_connections"],0)
        self.assertEqual(r["worker_restarts"],0)

    def test_apply_adds_expiring_native_scheduler_requests(self):
        r=self.run(apply=True)
        self.assertEqual(r["changes_made"],2)
        with sqlite3.connect(self.db) as con:
            saved=con.execute("SELECT playlist_id,reason,reference_asset FROM skip_schedule_requests ORDER BY playlist_id").fetchall()
            self.assertEqual(saved,[(8,"customer_verified",""),(10,"customer_verified","")])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='queued'").fetchone()[0],4)
        self.assertEqual(self.run(apply=True)["changes_made"],0)

    def test_existing_manual_reference_is_never_overwritten(self):
        with sqlite3.connect(self.db) as con:
            con.execute("""INSERT INTO skip_schedule_requests VALUES
                (8,'analysis-show',4,1,'some-reference','reference',1760000000,1980000000)""")
        r=self.run(apply=True)
        self.assertEqual(r["changes_made"],1)
        with sqlite3.connect(self.db) as con:
            existing=con.execute("SELECT reason,reference_asset FROM skip_schedule_requests WHERE playlist_id=8").fetchone()
            self.assertEqual(existing,("reference","some-reference"))

    def test_bad_account_or_disabled_device_gives_no_requests(self):
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE skip_customer_marker_provenance SET account_key='different'")
        self.assertEqual(self.run(apply=True)["changes_made"],0)
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE skip_customer_marker_provenance SET account_key='account'")
            con.execute("UPDATE devices SET enabled=0")
        self.assertEqual(self.run(apply=True)["changes_made"],0)

    def test_run_does_not_approve_disabled_markers(self):
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE skip_records SET disabled=1")
        self.assertEqual(self.run(apply=True)["changes_made"],0)

    def test_job_needs_queued_and_enabled_source(self):
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE skip_jobs SET attempts=3 WHERE id=20")
            con.execute("UPDATE skip_analysis_sources SET enabled=0 WHERE playlist_id=10")
        self.assertEqual(self.run(apply=True)["changes_made"],0)

    def test_worker_digest_change_blocks_any_action(self):
        self.scheduler.write_text("def select_job(): return 2")
        with self.assertRaisesRegex(mod.Stop,"WORKER_VERSION_DRIFT"):
            self.run(apply=True)
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_schedule_requests").fetchone()[0],0)

    def test_missing_db_never_created(self):
        missing=Path(self.temp.name)/"missing.db"
        with self.assertRaises(mod.Stop):
            mod.run(apply=True,database=missing,paths=self.paths,now=self.now)
        self.assertFalse(missing.exists())


if __name__=="__main__":
    unittest.main()
