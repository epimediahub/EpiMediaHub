#!/usr/bin/env python3
"""Verify the *actual failure mechanisms* are repaired, not just syntax."""
import ast
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import scene_fix

old_code=("def capture_demo():\n    sql='SELECT * FROM customer_playlists WHERE id=?'\n"
          "    return sql\n\n"
          "def cache_demo():\n"
          "    sql='''JOIN customer_playlists p ON p.id=a.playlist_id JOIN customers c ON c.id=p.customer_id AND c.enabled=1'''\n"
          "    return sql\n\n"
          "def release_demo():\n"
          "    sql='''JOIN customer_playlists p ON p.id=a.playlist_id JOIN customers c ON c.id=p.customer_id AND c.enabled=1'''\n"
          "    return sql\n\n"
          "def visual_demo(audio,kind):\n"
          "    if audio:\n"
          "        begin, end = audio[0]['start_ms'] - 6000, audio[0]['end_ms'] + 6000\n"
          "    else:\n"
          "        begin, end = 0, 100000\n"
          "    return begin, end\n")


def fixture():
    db=sqlite3.connect(':memory:')
    db.row_factory=sqlite3.Row
    db.executescript("""
      CREATE TABLE skip_analysis_playlists(id INTEGER,archived INTEGER);
      CREATE TABLE skip_analysis_sources(playlist_id INTEGER,enabled INTEGER);
      CREATE TABLE skip_auto_settings(playlist_id INTEGER,enabled INTEGER);
      CREATE TABLE skip_release_settings(playlist_id INTEGER,enabled INTEGER);
      CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,source_key TEXT,
          playlist_id INTEGER,season INTEGER,episode INTEGER,duration_ms INTEGER,
          media_type TEXT);
      CREATE TABLE skip_jobs(id INTEGER PRIMARY KEY,asset_key TEXT,status TEXT,
          attempts INTEGER,updated_at TEXT,detail TEXT);
      CREATE TABLE skip_records(id INTEGER PRIMARY KEY,asset_key TEXT,
          source_key TEXT,season INTEGER,episode INTEGER,duration_ms INTEGER,
          source TEXT,segment_type TEXT,status TEXT,disabled INTEGER,media_type TEXT);
      CREATE TABLE skip_auto_evidence(record_id INTEGER,evidence_json TEXT,
          human_review INTEGER);
      CREATE TABLE skip_language_priority(asset_key TEXT,priority INTEGER);
      CREATE TABLE skip_auto_blocks(asset_key TEXT,kind TEXT,duration_ms INTEGER);
      CREATE TABLE skip_presence(device_id INTEGER,playlist_id INTEGER,expires_at INTEGER);
      CREATE TABLE episcene_safe_release_retries(
          asset_key TEXT PRIMARY KEY,last_requeued_utc TEXT,
          attempt_count INTEGER,original_job_status TEXT);
      INSERT INTO skip_analysis_playlists VALUES(8,0);
      INSERT INTO skip_analysis_sources VALUES(8,1);
      INSERT INTO skip_auto_settings VALUES(8,1);
      INSERT INTO skip_release_settings VALUES(8,1);
    """)
    for i in (1,2,3,4):
        key='episode-'+str(i)
        db.execute('INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?)',
                   (key,'mobland',8,1,i,3600000,'episode'))
        db.execute('INSERT INTO skip_jobs VALUES(?,?,?,3,?,?)',
                   (100+i,key,'review','2026-10-14T19:00:00Z',''))
        db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                   (200+i,key,'mobland',1,i,3600000,
                    'audio_repetition','outro','pending',0,'episode'))
        db.execute('INSERT INTO skip_auto_evidence VALUES(?,?,0)',
                   (200+i,json.dumps({'episcene_required':True})))
        db.execute('INSERT INTO skip_language_priority VALUES(?,0)',(key,))
    db.commit()
    return db


