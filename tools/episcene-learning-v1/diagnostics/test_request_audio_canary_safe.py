"""Offline SQLite tests for guarded EpiScene recovery scheduling."""
from hashlib import sha256
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import request_audio_canary_safe as target


def db():
    con=sqlite3.connect(':memory:')
    con.row_factory=sqlite3.Row
    con.executescript("""
      CREATE TABLE episcene_audio_cache_canary_v1(asset_key TEXT,playlist_id INTEGER,queued_at TEXT);
      CREATE TABLE skip_jobs(id INTEGER,asset_key TEXT,status TEXT,attempts INTEGER);
      CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER,source_key TEXT,season INTEGER,episode INTEGER,media_type TEXT);
      CREATE TABLE skip_analysis_sources(playlist_id INTEGER,enabled INTEGER);
      CREATE TABLE skip_analysis_playlists(id INTEGER,archived INTEGER);
      CREATE TABLE skip_auto_settings(playlist_id INTEGER,enabled INTEGER);
      CREATE TABLE skip_schedule_requests(playlist_id INTEGER,source_key TEXT,season INTEGER,episode INTEGER,
          reference_asset TEXT,reason TEXT,requested_at INTEGER,expires_at INTEGER,
          UNIQUE(playlist_id,source_key));
    """)
    con.execute("INSERT INTO episcene_audio_cache_canary_v1 VALUES('key',8,'2026-11-03')")
    con.execute("INSERT INTO skip_jobs VALUES(1,'key','queued',0)")
    con.execute("INSERT INTO skip_assets VALUES('key',8,'series',1,4,'episode')")
    con.execute("INSERT INTO skip_analysis_sources VALUES(8,1)")
    con.execute("INSERT INTO skip_analysis_playlists VALUES(8,0)")
    con.execute("INSERT INTO skip_auto_settings VALUES(8,1)")
    con.commit()
    return con


class RecoveryRequestTests(unittest.TestCase):
    def test_strictly_one_request_and_does_not_touch_jobs(self):
        c=db()
        target.check_schema(c)
        row=target.canary(c)
        target.insert_request(c,row,123)
        self.assertEqual(c.execute('SELECT COUNT(*) FROM skip_schedule_requests').fetchone()[0],1)
        self.assertEqual(c.execute('SELECT status FROM skip_jobs').fetchone()[0],'queued')
        with self.assertRaisesRegex(RuntimeError,'exists'):
            target.canary(c)
        c.close()

    def test_expired_manual_learning_row_is_retired_only_in_transaction(self):
        c=db()
        c.execute("""INSERT INTO skip_schedule_requests VALUES(8,'series',1,4,'','manual_learning',1,1000)""")
        row=target.canary(c)
        self.assertEqual(target.clear_expired_manual_request(c,row,2000),1)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM skip_schedule_requests").fetchone()[0],0)
        target.insert_request(c,row,2000)
        self.assertEqual(c.execute("SELECT reason FROM skip_schedule_requests").fetchone()[0],
                         target.REASON)
        c.rollback()
        self.assertEqual(c.execute("SELECT reason FROM skip_schedule_requests").fetchone()[0],
                         'manual_learning')
        c.close()

    def test_active_manual_learning_row_remains_untouched(self):
        c=db()
        c.execute("""INSERT INTO skip_schedule_requests VALUES(8,'series',1,4,'','manual_learning',1,9999999999)""")
        with self.assertRaisesRegex(RuntimeError,'request exists'):
            target.canary(c)
        self.assertEqual(c.execute("SELECT reason FROM skip_schedule_requests").fetchone()[0],
                         'manual_learning')
        c.close()

    def test_expired_reference_request_is_not_retired(self):
        c=db()
        c.execute("""INSERT INTO skip_schedule_requests VALUES(8,'series',1,4,'key','reference',1,1000)""")
        with self.assertRaisesRegex(RuntimeError,'request exists'):
            target.canary(c)
        self.assertEqual(c.execute("SELECT reason FROM skip_schedule_requests").fetchone()[0],
                         'reference')
        c.close()

    def test_refuse_missing_scheduler_constraints(self):
        c=db()
        c.execute("UPDATE skip_analysis_sources SET enabled=0")
        with self.assertRaisesRegex(RuntimeError,'no longer enabled'):
            target.canary(c)
        c.close()

    def test_refuse_displaced_request_and_wrong_job(self):
        c=db()
        selected=lambda con,pid,stage,parallel: ({'asset_key':'key'},'')
        with self.assertRaisesRegex(RuntimeError,'higher-priority'):
            target.validate_selected(c,lambda con,stage:[
                {'playlist_id':8,'reason':'reference'}],selected,'key')
        with self.assertRaisesRegex(RuntimeError,'exact German canary'):
            target.validate_selected(c,lambda con,stage:[
                {'playlist_id':8,'reason':target.REASON}],
                lambda *args,**kwargs:({'asset_key':'other'},''),'key')
        c.close()

    def test_safe_scheduler_source_compiler(self):
        source = """def requests(con, stage):
    return con.execute('SELECT 1',()).fetchall()
def select_job(con, playlist_id, excluded=(), *, stage=None, parallel=False):
    return con.execute('SELECT 1',()).fetchone(), ''
"""
        with tempfile.TemporaryDirectory() as folder:
            f=Path(folder)/'skip_schedule.py'
            f.write_text(source)
            with patch.object(target,'SOURCE',f), patch.object(
                    target,'EXPECTED_SCHEDULER_SHA16',sha256(source.encode()).hexdigest()[:16]):
                sha,requester,selector=target.code_selector()
                self.assertEqual(len(sha),16)
                self.assertEqual(len(requester(sqlite3.connect(':memory:'),2)),1)
            unsafe=source.replace('SELECT 1','DELETE FROM skip_jobs')
            f.write_text(unsafe)
            with patch.object(target,'SOURCE',f), patch.object(
                    target,'EXPECTED_SCHEDULER_SHA16',sha256(unsafe.encode()).hexdigest()[:16]):
                with self.assertRaisesRegex(RuntimeError,'SQL modification'):
                    target.code_selector()


if __name__=='__main__':
    unittest.main()
