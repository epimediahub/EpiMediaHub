"""Isolated fixture-only provider expiry to report rows, no live accounts."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from expiry_report_rows import VerifiedPlaylistExpiry, linked_expiries


class ExpiryJoinTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.db=Path(self.dir.name)/"db.sqlite3"
        with sqlite3.connect(self.db) as db:
            db.executescript("""
                CREATE TABLE customers(id INTEGER PRIMARY KEY,name TEXT,enabled INTEGER);
                CREATE TABLE customer_playlists(
                    id INTEGER PRIMARY KEY,customer_id INTEGER,name TEXT,
                    enabled INTEGER,config_json TEXT);
                INSERT INTO customers VALUES(7,'Musterkunde',1);
                INSERT INTO customers VALUES(8,'Deaktiviert',0);
                INSERT INTO customer_playlists VALUES
                    (10,7,'THE BEST',1,'SECRET_CREDENTIALS_NEVER_READ'),
                    (11,7,'4K IPTV',1,'MORE_SECRET_CREDENTIALS_NEVER_READ'),
                    (12,8,'THE BEST',1,'DO_NOT_REPORT'),
                    (13,7,'THE BEST',0,'DISABLED_PRIVATE');
            """)
        self.now=datetime(2026,10,20,13,0,tzinfo=timezone.utc)

    def tearDown(self):
        self.dir.cleanup()

    def seen(self,pid,year,month,day,age_hours=1):
        return VerifiedPlaylistExpiry(pid,date(year,month,day),
                                      self.now-timedelta(hours=age_hours))

    def test_same_customer_multiple_playlist_expiries_and_credentials_hidden(self):
        got=linked_expiries(self.db,[
            self.seen(10,2026,11,18),
            self.seen(11,2026,11,4),
            self.seen(12,2026,11,1),
            self.seen(13,2026,11,2)
        ],self.now)
        self.assertEqual([(r.customer,r.playlist,r.day.isoformat()) for r in got],[
            ("Musterkunde","4K IPTV","2026-11-04"),
            ("Musterkunde","THE BEST","2026-11-18")
        ])
        self.assertNotIn("SECRET_CREDENTIALS_NEVER_READ",repr(got))

    def test_unknown_stale_and_unlinked_expiries_are_excluded(self):
        got=linked_expiries(self.db,[
            self.seen(10,2026,11,18,age_hours=72),
            self.seen(7777,2026,11,4)
        ],self.now)
        self.assertEqual(got,[])

    def test_duplicate_account_observation_fails_closed(self):
        with self.assertRaises(ValueError):
            linked_expiries(self.db,[
                self.seen(10,2026,11,1),self.seen(10,2026,11,2)
            ],self.now)

    def test_unsanitized_values_not_allowed(self):
        with self.assertRaises(ValueError):
            linked_expiries(self.db,[
                VerifiedPlaylistExpiry(10,datetime(2026,11,4),
                                      self.now)
            ],self.now)


if __name__=="__main__":
    unittest.main()