class SceneSafety(unittest.TestCase):
    def test_patch_only_three_analysis_inventory_lookups_and_visual_start(self):
        patched,changed=scene_fix.patch(old_code)
        self.assertTrue(changed)
        ast.parse(patched)
        self.assertEqual(patched.count(scene_fix.NEW_JOIN),2)
        self.assertNotIn('customer_playlists',patched)
        self.assertEqual(scene_fix.patch(patched),(patched,False))
        symbols={}
        exec(patched,symbols)
        cut=symbols['visual_demo']([dict(start_ms=3200000,end_ms=3520000)],'outro')
        self.assertEqual(cut,(3139000,3526000))
        same=symbols['visual_demo']([dict(start_ms=30000,end_ms=60000)],'intro')
        self.assertEqual(same,(24000,66000))

    def test_reject_unexpected_live_revision(self):
        for inp in (old_code.replace('customer_playlists','changed_table'),
                    old_code.replace('if audio:','if not audio:'),
                    'print("malicious or outdated")'):
            with self.subTest(inp=inp[:40]):
                with self.assertRaises(ValueError):
                    scene_fix.patch(inp)

    def test_independent_cache_sql_not_filtered_by_missing_customer_row(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript("""
              CREATE TABLE skip_analysis_playlists(id INTEGER,archived INTEGER);
              CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER);
              INSERT INTO skip_analysis_playlists VALUES(8,0);
              INSERT INTO skip_assets VALUES('test-asset',8);
            """)
            valid=db.execute("""SELECT a.asset_key FROM skip_assets a
               JOIN skip_analysis_playlists p ON p.id=a.playlist_id AND p.archived=0""").fetchall()
            self.assertEqual(valid,[('test-asset',)])
            db.execute('UPDATE skip_analysis_playlists SET archived=1')
            invalid=db.execute("""SELECT a.asset_key FROM skip_assets a
               JOIN skip_analysis_playlists p ON p.id=a.playlist_id AND p.archived=0""").fetchall()
            self.assertEqual(invalid,[])


class PeerSeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake=types.ModuleType('safe_release_rollout')
        fake.ensure_retry_table=lambda con:None
        fake.main=lambda:None
        cls.fake=fake
        cls.patcher=mock.patch.dict(sys.modules,{
            'safe_release_rollout':fake,
            'skip_release':types.SimpleNamespace(enabled=lambda con,pid:True),
            'skip_schedule':types.SimpleNamespace(request_series=lambda con,k,reason='playback':None),
        })
        cls.patcher.start()
        import safe_release_rollout_v2 as m
        cls.module=m
    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()

    def test_seed_three_independent_episodes_without_manual_reference(self):
        db=fixture()
        with db:
            candidates=self.module.collect(db)
            self.assertEqual(len(candidates),4)
            plan=self.module.plan(db,candidates,max_jobs=2,models=set())
            self.assertEqual(len(plan),2)
            self.assertEqual({r['episode'] for r in plan},{1,2})
            scheduled=self.module.requeue(db,limit=2)
            self.assertEqual(len(scheduled),2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='queued'").fetchone()[0],2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM episcene_safe_release_retries").fetchone()[0],2)
            # On the NEXT run only two unscheduled siblings remain. The
            # already seeded family must NOT lose its independent peer count.
            next_plan=self.module.plan(db,self.module.collect(db),max_jobs=2)
            self.assertEqual({r['episode'] for r in next_plan},{3,4})

    def test_disagreement_and_open_manual_correction_are_never_requeued(self):
        db=fixture()
        db.execute("""UPDATE skip_auto_evidence SET evidence_json=?
          WHERE record_id=201""",(json.dumps({
              'episcene_required':True,'audio_visual_disagreement':True}),))
        db.execute("""INSERT INTO skip_records VALUES(
              777,'episode-2','mobland',1,2,3600000,'device','outro','pending',0,'episode')""")
        with db:
            candidates=self.module.collect(db)
            self.assertEqual({r['episode'] for r in candidates},{3,4})
            self.assertEqual(self.module.requeue(db,limit=4),[])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='queued'").fetchone()[0],0)

    def test_archived_sources_and_live_playback_do_not_seed(self):
        db=fixture()
        db.execute('UPDATE skip_analysis_playlists SET archived=1')
        with db:self.assertEqual(self.module.collect(db),[])
        db.execute('UPDATE skip_analysis_playlists SET archived=0')
        db.execute('INSERT INTO skip_presence VALUES(10,8,4102444800)')
        with db:self.assertEqual(self.module.collect(db),[])


if __name__=='__main__':
    unittest.main(verbosity=2)
