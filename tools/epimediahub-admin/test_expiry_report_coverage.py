"""Synthetic private expiry coverage tests, no provider/network contact."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from expiry_cache import save_verified
from expiry_report_coverage import preview, CoveragePreviewUnavailable
from expiry_report_rows import VerifiedPlaylistExpiry


class CoveragePreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.db=self.base/"provisioning.db"
        self.cache=self.base/"admin-mobile"/"expiry-cache.sqlite3"
        self.now=datetime(2026,10,20,17,0,tzinfo=timezone.utc)
        with sqlite3.connect(self.db) as con:
            con.executescript("""
                CREATE TABLE customers(id INTEGER PRIMARY KEY,
                    name TEXT, enabled INTEGER, reseller_id INTEGER);
                CREATE TABLE customer_playlists(id INTEGER PRIMARY KEY,
                    customer_id INTEGER,name TEXT,enabled INTEGER,config_json TEXT);
                INSERT INTO customers VALUES
                    (1,'Kunde Beta',1,NULL),
                    (2,'Kunde Alpha',1,77),
                    (3,'Deaktiviert',0,77);
                INSERT INTO customer_playlists VALUES
                    (11,1,'THE BEST',1,'SUPER_PRIVATE_CREDENTIALS'),
                    (12,2,'THE BEST',1,'OTHER_PRIVATE_SECRET'),
                    (13,2,'4K IPTV',1,'PRIVATE_THIRD'),
                    (14,3,'THE BEST',1,'SHOULD_NOT_REPORT'),
                    (15,1,'THE BEST',0,'SHOULD_NOT_REPORT');
            """)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_cache_marks_all_unknown_and_no_false_zero_expiries(self):
        result=preview(self.db,self.cache,self.now)
        self.assertEqual(result["active_accounts"],3)
        self.assertEqual(result["confirmed_accounts"],0)
        self.assertEqual(result["unverified_accounts"],3)
        self.assertFalse(result["snapshot_complete"])
        self.assertEqual(result["network_requests"],0)
        self.assertTrue(all(item["status"]=="unverified"
                            for group in result["playlists"] for item in group["entries"]))
        self.assertNotIn("PRIVATE_",str(result))

    def test_partial_coverage_keeps_known_dates_and_unknown_accounts_visible(self):
        save_verified(self.cache,[
            VerifiedPlaylistExpiry(12,date(2026,11,22),self.now),
            VerifiedPlaylistExpiry(13,date(2026,10,21),
                                   self.now-timedelta(hours=70)),
        ])
        result=preview(self.db,self.cache,self.now)
        self.assertEqual(result["confirmed_accounts"],1)
        self.assertEqual(result["unverified_accounts"],2)
        self.assertEqual([x["name"] for x in result["playlists"]],
                         ["4K IPTV","THE BEST"])
        items=result["playlists"][1]["entries"]
        self.assertEqual(items[0]["customer"],"Kunde Alpha")
        self.assertEqual(items[0]["expires_on"],"2026-11-22")
        self.assertEqual(items[1]["customer"],"Kunde Beta")
        self.assertIsNone(items[1]["expires_on"])
        self.assertFalse(result["snapshot_complete"])

    def test_private_cache_symlink_rejected(self):
        self.cache.parent.mkdir(mode=0o700)
        self.cache.symlink_to(self.db)
        with self.assertRaises(CoveragePreviewUnavailable):
            preview(self.db,self.cache,self.now)

    def test_complete_only_when_every_active_account_is_fresh(self):
        save_verified(self.cache,[
            VerifiedPlaylistExpiry(11,date(2026,10,25),self.now),
            VerifiedPlaylistExpiry(12,date(2026,11,10),self.now),
            VerifiedPlaylistExpiry(13,date(2026,12,20),self.now),
        ])
        result=preview(self.db,self.cache,self.now)
        self.assertEqual(result["confirmed_accounts"],3)
        self.assertTrue(result["snapshot_complete"])

    def test_missing_database_and_invalid_clock_fail_closed(self):
        with self.assertRaises(CoveragePreviewUnavailable):
            preview(self.db.with_name("missing"),self.cache,self.now)
        with self.assertRaises(CoveragePreviewUnavailable):
            preview(self.db,self.cache,self.now.replace(tzinfo=None))


if __name__=="__main__":
    unittest.main()
