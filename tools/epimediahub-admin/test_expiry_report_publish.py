"""Pure fixture test for report publication; no real FCM or provider calls."""
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from zoneinfo import ZoneInfo

from expiry_cache import save_verified, Unavailable
from expiry_report_rows import VerifiedPlaylistExpiry
from expiry_report_publish import publish_once

BERLIN=ZoneInfo("Europe/Berlin")

class DummyRegistry:
    def __init__(self): self.events=[]
    def enqueue(self,events,now): self.events.extend(events)


class ExpiryPublisherTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.db=self.base/"provisioning.db"
        with sqlite3.connect(self.db) as db:
            db.executescript("""
                CREATE TABLE customers(id INTEGER PRIMARY KEY,
                    name TEXT,enabled INTEGER,reseller_id INTEGER);
                CREATE TABLE customer_playlists(id INTEGER PRIMARY KEY,
                    customer_id INTEGER,name TEXT,enabled INTEGER,config_json TEXT);
                INSERT INTO customers VALUES(1,'Muster Name',1,NULL);
                INSERT INTO customer_playlists VALUES(
                    6,1,'4K IPTV',1,'{"type":"XTREAM","xtream_password":"PASSWORD_SHOULD_NOT_APPEAR"}');
            """)
        self.now=datetime(2026,11,30,8,0,tzinfo=BERLIN)
        obs=VerifiedPlaylistExpiry(
            6,date(2026,12,9),self.now.astimezone(timezone.utc)
        )
        save_verified(self.base/"admin-mobile"/"expiry-cache.sqlite3",[obs])
        self.dummy=DummyRegistry()

    def tearDown(self): self.tmp.cleanup()

    def test_last_day_monday_produces_monthly_and_weekly_once_per_period(self):
        result=publish_once(self.base,self.db,self.now,
                            certified_source=True,registry=self.dummy)
        self.assertEqual(result["published"],["month:2026-12","week:2026-11-30"])
        self.assertEqual(set(result["queued_notification_kinds"]),
                         {"expiry_monthly","expiry_weekly"})
        path=self.base/"admin-mobile"/"expiry-reports"/"expiry-2026-12.pdf"
        self.assertTrue(path.read_bytes().startswith(b"%PDF-"))
        self.assertEqual(path.stat().st_mode & 0o077,0)
        first_hash=__import__("hashlib").sha256(path.read_bytes()).hexdigest()
        publish_once(self.base,self.db,self.now,
                     certified_source=True,registry=self.dummy)
        self.assertEqual(__import__("hashlib").sha256(path.read_bytes()).hexdigest(),
                         first_hash)
        self.assertEqual(self.dummy.events[:2],self.dummy.events[2:])
        self.assertFalse(any("Muster Name" in str(e) or "PASSWORD" in str(e)
                             for e in self.dummy.events))

    def test_not_enabled_or_not_due_fails_closed(self):
        with self.assertRaises(Unavailable):
            publish_once(self.base,self.db,self.now,certified_source=False,
                         registry=self.dummy)
        result=publish_once(self.base,self.db,
            self.now+timedelta(days=1),certified_source=True,registry=self.dummy)
        self.assertEqual(result["published"],[])
        self.assertEqual(self.dummy.events,[])

    def test_partial_refresh_never_publishes_or_sends_push(self):
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO customer_playlists VALUES(7,1,'THE BEST',1,?)",
                       ('{"type":"XTREAM"}',))
        with self.assertRaises(Unavailable):
            publish_once(self.base,self.db,self.now,
                         certified_source=True,registry=self.dummy)
        self.assertEqual(self.dummy.events,[])
        self.assertFalse((self.base/"admin-mobile"/"expiry-reports"
                          /"expiry-2026-12.pdf").exists())

    def test_before_daily_refresh_not_published(self):
        early=self.now.replace(hour=6,minute=30)
        result=publish_once(self.base,self.db,early,
                            certified_source=True,registry=self.dummy)
        self.assertEqual(result["published"],[])
        self.assertEqual(self.dummy.events,[])


if __name__=="__main__":
    unittest.main()
