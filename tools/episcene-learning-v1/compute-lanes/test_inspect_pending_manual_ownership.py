"""Synthetic pending-marker ownership diagnosis; no real private data."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "inspect_pending_manual_ownership",
    Path(__file__).with_name("inspect_pending_manual_ownership.py"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class PendingManualTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "test.db"
        with sqlite3.connect(self.path) as c:
            c.executescript("""
                CREATE TABLE skip_records (
                   id INTEGER,asset_key TEXT,source TEXT,status TEXT,
                   device_id INTEGER,customer_id INTEGER,source_key TEXT,
                   media_type TEXT,season INTEGER,episode INTEGER,
                   title TEXT,duration_ms INTEGER,segment_type TEXT);
                CREATE TABLE skip_assets(
                   asset_key TEXT,playlist_id INTEGER,source_key TEXT,
                   media_type TEXT,season INTEGER,episode INTEGER,
                   title TEXT,duration_ms INTEGER);
                CREATE TABLE devices(id INTEGER,customer_id INTEGER,enabled INTEGER);
                CREATE TABLE customers(id INTEGER,enabled INTEGER);
                CREATE TABLE customer_playlists(id INTEGER,customer_id INTEGER);
                INSERT INTO customers VALUES (99,1),(88,1);
                INSERT INTO devices VALUES(7,99,1),(8,88,1);
                INSERT INTO customer_playlists VALUES (55,99),(8,99);
                INSERT INTO skip_assets VALUES
                   ('asset_private_a',55,'source-a','episode',4,1,
                    'Super Secret Test Name',2520000),
                   ('asset_private_b',8,'source-a','episode',4,2,
                    'Other Name',2400000);
                INSERT INTO skip_records VALUES
                   (1,'asset_private_a','device','pending',7,99,'source-a',
                    'episode',4,1,'Super Secret Test Name',2520000,'intro'),
                   (2,'asset_private_a','device','pending',8,99,'source-a',
                    'episode',4,1,'Super Secret Test Name',2520000,'outro'),
                   (3,'asset_private_b','device','pending',7,99,'source-a',
                    'episode',4,2,'Other Name',2400000,'recap'),
                   (4,'asset_private_a','machine','pending',7,99,'source-a',
                    'episode',4,1,'Super Secret Test Name',2520000,'intro');
            """)

    def tearDown(self):
        self.tmp.cleanup()

    def test_normal_playlist_marking_seen_without_customer_identifiers(self):
        with audit.ro_db(self.path) as db:
            result = audit.summary(db)
        self.assertEqual(result["status"], "READ_ONLY_SUCCESS")
        self.assertEqual(result["pending_manual"]["other_or_unmapped"]["total"], 2)
        self.assertEqual(result["pending_manual"]["analysis"]["total"], 1)
        self.assertEqual(result["pending_manual"]["other_or_unmapped"]
                         ["all_ownership_checks_pass"], 1)
        self.assertEqual(result["pending_manual"]["other_or_unmapped"]
                         ["device_owner_mismatch"], 1)
        self.assertEqual(result["segment_types"]["other_or_unmapped"],
                         {"intro": 1, "outro": 1})
        self.assertEqual(result["production_writes"], 0)
        self.assertNotIn("Super Secret", str(result))
        self.assertNotIn("asset_private", str(result))
        self.assertNotIn("99", str(result))

    def test_query_is_read_only(self):
        before = self.path.read_bytes()
        with audit.ro_db(self.path) as db:
            audit.summary(db)
        self.assertEqual(before, self.path.read_bytes())

    def test_nonexistent_source_does_not_create_file(self):
        missing = self.root / "absent.db"
        with self.assertRaises(ValueError):
            audit.ro_db(missing)
        self.assertFalse(missing.exists())

    def test_code_fingerprint_contains_no_source(self):
        source = self.root / "handler.py"
        source.write_text("verified_manual_submission = True\\nSECRET = 'Do-not-print'")
        value = audit.source_fingerprints({"manual_handler": source})
        self.assertTrue(value["manual_handler"]["has_manual_authenticator"])
        self.assertNotIn("Do-not-print", str(value))


if __name__ == "__main__":
    unittest.main()
