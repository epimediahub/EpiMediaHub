import sqlite3
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from report_saved_jobs_v24 import report

NOW=datetime(2026,10,22,10,0,tzinfo=timezone.utc)

class TestLiveReporting(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.db=Path(t.name)/'db.sqlite3'
        with sqlite3.connect(self.db) as db:
            db.executescript('''CREATE TABLE skip_assets (asset_key TEXT,playlist_id INTEGER);
            CREATE TABLE skip_jobs (id INTEGER PRIMARY KEY,asset_key TEXT,status TEXT,
            detail TEXT,attempts INTEGER,updated_at TEXT);''')
            db.executemany('INSERT INTO skip_assets VALUES (?,?)',
                [('a',8),('b',10),('client',55)])
            db.executemany('INSERT INTO skip_jobs VALUES (?,?,?,?,?,?)',[
                (1,'a','done','EpiScene Knowledge First: intro aus introdb wiederverwendet',1,'2026-10-22T09:00:00'),
                (2,'b','done','EpiScene Knowledge First: outro aus own wiederverwendet',1,'2026-10-22T09:01:00'),
                (3,'a','done','EpiScene Knowledge First: recap aus theintrodb wiederverwendet',1,'2026-10-22T09:01:00'),
                (4,'client','done','EpiScene Knowledge First: intro aus own wiederverwendet',1,'2026-10-22T09:00:00'),
                (5,'b','review','EpiScene Knowledge First: intro aus introdb wiederverwendet',1,'2026-10-22T09:00:00'),
                (6,'a','done','EpiScene Knowledge First: intro aus introdb wiederverwendet',1,'2026-10-01T09:00:00'),
                (7,'a','done','EpiScene Knowledge First: outro aus evil wiederverwendet',1,'2026-10-22T09:00:00'),
            ])

    def test_real_worker_schema_without_kind_is_supported(self):
        before=self.db.read_bytes()
        x=report(self.db,hours=24,current=NOW)
        self.assertEqual(x['status'],'MEASURED')
        self.assertEqual(x['confirmed_completed_reuses'],3)
        self.assertEqual(x['by_playlist']['8']['intro']['introdb'],1)
        self.assertEqual(x['by_playlist']['10']['outro']['own'],1)
        self.assertEqual(x['by_playlist']['8']['recap']['theintrodb'],1)
        self.assertEqual(self.db.read_bytes(),before)

    def test_fails_closed_if_required_columns_missing(self):
        with sqlite3.connect(self.db) as db:
            db.execute('ALTER TABLE skip_jobs RENAME TO old_jobs')
        self.assertEqual(report(self.db,current=NOW)['status'],'STOP_UNEXPECTED_SCHEMA')

    def test_fresh_work_with_no_completed_jobs_is_not_false_positive(self):
        self.assertEqual(report(self.db,hours=1,current=datetime(2026,10,22,15,tzinfo=timezone.utc))['confirmed_completed_reuses'],0)

    def test_wrong_customer_playlist_is_not_counted_even_with_valid_detail(self):
        with sqlite3.connect(self.db) as db:
            db.execute("DELETE FROM skip_jobs WHERE asset_key!='client'")
        self.assertEqual(report(self.db,current=NOW)['confirmed_completed_reuses'],0)

if __name__ == '__main__': unittest.main()
