"""Offline SQLite regression tests for limited EpiScene same-season peer requeue."""
import contextlib
import io
import sqlite3
import unittest

import audio_peer_canary_v1 as peer


def fixture():
    c=sqlite3.connect(':memory:')
    c.row_factory=sqlite3.Row
    c.executescript("""
        CREATE TABLE episcene_audio_cache_canary_v1(
          asset_key TEXT PRIMARY KEY, playlist_id INTEGER, original_status TEXT, queued_at TEXT);
        CREATE TABLE skip_assets(
          asset_key TEXT PRIMARY KEY,playlist_id INTEGER,source_key TEXT,
          season INTEGER,episode INTEGER,media_type TEXT,duration_ms INTEGER);
        CREATE TABLE skip_jobs(
          id INTEGER PRIMARY KEY,asset_key TEXT UNIQUE,status TEXT,attempts INTEGER,
          updated_at TEXT,detail TEXT);
        CREATE TABLE skip_auto_windows(asset_key TEXT,kind TEXT);
        CREATE TABLE skip_records(id INTEGER PRIMARY KEY,asset_key TEXT,source TEXT,disabled INTEGER);
        CREATE TABLE skip_auto_evidence(record_id INTEGER,human_review INTEGER);
        CREATE TABLE skip_analysis_playlists(id INTEGER,archived INTEGER);
        CREATE TABLE skip_analysis_sources(playlist_id INTEGER,enabled INTEGER);
        CREATE TABLE skip_auto_settings(playlist_id INTEGER,enabled INTEGER);
        CREATE TABLE skip_auto_blocks(asset_key TEXT,kind TEXT,duration_ms INTEGER);
        CREATE TABLE skip_presence(playlist_id INTEGER,expires_at INTEGER);
    """)
    for pid in (8,10):
        c.execute('INSERT INTO skip_analysis_playlists VALUES (?,0)',(pid,))
        c.execute('INSERT INTO skip_analysis_sources VALUES (?,1)',(pid,))
        c.execute('INSERT INTO skip_auto_settings VALUES (?,1)',(pid,))
        for ep in (1,2,3,4):
            key='p'+str(pid)+'e'+str(ep)
            c.execute('INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?)',
                      (key,pid,'series'+str(pid),1,ep,'episode',3600000))
            c.execute('INSERT INTO skip_jobs VALUES(?,?,?,?,?,?)',
                      (pid*10+ep,key,'no_reference' if ep==1 else 'review',0,'old','original'))
            if ep==1:
                c.execute('INSERT INTO episcene_audio_cache_canary_v1 VALUES (?,?,?,?)',
                          (key,pid,'review','2026-11-03'))
                c.execute('INSERT INTO skip_auto_windows VALUES (?,?)',(key,'intro'))
                c.execute('INSERT INTO skip_auto_windows VALUES (?,?)',(key,'outro'))
    c.commit()
    return c


def call(c,queue):
    with contextlib.redirect_stdout(io.StringIO()):
        return peer.run(c,queue,1793700000)


class PeerCanaryTests(unittest.TestCase):
    def test_read_only_plan_and_limited_selection(self):
        c=fixture()
        self.assertEqual(call(c,False),0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='review'").fetchone()[0],6)
        self.assertFalse(peer.table_exists(c,peer.LEDGER))
        c.close()

    def test_four_jobs_max_and_idempotent(self):
        c=fixture()
        self.assertEqual(call(c,True),4)
        c.commit()
        self.assertEqual(c.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='queued'").fetchone()[0],4)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM "+peer.LEDGER).fetchone()[0],4)
        self.assertEqual(call(c,True),0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM "+peer.LEDGER).fetchone()[0],4)
        c.close()

    def test_playback_protection_atomic_no_partial_commit(self):
        c=fixture()
        c.execute("INSERT INTO skip_presence VALUES(8,9999999999)")
        self.assertEqual(call(c,True),0)
        self.assertFalse(peer.table_exists(c,peer.LEDGER))
        self.assertEqual(c.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='queued'").fetchone()[0],0)
        c.close()

    def test_manual_review_protection(self):
        c=fixture()
        for ep in (2,3):
            key='p10e'+str(ep)
            c.execute('INSERT INTO skip_records VALUES(?,?,?,?)',(ep,key,'device',0))
        self.assertEqual(call(c,True),0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='queued'").fetchone()[0],0)
        c.close()

    def test_safety_block_protection(self):
        c=fixture()
        for ep in (2,3):
            c.execute('INSERT INTO skip_auto_blocks VALUES(?,?,?)',('p8e'+str(ep),'intro',3600000))
        self.assertEqual(call(c,True),0)
        c.close()

    def test_missing_seed_window_rejects_all(self):
        c=fixture()
        c.execute("DELETE FROM skip_auto_windows WHERE asset_key='p8e1' AND kind='outro'")
        with self.assertRaisesRegex(RuntimeError,'missing intro or outro'):
            call(c,True)
        c.close()

    def test_no_cross_season_or_series(self):
        c=fixture()
        c.execute("UPDATE skip_assets SET season=2 WHERE episode IN (2,3,4) AND playlist_id=8")
        self.assertEqual(call(c,True),0)
        c.close()


if __name__=='__main__':
    unittest.main()
