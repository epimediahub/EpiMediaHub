"""EpiScene feedback learning tests: current human truth, history, rejections, zero releases."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import feedback_learning as fb


def fixture(root):
    prod=root/'source.sqlite3'
    target=root/'private'/'feedback.sqlite3'
    target.parent.mkdir(mode=0o700)
    with sqlite3.connect(prod) as db:
        db.executescript("""
        CREATE TABLE skip_records (
          id INTEGER PRIMARY KEY,asset_key TEXT,source TEXT,source_key TEXT,
          segment_type TEXT,status TEXT,season INTEGER,episode INTEGER,
          media_type TEXT,title TEXT,start_ms INTEGER,end_ms INTEGER,
          duration_ms INTEGER,disabled INTEGER,reviewed_at TEXT,
          created_at TEXT,device_id INTEGER,customer_id INTEGER);
        CREATE TABLE skip_assets(
          asset_key TEXT PRIMARY KEY,playlist_id INTEGER,source_key TEXT,
          season INTEGER,episode INTEGER,media_type TEXT,title TEXT,
          duration_ms INTEGER,stream_id TEXT,extension TEXT,updated_at TEXT,
          content_version TEXT,etag TEXT);
        CREATE TABLE devices(id INTEGER PRIMARY KEY,customer_id INTEGER,enabled INTEGER);
        CREATE TABLE customer_playlists(id INTEGER PRIMARY KEY,customer_id INTEGER);
        CREATE TABLE skip_auto_evidence(record_id INTEGER PRIMARY KEY,human_review INTEGER);
        INSERT INTO devices VALUES(99,12,1),(98,999,1);
        INSERT INTO customer_playlists VALUES(8,12);
        """)
        for i,shift in enumerate((35133,35100,34600,35500,35200),1):
            asset=f'asset-{i}'
            db.execute('INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (asset,8,'series-key',1,i,'episode','MobLand',2400000,
                 str(i),'mkv','2026-10-14',None,None))
            db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (200+i,asset,'device','series-key','outro','approved',1,i,
                 'episode','MobLand',2300000,2390000,2400000,0,
                 '2026-10-14T15:00:00Z','2026-10-14T13:00:00Z',99,12))
            db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (300+i,asset,'audio_repetition','series-key','outro','superseded',1,i,
                 'episode','MobLand',2300000+shift,2390000,2400000,0,
                 None,'2026-10-14T14:00:00Z',None,None))
        db.execute('INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('asset-6',8,'series-key',1,6,'episode','MobLand',2400000,'6','mkv','2026-10-14',None,None))
        db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (206,'asset-6','device','series-key','outro','rejected',1,6,'episode','MobLand',
             2300000,2390000,2400000,0,'2026-10-14T15:00:00Z','2026-10-14T13:00:00Z',99,12))
        db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (306,'asset-6','audio_repetition','series-key','outro','superseded',1,6,'episode','MobLand',
             2335000,2390000,2400000,0,None,'2026-10-14T14:00:00Z',None,None))
        db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (404,'asset-5','episcene','series-key','intro','approved',1,5,'episode','MobLand',
             30000,60000,2400000,0,None,'2026-10-14T13:00:00Z',None,None))
        db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (210,'asset-5','device','series-key','recap','approved',1,5,'episode','MobLand',
             1000,30000,2400000,0,'2026-10-14T15:00:00Z','2026-10-14T13:00:00Z',98,12))
    return prod,target


class FeedbackLearningSafety(unittest.TestCase):
    def test_five_independent_examples_create_model_shadow_only(self):
        with tempfile.TemporaryDirectory() as td:
            p,d=fixture(Path(td))
            before=p.read_bytes()
            check=fb.run(p,d,persist=False)
            self.assertEqual(check['positives'],5)
            self.assertEqual(check['negatives'],1)
            self.assertEqual(check['same_asset_comparisons'],6)
            self.assertEqual(check['shadow_models'],1)
            self.assertFalse(d.exists())
            result=fb.run(p,d)
            self.assertEqual(result['active_human_decisions'],6)
            self.assertFalse(result['auto_publish'])
            self.assertTrue(result['production_db_modified'] is False)
            self.assertEqual(p.read_bytes(),before)
            with sqlite3.connect(d) as con:
                self.assertEqual(con.execute('SELECT COUNT(*) FROM feedback_versions WHERE active=1').fetchone()[0],6)
                self.assertEqual(con.execute('SELECT COUNT(*) FROM feedback_versions WHERE decision="negative" AND active=1').fetchone()[0],1)
                m=con.execute('SELECT start_shift_ms,independent_episodes,auto_publish_allowed FROM shadow_calibrations').fetchone()
                self.assertEqual(m,(35133,5,0))
                self.assertFalse(con.execute('SELECT 1 FROM feedback_versions WHERE marker_id IN (404,210)').fetchone())

    def test_idempotent_history_and_cancel_superseded_labels(self):
        with tempfile.TemporaryDirectory() as td:
            p,d=fixture(Path(td))
            fb.run(p,d)
            with sqlite3.connect(p) as con:
                con.execute("UPDATE skip_records SET status='superseded' WHERE id=201")
                con.execute("UPDATE skip_records SET start_ms=2280000,reviewed_at='2026-10-15T09:00:00Z' WHERE id=202")
            fb.run(p,d)
            fb.run(p,d)
            with sqlite3.connect(d) as con:
                self.assertEqual(con.execute('SELECT COUNT(*) FROM feedback_versions WHERE marker_id=201 AND active=1').fetchone()[0],0)
                self.assertEqual(con.execute('SELECT COUNT(*) FROM feedback_versions WHERE marker_id=201').fetchone()[0],1)
                self.assertEqual(con.execute('SELECT COUNT(*) FROM feedback_versions WHERE marker_id=202').fetchone()[0],2)
                self.assertEqual(con.execute('SELECT COUNT(*) FROM feedback_versions WHERE marker_id=202 AND active=1').fetchone()[0],1)
                self.assertEqual(con.execute('SELECT COUNT(*) FROM shadow_calibrations').fetchone()[0],0)

    def test_duplicate_human_decision_excludes_both(self):
        with tempfile.TemporaryDirectory() as td:
            p,d=fixture(Path(td))
            with sqlite3.connect(p) as con:
                con.execute('INSERT INTO skip_records SELECT 555,asset_key,source,source_key,segment_type,status,season,episode,media_type,title,start_ms+1000,end_ms,duration_ms,disabled,reviewed_at,created_at,device_id,customer_id FROM skip_records WHERE id=202')
            result=fb.run(p,d,persist=False)
            self.assertEqual(result['ambiguous_asset_kinds'],1)
            self.assertEqual(result['positives'],4)
            self.assertEqual(result['shadow_models'],1)

    def test_multiple_machine_hints_not_cherrypicked(self):
        with tempfile.TemporaryDirectory() as td:
            p,d=fixture(Path(td))
            with sqlite3.connect(p) as con:
                con.execute('INSERT INTO skip_records SELECT 333,asset_key,source,source_key,segment_type,status,season,episode,media_type,title,start_ms+10000,end_ms,duration_ms,disabled,reviewed_at,created_at,device_id,customer_id FROM skip_records WHERE id=301')
            report=fb.run(p,d,persist=False)
            self.assertEqual(report['same_asset_comparisons'],5)
            self.assertEqual(report['shadow_models'],1)

if __name__=='__main__':
    unittest.main(verbosity=2)
