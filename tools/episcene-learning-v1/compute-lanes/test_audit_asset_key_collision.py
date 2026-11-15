"""Synthetic key-sharing audit: identity/cut mismatch without private data leakage."""
from pathlib import Path
import importlib.util
import sqlite3
import tempfile
import unittest

spec=importlib.util.spec_from_file_location(
  "audit_asset_key_collision",Path(__file__).with_name("audit_asset_key_collision.py"))
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class CollisionAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.database=self.root/"test.sqlite3"
        with sqlite3.connect(self.database) as c:
            c.executescript("""
                CREATE TABLE skip_records(id INTEGER PRIMARY KEY,
                  asset_key TEXT,customer_id INTEGER,source TEXT,status TEXT,
                  media_type TEXT,title TEXT,season INTEGER,episode INTEGER,duration_ms INTEGER);
                CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER,
                  duration_ms INTEGER,season INTEGER,episode INTEGER,source_key TEXT,title TEXT);
                CREATE TABLE customer_playlists(id INTEGER PRIMARY KEY,customer_id INTEGER);
                INSERT INTO customer_playlists VALUES(42,100);
                INSERT INTO skip_assets VALUES
                  ('secret_asset_key',42,3000000,4,1,'source','Super Secret'),
                  ('asset_two',42,3100000,4,2,'source','Super Secret');
                INSERT INTO skip_records VALUES
                  (1,'secret_asset_key',200,'device','pending','episode',
                   'The Lincoln Lawyer',4,1,3500000),
                  (2,'secret_asset_key',200,'device','pending','episode',
                   'The Lincoln Lawyer',4,1,3500000),
                  (3,'secret_asset_key',100,'device','pending','episode',
                   'The Lincoln Lawyer',4,1,3000000),
                  (4,'asset_two',100,'device','approved','episode',
                   'The Lincoln Lawyer',4,2,3100000),
                  (5,'secret_asset_key',200,'device','pending','episode',
                   'Other secret series',4,1,3500000);
            """)
        self.code=self.root/"test.py"
        self.code.write_text("""
def add_record(): pass
def provider_asset_key(): pass
secret = 'password=do-not-output'
q = 'INSERT INTO skip_assets ... ON CONFLICT(asset_key)'
""")

    def tearDown(self):
        self.tmp.cleanup()

    def test_aggregates_repeat_cuts_without_identifiers(self):
        before=self.database.read_bytes()
        result=audit.run(self.database,{"skip_markers.py":self.code})
        counts=result["marker_identity_collisions"]
        self.assertEqual(counts["s4_pending_records"],3)
        self.assertEqual(counts["s4_distinct_asset_keys"],1)
        self.assertEqual(counts["s4_owner_mismatch"],2)
        self.assertEqual(counts["s4_asset_keys_with_multiple_marker_customers"],1)
        self.assertEqual(counts["s4_asset_keys_with_multiple_record_runtimes"],1)
        self.assertEqual(counts["s4_runtime_mismatch_gt_500ms"],2)
        self.assertEqual(self.database.read_bytes(),before)
        self.assertNotIn("secret_asset_key",str(result))
        self.assertNotIn("do-not-output",str(result))
        self.assertNotIn("42",str(result))
        self.assertTrue(result["deployed_code_structure"]["skip_markers.py"]
                        ["sql_mentions_skip_assets"])
        self.assertTrue(result["deployed_code_structure"]["skip_markers.py"]
                        ["sql_mentions_on_conflict"])
        self.assertEqual(result["database_writes"],0)

    def test_no_create_when_missing_db(self):
        with self.assertRaises(ValueError):
            audit.run(self.root/"absent.db",{"skip_markers.py":self.code})
        self.assertFalse((self.root/"absent.db").exists())

    def test_module_source_lines_never_exported(self):
        info=audit.structure(self.code)
        self.assertFalse(info["source_content_exported"])
        self.assertEqual(info["functions_present"],["add_record","provider_asset_key"])
        self.assertNotIn("password",str(info))


if __name__=="__main__":
    unittest.main()
