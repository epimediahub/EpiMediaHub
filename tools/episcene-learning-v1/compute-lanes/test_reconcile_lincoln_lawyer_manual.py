"""EpiScene series reconciliation on synthetic customer data only."""
from pathlib import Path
import importlib.util
import sqlite3
import tempfile
import unittest

spec=importlib.util.spec_from_file_location(
    "reconcile_lincoln_lawyer_manual",
    Path(__file__).with_name("reconcile_lincoln_lawyer_manual.py"))
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ReconcileSeriesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"prod.sqlite3"
        with sqlite3.connect(self.db) as db:
            db.executescript("""
                CREATE TABLE skip_records(
                  asset_key TEXT,source TEXT,status TEXT,media_type TEXT,
                  season INTEGER,episode INTEGER,title TEXT,segment_type TEXT,
                  device_id INTEGER,customer_id INTEGER,duration_ms INTEGER,
                  source_key TEXT);
                CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER,
                  season INTEGER,episode INTEGER,title TEXT,duration_ms INTEGER,
                  source_key TEXT);
                CREATE TABLE devices(id INTEGER,customer_id INTEGER,enabled INTEGER);
                CREATE TABLE customers(id INTEGER,enabled INTEGER);
                CREATE TABLE customer_playlists(id INTEGER,customer_id INTEGER);
                INSERT INTO devices VALUES(20,30,1);
                INSERT INTO customers VALUES(30,1),(40,1);
                INSERT INTO customer_playlists VALUES(42,30),(8,40);
                INSERT INTO skip_assets VALUES
                  ('my_a',42,4,1,'The Lincoln Lawyer',2500000,'source-a'),
                  ('analysis_b',8,4,2,'The Lincoln Lawyer',2500000,'source-b');
                INSERT INTO skip_records VALUES
                  ('my_a','device','approved','episode',4,1,'The Lincoln Lawyer',
                   'intro',20,30,2500000,'source-a'),
                  ('my_a','device','pending','episode',4,1,'THE LINCOLN LAWYER',
                   'outro',20,30,2500000,'source-a'),
                  ('missing','device','pending','episode',4,3,'The Lincoln Lawyer',
                   'recap',20,30,2600000,'source-c'),
                  ('analysis_b','device','pending','episode',4,2,'The Lincoln Lawyer',
                   'outro',20,30,2480000,'source-b'),
                  ('my_a','machine','pending','episode',4,1,'The Lincoln Lawyer',
                   'recap',20,30,2500000,'source-a'),
                  ('analysis_b','device','approved','episode',3,2,'The Lincoln Lawyer',
                   'outro',20,30,2500000,'source-b'),
                  ('my_a','device','pending','episode',4,1,'Other secret series',
                   'outro',20,30,2500000,'source-a');
            """)
    
    def tearDown(self):
        self.tmp.cleanup()

    def test_approved_and_pending_normal_playlist_visible_without_identifiers(self):
        with mod.open_readonly(self.db) as con:
            data=mod.analyze(con)
        self.assertEqual(data["matching_title_records"],5)
        self.assertEqual(data["season4_by_location"]["other_registered"]["approved"],1)
        self.assertEqual(data["season4_by_location"]["other_registered"]["pending"],1)
        self.assertEqual(data["season4_by_location"]["unregistered_asset"]["pending_unregistered_media"],1)
        self.assertEqual(data["season4_by_location"]["analysis"]["pending_playlist_owner_mismatch"],1)
        self.assertEqual(data["season4_by_location"]["analysis"]["pending_runtime_mismatch"],1)
        self.assertEqual(data["by_season_status"]["3"]["approved"],1)
        self.assertIn("1",data["season4_episodes"])
        self.assertNotIn("source-a",str(data))
        self.assertNotIn("my_a",str(data))
        self.assertNotIn("Other secret series",str(data))
        self.assertEqual(data["database_writes"],0)

    def test_database_preserved(self):
        before=self.db.read_bytes()
        with mod.open_readonly(self.db) as con:
            mod.analyze(con)
        self.assertEqual(before,self.db.read_bytes())

    def test_missing_file_not_created(self):
        absent=Path(self.tmp.name)/"missing.db"
        with self.assertRaises(ValueError):
            mod.open_readonly(absent)
        self.assertFalse(absent.exists())


if __name__=="__main__":
    unittest.main()
