#!/usr/bin/env python3
"""Fully offline regression tests for reciprocal visual-peer scheduling."""
from datetime import datetime,timezone
import json
import sqlite3
import sys
import types
import unittest
from unittest.mock import patch

import recheck_approved_visual_peers as m

A='a'*64
B='b'*64
C='c'*64
D='d'*64
E='e'*64

SCHEMA="""
CREATE TABLE skip_records(id INTEGER PRIMARY KEY,asset_key TEXT,status TEXT,
 source TEXT,disabled INTEGER,source_key TEXT,season INTEGER,episode INTEGER,
 segment_type TEXT,duration_ms INTEGER);
CREATE TABLE skip_assets(asset_key TEXT,source_key TEXT,playlist_id INTEGER,
 season INTEGER,episode INTEGER,title TEXT,duration_ms INTEGER,media_type TEXT);
CREATE TABLE skip_jobs(id INTEGER PRIMARY KEY,asset_key TEXT,status TEXT,
 updated_at TEXT,attempts INTEGER,detail TEXT);
CREATE TABLE skip_auto_evidence(record_id INTEGER,evidence_json TEXT,human_review INTEGER);
CREATE TABLE episcene_safe_release_retries(asset_key TEXT PRIMARY KEY,
 attempt_count INTEGER,last_requeued_utc TEXT,original_job_status TEXT);
CREATE TABLE skip_analysis_playlists(id INTEGER,archived INTEGER);
CREATE TABLE skip_analysis_sources(playlist_id INTEGER,enabled INTEGER);
CREATE TABLE skip_auto_settings(playlist_id INTEGER,enabled INTEGER);
CREATE TABLE skip_presence(playlist_id INTEGER,expires_at INTEGER);
CREATE TABLE skip_release_settings(playlist_id INTEGER);
CREATE TABLE skip_auto_blocks(asset_key TEXT,kind TEXT,duration_ms INTEGER);
"""

def doc(support=3,conflict=False):
    return json.dumps(dict(episcene_required=True,
        audio_visual_disagreement=conflict,decision=dict(
        status='AUTO_CONFIRMED',support=support,
        ambiguous=False,boundaries_confirmed=True,matches=[
            {'partner':B,'quality':.98,'boundaries_confirmed':True},
            {'partner':C,'quality':.99,'boundaries_confirmed':True},
            {'partner':D,'quality':.97,'boundaries_confirmed':True}])))

class MockV2:
    @staticmethod
    def protected(db,record):
        return bool(db.execute("""SELECT 1 FROM skip_auto_blocks
          WHERE asset_key=? AND kind=?""",
          (record['asset_key'],record['kind'])).fetchone())

class RecheckTests(unittest.TestCase):
    def make_db(self):
        db=sqlite3.connect(':memory:')
        db.row_factory=sqlite3.Row
        db.executescript(SCHEMA)
        for table in ('skip_analysis_playlists','skip_analysis_sources',
                      'skip_auto_settings','skip_release_settings'):
            db.execute('INSERT INTO '+table+' VALUES ('+('10,0' if table=='skip_analysis_playlists' else
                           '10,1' if table!='skip_release_settings' else '10')+')')
        peers=[(A,6,'approved'),(B,4,'pending'),(C,7,'pending'),(D,9,'pending'),
               (E,10,'pending')]
        for n,(key,ep,st) in enumerate(peers):
            db.execute('INSERT INTO skip_assets VALUES (?,?,?,?,?,?,?,?)',
                       (key,'source-v1',10,3,ep,'Futurama',1400000,'episode'))
            db.execute('INSERT INTO skip_jobs VALUES (?,?,?,?,?,?)',
                       (n+1,key,'done' if key==A else 'review','2026-10-22',1,''))
            db.execute('INSERT INTO skip_records VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (n+1,key,st,'episcene' if key==A else 'audio_repetition',
                        0,'source-v1',3,ep,'intro',1400000))
            db.execute('INSERT INTO skip_auto_evidence VALUES (?,?,?)',
                       (n+1,doc() if key==A else '{"episcene_required":true}',0))
        db.commit()
        return db

    def test_verified_source_yields_only_known_peers(self):
        sample=[dict(playlist_id=10,source_key='Futurama',season=3,
                     segment_type='intro',asset_key=A,evidence_json=doc())]
        groups=m.partner_keys(sample)
        self.assertEqual(groups[(10,'Futurama',3,'intro')],{B,C,D})
        sample[0]['evidence_json']=doc(support=2)
        self.assertEqual(m.partner_keys(sample),{})
        sample[0]['evidence_json']=doc(conflict=True)
        self.assertEqual(m.partner_keys(sample),{})

    def test_plan_keeps_jobs_pending_until_normal_analysis(self):
        db=self.make_db()
        with patch.dict(sys.modules,{'skip_release':types.SimpleNamespace(enabled=lambda db,p:True)}):
            rows,report=m.get_plan(db,MockV2,'2026-10-23T07:20:00+00:00')
        self.assertEqual([row['asset_key'] for row in rows],[B,C,D])
        self.assertEqual(report['selected'],3)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM skip_records WHERE status='approved'").fetchone()[0],1)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='review'").fetchone()[0],4)

    def test_blocked_or_cross_language_jobs_are_not_selected(self):
        db=self.make_db()
        db.execute("INSERT INTO skip_auto_blocks VALUES(?,?,?)",(B,'intro',1400000))
        db.execute('UPDATE skip_assets SET source_key=? WHERE asset_key=?',('italian-other-edition',C))
        db.commit()
        with patch.dict(sys.modules,{'skip_release':types.SimpleNamespace(enabled=lambda db,p:True)}):
            rows,_=m.get_plan(db,MockV2,'2026-10-23T07:20:00+00:00')
        self.assertEqual([r['asset_key'] for r in rows],[D])

    def test_no_extra_same_day_retry_and_daily_limit(self):
        db=self.make_db()
        db.execute("INSERT INTO episcene_safe_release_retries VALUES(?,?,?,?)",
                   (B,1,'2026-10-23T03:00:00+00:00','review'))
        db.execute("INSERT INTO episcene_safe_release_retries VALUES(?,?,?,?)",
                   (C,1,'2026-10-22T03:00:00+00:00','review'))
        db.commit()
        with patch.dict(sys.modules,{'skip_release':types.SimpleNamespace(enabled=lambda db,p:True)}):
            rows,_=m.get_plan(db,MockV2,'2026-10-23T07:20:00+00:00')
        self.assertEqual([r['asset_key'] for r in rows],[D,C])
        db.execute('INSERT INTO skip_presence VALUES (10,?)',(int(datetime.now(timezone.utc).timestamp())+3600,))
        with patch.dict(sys.modules,{'skip_release':types.SimpleNamespace(enabled=lambda db,p:True)}):
            with self.assertRaisesRegex(RuntimeError,'VIEWER_ACTIVE'):
                m.get_plan(db,MockV2,'2026-10-23T07:20:00+00:00')

if __name__=='__main__':
    unittest.main()
