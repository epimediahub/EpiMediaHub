"""Offline tests for sanitized EpiScene 4K probe diagnosis."""
from datetime import datetime,timezone
import sqlite3
import unittest

import diagnose_4k_probe_readonly as mod

class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
          CREATE TABLE skip_analysis_playlists(id INTEGER PRIMARY KEY,
               archived INTEGER, expires_at INTEGER);
          CREATE TABLE skip_analysis_sources(playlist_id INTEGER, enabled INTEGER);
          CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY, playlist_id INTEGER);
          CREATE TABLE skip_jobs(asset_key TEXT, status TEXT, detail TEXT,
               updated_at TEXT);
          INSERT INTO skip_analysis_playlists VALUES(8,0,0),(10,0,0);
          INSERT INTO skip_analysis_sources VALUES(8,1),(10,1);
          INSERT INTO skip_assets VALUES('a',8),('b',8),('c',10),('d',8);
        """)
        self.now=1792749600.0
    def tearDown(self):
        self.db.close()

    def insert(self,key,status,detail,offset):
        moment=datetime.fromtimestamp(self.now+offset,timezone.utc).isoformat()
        self.db.execute('INSERT INTO skip_jobs VALUES (?,?,?,?)',
                        (key,status,detail,moment))

    def test_error_buckets_never_echo_provider_secret(self):
        cases=[
            ('HTTP 401 https://private.example/credentials','HTTP_AUTH_401_403'),
            ('HTTP 405 https://private.example/credentials','HTTP_405_STREAM_METHOD'),
            ('PROXY_HTTP_502 https://private.example/credentials','HTTP_5XX_PROXY_OR_PROVIDER'),
            ('HTTP 429','HTTP_429_RATE_LIMIT'),
            ('ffprobe failed private-url','MEDIA_PROBE_OR_DECODER'),
            ('password MY_SECRET_THIS_IS_NOT_TECHNICAL','OTHER_PRIVATE_ERROR'),
            ('','EMPTY_DETAIL')]
        for value,expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(mod.cause(value),expected)

    def test_recent_failures_are_not_assumed_stall(self):
        self.insert('a','failed','HTTP 403 https://private-source',-240)
        self.insert('b','review','',-60)
        self.insert('c','failed','HTTP 405 SECRET_ITALIAN_PROVIDER',-30)
        self.insert('d','failed','HTTP 405 old SECRET',-14000)
        result=mod.collect(self.db,self.now)
        self.assertEqual(result['recent_failed_count'],1)
        self.assertEqual(result['recent_completed_count'],1)
        self.assertEqual(result['last_completed_age_minutes'],1)
        self.assertEqual(result['recent_failure_categories'],{'HTTP_AUTH_401_403':1})
        self.assertNotIn('SECRET',str(result))
        self.assertNotIn('private-source',str(result))
        self.assertEqual(result['provider_requests'],0)

    def test_no_current_access_does_not_invent_unauthorized(self):
        self.insert('a','failed','unknown private provider detail',-30)
        result=mod.collect(self.db,self.now)
        self.assertEqual(result['last_failure_category'],'OTHER_PRIVATE_ERROR')
        self.assertEqual(result['catalogue_expiry_state'],'UNKNOWN')

    def test_expiry_only_when_in_production_db(self):
        self.db.execute('UPDATE skip_analysis_playlists SET expires_at=? WHERE id=8',
                        (int(self.now)-60,))
        self.assertEqual(mod.collect(self.db,self.now)['catalogue_expiry_state'],'PAST')

if __name__=='__main__':unittest.main()
