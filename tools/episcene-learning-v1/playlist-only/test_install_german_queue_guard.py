#!/usr/bin/env python3
"""Fixture regression for fail-closed 4K German queue guard."""
import sqlite3
import unittest

import install_german_queue_guard as gate


def fixture():
    db=sqlite3.connect(':memory:')
    db.executescript("""
      PRAGMA foreign_keys=OFF;
      CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER,
                               media_type TEXT);
      CREATE TABLE skip_jobs(asset_key TEXT PRIMARY KEY,status TEXT,attempts INTEGER);
      CREATE TABLE skip_catalogue_episodes(playlist_id INTEGER,series_id TEXT,
                                           asset_key TEXT);
      CREATE TABLE skip_language_priority(asset_key TEXT PRIMARY KEY,priority INTEGER);
      CREATE TABLE skip_analysis_playlists(id INTEGER PRIMARY KEY,archived INTEGER);
      CREATE TABLE skip_analysis_sources(playlist_id INTEGER,enabled INTEGER);
      INSERT INTO skip_analysis_playlists VALUES(8,0),(10,0);
      INSERT INTO skip_analysis_sources VALUES(8,1),(10,1);
      INSERT INTO skip_assets VALUES('german-one',8,'episode'),
          ('german-two',8,'episode'),('foreign-one',8,'episode'),
          ('foreign-two',8,'episode'),('best-one',10,'episode');
      INSERT INTO skip_jobs VALUES('german-one','queued',0),
          ('german-two','done',1),('foreign-one','queued',0),
          ('foreign-two','queued',0),('best-one','queued',0);
      INSERT INTO skip_catalogue_episodes VALUES
          (8,'100','german-one'),(8,'100','german-two'),
          (8,'200','foreign-one'),(8,'200','foreign-two');
      INSERT INTO skip_language_priority VALUES
          ('german-one',0),('german-two',0),
          ('foreign-one',1),('foreign-two',2),('best-one',2);
    """)
    return db


class GateTests(unittest.TestCase):
    def test_provider_category_evidence(self):
        cats=[{'category_id':'1','category_name':'DE | Serien'},
              {'category_id':'2','category_name':'IT | Serie'},
              {'category_id':'3','category_name':'DE / IT'}]
        series=[{'series_id':100,'category_id':'1'},
                {'series_id':200,'category_id':'2'},
                {'series_id':300,'category_id':'3'}]
        allowed,info=gate.german_series(cats,series)
        self.assertEqual(allowed,{'100'})
        self.assertEqual(info['de_series'],1)
        self.assertEqual(gate.category_class('DE / IT'),'mixed')
        self.assertEqual(gate.category_class('UNKNOWN'),'other')

    def test_exact_set_check_detects_equal_count_mismatch(self):
        db=fixture()
        mapped=gate.assets_for_series(db,{'100'})
        self.assertEqual(mapped,{'german-one','german-two'})
        with self.assertRaisesRegex(RuntimeError,'mismatch'):
            gate.verify_database(db,{'german-one','foreign-one'})

    def test_install_holds_only_foreign_and_catches_requeues(self):
        db=fixture()
        scope={'german-one','german-two'}
        before_best=db.execute("SELECT status FROM skip_jobs WHERE asset_key='best-one'").fetchone()[0]
        held=gate.apply_guard(db,scope)
        self.assertEqual(held,2)
        status=dict(db.execute("SELECT asset_key,status FROM skip_jobs"))
        self.assertEqual(status['german-one'],'queued')
        self.assertEqual(status['german-two'],'done')
        self.assertEqual(status['foreign-one'],'language_hold')
        self.assertEqual(status['foreign-two'],'language_hold')
        self.assertEqual(status['best-one'],before_best)
        db.execute("UPDATE skip_jobs SET status='queued' WHERE asset_key='foreign-one'")
        self.assertEqual(db.execute("SELECT status FROM skip_jobs WHERE asset_key='foreign-one'").fetchone()[0],
                         'language_hold')
        db.execute("INSERT INTO skip_assets VALUES('new-foreign',8,'episode')")
        db.execute("INSERT INTO skip_jobs VALUES('new-foreign','queued',0)")
        self.assertEqual(db.execute("SELECT status FROM skip_jobs WHERE asset_key='new-foreign'").fetchone()[0],
                         'language_hold')
        # A job can arrive ahead of its asset metadata in recovery imports.
        db.execute("INSERT INTO skip_jobs VALUES('job-before-asset','queued',0)")
        db.execute("INSERT INTO skip_assets VALUES('job-before-asset',8,'episode')")
        self.assertEqual(db.execute("SELECT status FROM skip_jobs WHERE asset_key='job-before-asset'").fetchone()[0],
                         'language_hold')
        db.execute("INSERT INTO skip_assets VALUES('moved-from-best',10,'episode')")
        db.execute("INSERT INTO skip_jobs VALUES('moved-from-best','queued',0)")
        db.execute("UPDATE skip_assets SET playlist_id=8 WHERE asset_key='moved-from-best'")
        self.assertEqual(db.execute("SELECT status FROM skip_jobs WHERE asset_key='moved-from-best'").fetchone()[0],
                         'language_hold')
        self.assertEqual(db.execute("SELECT status FROM skip_jobs WHERE asset_key='best-one'").fetchone()[0],
                         'queued')
        db.commit()
        restored=gate.rollback_guard(db)
        self.assertEqual(restored,5)
        self.assertEqual(db.execute("SELECT status FROM skip_jobs WHERE asset_key='foreign-two'").fetchone()[0],
                         'queued')
        self.assertEqual(db.execute("SELECT status FROM skip_jobs WHERE asset_key='german-two'").fetchone()[0],
                         'done')

    def test_apply_rolls_back_when_existing_guard_object_found(self):
        db=fixture()
        db.execute('CREATE TABLE episcene_scope_4k_unknown(id INTEGER)')
        with self.assertRaisesRegex(RuntimeError,'already exist'):
            gate.apply_guard(db,{'german-one','german-two'})
        self.assertEqual(db.execute("SELECT status FROM skip_jobs WHERE asset_key='foreign-one'").fetchone()[0],
                         'queued')
        self.assertNotIn('episcene_scope_4k_allowed',
                         {x[0] for x in db.execute("SELECT name FROM sqlite_master")})


if __name__=='__main__':
    unittest.main(verbosity=2)
