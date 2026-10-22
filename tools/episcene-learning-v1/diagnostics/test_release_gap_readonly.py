#!/usr/bin/env python3
"""Fail-safe tests for aggregate, no-write EpiScene visual gap diagnostics."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import release_gap_readonly as mod


def seed(path, *, revisions=False):
    db=sqlite3.connect(path)
    db.executescript('''
    CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY, playlist_id INTEGER,
      source_key TEXT, season INTEGER, episode INTEGER, duration_ms INTEGER,
      stream_id TEXT, extension TEXT, updated_at TEXT, content_version TEXT, etag TEXT);
    CREATE TABLE skip_scene_windows(id INTEGER PRIMARY KEY, asset_key TEXT,
      kind TEXT, duration_ms INTEGER);
    CREATE TABLE skip_jobs(asset_key TEXT, status TEXT, detail TEXT, attempts INTEGER);
    CREATE TABLE skip_records(id INTEGER PRIMARY KEY, asset_key TEXT,
      source TEXT, status TEXT, segment_type TEXT);
    CREATE TABLE skip_auto_evidence(record_id INTEGER,evidence_json TEXT);
    ''')
    db.executemany('INSERT INTO skip_assets(asset_key,playlist_id,source_key,season,episode,duration_ms) VALUES (?,?,?,?,?,?)',
        [('a1',8,'seriesA',1,1,100000),('a2',8,'seriesA',1,2,100000),
         ('a3',8,'seriesA',1,3,100000),('b1',10,'seriesB',1,1,90000)])
    db.executemany('INSERT INTO skip_scene_windows(id,asset_key,kind,duration_ms) VALUES (?,?,?,?)',
        [(1,'a1','intro',100000),(2,'a2','intro',100000),(3,'a3','intro',100000),
         (4,'a1','outro',99000)])
    db.executemany('INSERT INTO skip_records VALUES (?,?,?,?,?)',[
        (10,'a1','audio','pending','intro'),
        (11,'a2','episcene','pending','intro'),
        (12,'b1','audio','pending','intro'),
        (13,'a3','audio','pending','intro')])
    db.executemany('INSERT INTO skip_auto_evidence VALUES (?,?)',[
        (10,json.dumps({'episcene_required':True})),
        (11,json.dumps({'method':'episcene_consensus','decision':{'status':'REVIEW'}})),
        (12,json.dumps({'episcene_required':True})),
        (13,json.dumps({'audio_visual_disagreement':True}))])
    db.executemany('INSERT INTO skip_jobs VALUES (?,?,?,?)',[
        ('a1','review','not verified',1),
        ('a2','failed','undisclosed tokenabc123 example',1),
        ('a3','failed','undisclosed tokenabc123 example',2),
        ('b1','partial','ffmpeg decoder failed',3)])
    if revisions:
        db.execute('CREATE TABLE skip_scene_window_versions(window_id INTEGER, version TEXT)')
        db.row_factory=sqlite3.Row
        for num,key in [(1,'a1'),(2,'a2'),(3,'a3'),(4,'a1')]:
            value=mod.version(db.execute('SELECT * FROM skip_assets WHERE asset_key=?',(key,)).fetchone())
            db.execute('INSERT INTO skip_scene_window_versions VALUES (?,?)',
                (num,value if num!=2 else 'stale-revision'))
    db.commit()
    db.close()


class TestReleaseGap(unittest.TestCase):
    def test_only_aggregates_and_original_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'db.sqlite3'
            seed(p)
            with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as db:
                report=mod.analyze(db)
            self.assertEqual(report['window_to_pending_marker_gap']['8'],
                {'THREE_PLUS_EPISODES_HAVE_WINDOWS_CHECK_CONSENSUS_ENGINE':2})
            self.assertEqual(report['window_to_pending_marker_gap']['10'],
                {'NO_VISUAL_WINDOWS_FOR_ASSET_AND_KIND':1})
            self.assertEqual(report['pending_stage_by_playlist']['8']['AUDIO_VISUAL_CONFLICT'],1)
            self.assertEqual(report['failed_jobs']['8']['unclassified_distinct_details'],1)
            self.assertEqual(report['failed_jobs']['8']['unclassified_most_common_detail_repetitions'],2)
            leak=json.dumps(report)
            for prohibited in ('tokenabc123','undisclosed','seriesA','seriesB','a1','b1'):
                self.assertNotIn(prohibited,leak)
            with sqlite3.connect(p) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM skip_records').fetchone()[0],4)

    def test_detect_revision_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'db.sqlite3'
            seed(p,revisions=True)
            with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as db:
                result=mod.analyze(db)
            self.assertTrue(result['version_table_present'])
            self.assertEqual(result['window_to_pending_marker_gap']['8'],
                {'THREE_PLUS_EPISODES_HAVE_WINDOWS_CHECK_CONSENSUS_ENGINE':1,
                 'WINDOWS_BUT_NO_MATCHING_ASSET_REVISION':1})

    def test_schema_fail_closed(self):
        with sqlite3.connect(':memory:') as db:
            with self.assertRaises(RuntimeError):
                mod.analyze(db)

if __name__=='__main__':unittest.main()
