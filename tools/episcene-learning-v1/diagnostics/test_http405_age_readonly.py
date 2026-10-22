#!/usr/bin/env python3
"""Smoke tests: age/recency attribution never exports details or mutates DB."""
from datetime import datetime, timezone
import json
import sqlite3
import unittest

import http405_age_readonly as m

class AgeCheck(unittest.TestCase):
    def test_recency_and_privacy(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript('''
                CREATE TABLE skip_assets(asset_key TEXT, playlist_id INTEGER);
                CREATE TABLE skip_jobs(asset_key TEXT,status TEXT,detail TEXT,updated_at TEXT);
            ''')
            db.executemany('INSERT INTO skip_assets VALUES (?,?)',[
                ('secretasset',10),('secondasset',10),('other',8),('notanalysis',55)])
            err='Anbieter meldet HTTP 405; eigene Zeitmarken bleiben nutzbar'
            db.executemany('INSERT INTO skip_jobs VALUES (?,?,?,?)',[
                ('secretasset','failed',err,'2026-10-12T12:00:00+00:00'),
                ('secondasset','failed',err,'2026-10-22T17:00:00+00:00'),
                ('other','done','PRIVATE_URL_123','2026-10-22T18:00:00Z'),
                ('notanalysis','failed',err,'2026-10-22T18:00:00Z')])
            r=m.summarize(db,datetime(2026,10,22,18,10,tzinfo=timezone.utc))
            self.assertEqual(r['the_best_405_still_failed_rows'],2)
            self.assertEqual(r['the_best_405_updated_within']['24h'],1)
            self.assertEqual(r['the_best_405_updated_within']['1h'],0)
            self.assertIn('2026-10-12',r['the_best_405_failed_rows_by_local_day'])
            self.assertEqual(r['other_recent_job_updates']['8']['last_24h_by_current_status']['done'],1)
            txt=json.dumps(r)
            for secret in ('secretasset','PRIVATE_URL_123','secondasset'):
                self.assertNotIn(secret,txt)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM skip_jobs').fetchone()[0],4)

    def test_null_and_invalid_dates(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript('CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER);'
                             'CREATE TABLE skip_jobs(asset_key TEXT,status TEXT,detail TEXT,updated_at TEXT);')
            db.execute('INSERT INTO skip_assets VALUES (?,?)',('a',10))
            db.execute("INSERT INTO skip_jobs VALUES ('a','partial','PRIVATE','wrong date')")
            r=m.summarize(db,datetime(2026,10,22,tzinfo=timezone.utc))
            self.assertEqual(r['other_recent_job_updates']['10']['invalid_dates_by_current_status']['partial'],1)

if __name__=='__main__':unittest.main()
