"""Synthetic ownership and cut-lineage tests, no live customer data."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location(
  "inspect_manual_marker_lineage",Path(__file__).with_name("inspect_manual_marker_lineage.py"))
mod=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class MarkerLineageTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.path=Path(self.dir.name)/"synthetic.db"
        with sqlite3.connect(self.path) as db:
            db.executescript("""
              CREATE TABLE skip_records(
                id INTEGER PRIMARY KEY,asset_key TEXT,device_id INTEGER,customer_id INTEGER,
                source_key TEXT,media_type TEXT,season INTEGER,episode INTEGER,title TEXT,
                duration_ms INTEGER,segment_type TEXT,source TEXT,status TEXT);
              CREATE TABLE skip_assets(
                asset_key TEXT PRIMARY KEY,playlist_id INTEGER,source_key TEXT,
                media_type TEXT,season INTEGER,episode INTEGER,title TEXT,duration_ms INTEGER);
              CREATE TABLE devices(id INTEGER,customer_id INTEGER,enabled INTEGER);
              CREATE TABLE customers(id INTEGER,enabled INTEGER);
              CREATE TABLE customer_playlists(id INTEGER,customer_id INTEGER);
              INSERT INTO customers VALUES(100,1),(101,1);
              INSERT INTO devices VALUES(5,100,1),(6,101,1);
              INSERT INTO customer_playlists VALUES(55,101),(8,100);
              INSERT INTO skip_assets VALUES
                ('a',55,'source-a','episode',4,1,'The Lincoln Lawyer',2500000),
                ('b',8,'source-b','episode',4,2,'Other Secret Show',2300000);
              INSERT INTO skip_records VALUES
                (1,'a',5,100,'source-a','episode',4,1,'The Lincoln Lawyer',2500000,'intro','device','pending'),
                (2,'unregistered',5,100,'source-z','episode',4,2,'The Lincoln Lawyer',2500000,'recap','device','pending'),
                (3,'b',5,100,'source-b','episode',4,2,'Other Secret Show',2300000,'outro','device','pending'),
                (4,'b',5,100,'source-b','episode',4,2,'Other Secret Show',2300000,'intro','device','approved'),
                (5,'a',5,100,'source-a','episode',4,1,'The Lincoln Lawyer',2500000,'intro','machine','pending');
            """)

    def tearDown(self):
        self.dir.cleanup()

    def test_exactly_classifies_source_disagreement(self):
        with mod.read_only(self.path) as conn:
            result=mod.audit(conn)
        self.assertEqual(result["pending_count"],3)
        d=result["by_asset_registration"]
        self.assertEqual(d["other_registered"]["playlist_owner_disagrees_with_record"],1)
        self.assertEqual(d["other_registered"]["device_owner_disagrees_with_playlist_owner"],1)
        self.assertEqual(d["other_registered"].get("device_owner_disagrees_with_record", 0),0)
        self.assertEqual(d["unregistered_asset"]["no_registered_asset"],1)
        self.assertEqual(d["analysis"]["current_ownership_fully_matches"],1)
        self.assertNotIn("Other Secret Show",str(result))
        self.assertNotIn("The Lincoln Lawyer",str(result))
        self.assertNotIn("'100'",str(result))
        self.assertEqual(result["database_writes"],0)
        self.assertEqual(result["provider_requests"],0)

    def test_named_show_reports_only_subset(self):
        with mod.read_only(self.path) as conn:
            result=mod.audit(conn,series="The Lincoln Lawyer")
        self.assertEqual(result["pending_count"],2)
        self.assertEqual(result["scope"],"specific_series")
        self.assertNotIn("Other Secret Show",str(result))

    def test_source_database_remains_unchanged(self):
        before=self.path.read_bytes()
        with mod.read_only(self.path) as conn:
            mod.audit(conn)
        self.assertEqual(self.path.read_bytes(),before)

    def test_no_create_if_missing(self):
        other=Path(self.dir.name)/"missing.db"
        with self.assertRaises(ValueError):
            mod.read_only(other)
        self.assertFalse(other.exists())


if __name__=="__main__":
    unittest.main()
