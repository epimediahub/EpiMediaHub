"""Synthetic post-install diagnostics test; no production database."""
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec=importlib.util.spec_from_file_location("verify_customer_markers_live",
   Path(__file__).with_name("verify_customer_markers_live.py"))
check=importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class MarkerVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.db=self.root/"test.sqlite3"
        with sqlite3.connect(self.db) as db:
            db.executescript("""
                CREATE TABLE skip_customer_asset_claims(
                  customer_id INTEGER,playlist_id INTEGER,asset_key TEXT);
                CREATE TABLE skip_customer_marker_provenance(
                  record_id INTEGER,customer_id INTEGER,playlist_id INTEGER,asset_key TEXT);
                CREATE TABLE skip_records(
                  id INTEGER,status TEXT,source TEXT,device_id INTEGER,customer_id INTEGER);
                INSERT INTO skip_customer_asset_claims VALUES(100,55,'secret-key');
                INSERT INTO skip_customer_marker_provenance VALUES(1,100,55,'secret-key');
                INSERT INTO skip_customer_marker_provenance VALUES(2,100,55,'secret-key');
                INSERT INTO skip_records VALUES(1,'approved','device',6,100);
                INSERT INTO skip_records VALUES(2,'pending','device',6,100);
            """)
        for n in check.EXPECTED:
            (self.root/n).write_bytes(b"synthetic-module")
        self.original=check.EXPECTED.copy()

    def tearDown(self):
        check.EXPECTED.clear()
        check.EXPECTED.update(self.original)
        self.tmp.cleanup()

    def test_no_secrets_or_mutations(self):
        digest=hashlib.sha256(b"synthetic-module").hexdigest()
        check.EXPECTED.update({n:digest for n in check.EXPECTED})
        original=self.db.read_bytes()
        result=check.diagnostic(self.db,self.root,lambda x:True)
        self.assertEqual(result["customer_asset_claims"],1)
        self.assertEqual(result["scoped_marker_provenance_total"],2)
        self.assertEqual(result["scoped_marker_status_counts"],
                         {"approved":1,"pending":1})
        self.assertTrue(result["all_versions_match"])
        self.assertTrue(result["both_services_active"])
        self.assertEqual(result["database_writes"],0)
        self.assertEqual(self.db.read_bytes(),original)
        self.assertNotIn("secret-key",str(result))
        self.assertNotIn("100",str(result))

    def test_component_drift_detected_without_restart(self):
        value=check.diagnostic(self.db,self.root,lambda x:True)
        self.assertFalse(value["all_versions_match"])
        self.assertEqual(value["worker_restarts"],0)

    def test_missing_source_is_not_created(self):
        absent=self.root/"missing.sqlite3"
        with self.assertRaises(ValueError):
            check.diagnostic(absent,self.root,lambda x:True)
        self.assertFalse(absent.exists())


if __name__=="__main__":
    unittest.main()
