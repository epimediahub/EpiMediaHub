"""Offline SQLite integration tests for limited EpiScene audio recovery canary."""
import contextlib
import io
import json
import sqlite3
import unittest
from audio_recovery_canary import execute, verify_schema


def testdb():
    con=sqlite3.connect(':memory:')
    con.row_factory=sqlite3.Row
    for query in [
        'CREATE TABLE skip_records(id INTEGER PRIMARY KEY,asset_key TEXT,source TEXT,status TEXT,segment_type TEXT,season INTEGER,episode INTEGER,source_key TEXT,media_type TEXT,duration_ms INTEGER,disabled INTEGER)',
        'CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER,source_key TEXT,season INTEGER,episode INTEGER,media_type TEXT,duration_ms INTEGER)',
        'CREATE TABLE skip_auto_evidence(record_id INTEGER,evidence_json TEXT,human_review INTEGER)',
        'CREATE TABLE skip_auto_windows(asset_key TEXT,kind TEXT)',
        'CREATE TABLE skip_jobs(id INTEGER PRIMARY KEY,asset_key TEXT,status TEXT,attempts INTEGER,detail TEXT,updated_at TEXT)',
        'CREATE TABLE skip_analysis_sources(playlist_id INTEGER,enabled INTEGER)',
        'CREATE TABLE skip_analysis_playlists(id INTEGER,archived INTEGER,enabled INTEGER,active INTEGER,paused INTEGER)',
        'CREATE TABLE skip_auto_settings(playlist_id INTEGER,enabled INTEGER)',
        'CREATE TABLE skip_release_settings(playlist_id INTEGER,enabled INTEGER)',
        'CREATE TABLE skip_auto_blocks(asset_key TEXT,kind TEXT,duration_ms INTEGER)',
        'CREATE TABLE skip_presence(playlist_id INTEGER,expires_at INTEGER)'
    ]: con.execute(query)
    for pid in (8,10):
        con.execute('INSERT INTO skip_analysis_playlists VALUES(?,0,1,1,0)',(pid,))
        con.execute('INSERT INTO skip_analysis_sources VALUES(?,1)',(pid,))
        con.execute('INSERT INTO skip_auto_settings VALUES(?,1)',(pid,))
        key='asset'+str(pid)
        con.execute('INSERT INTO skip_assets VALUES(?,?,?,1,1,?,?)',
                    (key,pid,'series'+str(pid),'episode',3600000))
        con.execute('INSERT INTO skip_jobs VALUES(?,?,?,?,?,?)',
                    (pid,key,'review',2,'old','2026-11-01T00:00:00'))
        con.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (pid,key,'audio_repetition','pending','intro',1,1,
                    'series'+str(pid),'episode',3600000,0))
        ev=json.dumps({'status':'AUTO_CONFIRMED','episcene_required':True,
                       'method':'episode_consensus_v3',
                       'windows':[{'asset_key':key,'origin':'server'}]})
        con.execute('INSERT INTO skip_auto_evidence VALUES(?,?,0)',(pid,ev))
    con.commit()
    return con


class CanaryTests(unittest.TestCase):
    def call(self,con,apply):
        with contextlib.redirect_stdout(io.StringIO()):
            return execute(con,apply,now=1793700000)

    def test_read_only_plan_no_changes(self):
        c=testdb()
        self.assertEqual(self.call(c,False),0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='episcene_audio_cache_canary_v1'").fetchone()[0],0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='review'").fetchone()[0],2)
        c.close()

    def test_canary_exactly_one_per_source_idempotent(self):
        c=testdb()
        self.assertEqual(self.call(c,True),2)
        c.commit()
        self.assertEqual(c.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='queued'").fetchone()[0],2)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM episcene_audio_cache_canary_v1").fetchone()[0],2)
        self.assertEqual(self.call(c,True),0)
        c.close()

    def test_playback_and_manual_protection(self):
        c=testdb()
        c.execute('INSERT INTO skip_presence VALUES(8,9999999999)')
        c.execute("INSERT INTO skip_records VALUES(33,'asset10','device','approved','intro',1,1,'series10','episode',3600000,0)")
        self.assertEqual(self.call(c,True),0)
        c.close()

    def test_block_or_present_cache_prevents_requeue(self):
        c=testdb()
        c.execute("INSERT INTO skip_auto_windows VALUES('asset8','intro')")
        c.execute("INSERT INTO skip_auto_blocks VALUES('asset10','intro',3600000)")
        self.assertEqual(self.call(c,True),0)
        c.close()

    def test_respects_release_and_source_settings(self):
        c=testdb()
        c.execute('INSERT INTO skip_release_settings VALUES(8,0)')
        c.execute('UPDATE skip_analysis_playlists SET archived=1 WHERE id=10')
        self.assertEqual(self.call(c,True),0)
        c.close()

    def test_failed_job_not_requeued_without_separate_review(self):
        c=testdb()
        c.execute("UPDATE skip_jobs SET status='failed' WHERE id=8")
        self.assertEqual(self.call(c,True),1)
        self.assertEqual(c.execute("SELECT status FROM skip_jobs WHERE id=8").fetchone()[0],'failed')
        c.close()


if __name__=='__main__':
    unittest.main()
