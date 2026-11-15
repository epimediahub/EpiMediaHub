"""Synthetic full-history key ownership diagnostics, read only."""
from pathlib import Path
import importlib.util
import sqlite3
import tempfile
import unittest

spec=importlib.util.spec_from_file_location(
    "audit_global_registration_lineage",
    Path(__file__).with_name("audit_global_registration_lineage.py"))
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class GlobalProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.db=self.root/"test.db"
        with sqlite3.connect(self.db) as conn:
            conn.executescript("""
            CREATE TABLE skip_records(
                asset_key TEXT,customer_id INTEGER,source TEXT,status TEXT,
                media_type TEXT,title TEXT,season INTEGER,episode INTEGER,
                duration_ms INTEGER,created_at TEXT);
            CREATE TABLE skip_assets(
                asset_key TEXT,playlist_id INTEGER,duration_ms INTEGER,season INTEGER,
                episode INTEGER,updated_at TEXT);
            CREATE TABLE customer_playlists(id INTEGER,customer_id INTEGER);
            INSERT INTO customer_playlists VALUES (42,100),(43,200);
            INSERT INTO skip_assets VALUES
                ('same-key',43,2400000,4,1,'2026-10-23T20:00:00Z'),
                ('key2',43,2600000,4,2,'2026-10-23T20:00:00Z');
            INSERT INTO skip_records VALUES
                ('same-key',100,'device','pending','episode','The Lincoln Lawyer',4,1,3000000,'2026-10-23T18:00:00Z'),
                ('same-key',100,'device','pending','episode','The Lincoln Lawyer',4,1,3000000,'2026-10-23T18:20:00Z'),
                ('same-key',200,'device','approved','episode','Another TV series',3,2,2400000,'2026-10-23T19:00:00Z'),
                ('key2',100,'device','pending','episode','The Lincoln Lawyer',4,2,3000000,'2026-10-23T18:00:00Z');
            """)
        self.code=self.root/"source.py"
        self.code.write_text("""
def add_record():
    SQL = 'INSERT INTO skip_assets(x) VALUES(1) ON CONFLICT(asset_key) DO UPDATE SET playlist_id=excluded.playlist_id'
    SECRET='SENSITIVE TOKEN HERE'
""")

    def tearDown(self):
        self.tmp.cleanup()

    def test_detects_later_registry_drift_and_global_reuse(self):
        original=self.db.read_bytes()
        result=audit.run(self.db,{"skip_markers.py":(self.code,{"add_record"})})
        counts=result["counts"]
        self.assertEqual(counts["candidate_asset_keys"],2)
        self.assertEqual(counts["keys_with_multiple_marker_customer_owners_globally"],1)
        self.assertEqual(counts["keys_where_registered_owner_only_matches_another_historical_marker"],1)
        self.assertEqual(counts["keys_where_registered_owner_is_no_marker_owner"],1)
        self.assertEqual(counts["keys_with_records_from_different_episodes_globally"],1)
        self.assertEqual(counts["registry_timestamp_comparisons_available"],2)
        self.assertEqual(counts["registry_updated_after_earliest_pending"],2)
        self.assertTrue(result["source_structure"]["skip_markers.py"]["target_functions_contain_on_conflict"])
        self.assertTrue(result["source_structure"]["skip_markers.py"]["target_functions_update_playlist_id"])
        self.assertNotIn("SENSITIVE TOKEN",str(result))
        self.assertNotIn("same-key",str(result))
        self.assertEqual(self.db.read_bytes(),original)
        self.assertEqual(result["database_writes"],0)

    def test_missing_db_does_not_create_file(self):
        other=self.root/"absent.db"
        with self.assertRaises(ValueError):
            audit.run(other,{"skip_markers.py":(self.code,{"add_record"})})
        self.assertFalse(other.exists())

    def test_no_raw_sql_or_customer_ids_output(self):
        result=audit.sql_structure(self.code,function_names={"add_record"})
        self.assertTrue(result["sql_or_python_source_exported"] is False)
        self.assertNotIn("200",str(result))
        self.assertNotIn("INSERT INTO",str(result))


if __name__=="__main__":
    unittest.main()
