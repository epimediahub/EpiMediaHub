#!/usr/bin/env python3
"""Verify read-only provider series -> local queued episode mapping."""
import json
import sqlite3
import unittest
import audit_4k_scope_join as probe


def fixture():
    db=sqlite3.connect(':memory:')
    db.executescript("""
       CREATE TABLE skip_catalogue_episodes(playlist_id INTEGER,series_id TEXT,asset_key TEXT);
       CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER,media_type TEXT,title TEXT);
       CREATE TABLE skip_jobs(asset_key TEXT,status TEXT);
       CREATE TABLE skip_language_priority(asset_key TEXT,priority INTEGER);
       INSERT INTO skip_catalogue_episodes VALUES
          (8,'100','secret-de-1'),(8,'100','secret-de-2'),
          (8,'200','secret-it'),(8,'300','secret-mixed'),
          (10,'100','secret-other-playlist');
       INSERT INTO skip_assets VALUES
          ('secret-de-1',8,'episode','private title 1'),
          ('secret-de-2',8,'episode','private title 2'),
          ('secret-it',8,'episode','private title 3'),
          ('secret-mixed',8,'episode','private title 4'),
          ('secret-other-playlist',10,'episode','private title 5');
       INSERT INTO skip_jobs VALUES
          ('secret-de-1','queued'),('secret-de-2','done'),
          ('secret-it','queued'),('secret-mixed','queued'),
          ('secret-other-playlist','queued');
       INSERT INTO skip_language_priority VALUES
          ('secret-de-1',0),('secret-de-2',0),
          ('secret-it',1),('secret-mixed',2),('secret-other-playlist',0);
    """)
    return db


class StrictMatching(unittest.TestCase):
    def test_allow_explicit_german_only_then_join_jobs(self):
        db=fixture()
        cats=[
          {'category_id':'1','category_name':'DE | Serien'},
          {'category_id':'2','category_name':'IT | Serie'},
          {'category_id':'3','category_name':'DE / IT gemischt'}
        ]
        series=[
          {'series_id':100,'category_id':'1','name':'private German'},
          {'series_id':200,'category_id':'2','name':'private Italian'},
          {'series_id':300,'category_id':'3','name':'private Mixed'}
        ]
        before=db.total_changes
        summary=probe.run_report(cats,series,db)
        self.assertEqual(db.total_changes,before)
        self.assertEqual(summary['provider']['eligible_series_ids'],1)
        jobs=summary['local']['mapped_german_category_jobs_by_status']
        self.assertEqual(jobs,{'done':1,'queued':1})
        self.assertEqual(summary['local']['not_mapped_jobs_by_status'],{'queued':2})
        self.assertTrue(summary['local']['legacy_rank0_vs_provider_de']['exact_same_asset_set'])
        self.assertEqual(summary['local']['legacy_rank0_vs_provider_de']['rank0_not_provider_de'],0)
        rendered=json.dumps(summary)
        for secret in ('secret-de','private title','private German'):
            self.assertNotIn(secret,rendered)

    def test_conflicting_duplicate_series_ids_are_excluded(self):
        cats=[{'category_id':1,'category_name':'DE | Serien'},
              {'category_id':2,'category_name':'IT | Serie'}]
        series=[{'series_id':5,'category_id':1},{'series_id':5,'category_id':2}]
        eligible,counts=probe.safe_series_ids(cats,series)
        self.assertEqual(eligible,set())
        self.assertEqual(counts['conflicting_series_ids'],1)

    def test_german_category_mismatch_is_not_approved(self):
        cats=[{'category_id':1,'category_name':'DE | Serien'}]
        series=[{'series_id':5,'category_id':None},{'series_id':6,'category_id':[1,999]}]
        eligible,counts=probe.safe_series_ids(cats,series)
        self.assertEqual(eligible,set())
        self.assertEqual(counts['eligible_series_ids'],0)

    def test_equal_legacy_and_provider_counts_can_hide_wrong_membership(self):
        db=fixture()
        db.execute("UPDATE skip_language_priority SET priority=1 WHERE asset_key='secret-de-2'")
        db.execute("UPDATE skip_language_priority SET priority=0 WHERE asset_key='secret-it'")
        cats=[{'category_id':1,'category_name':'DE | Serien'},
              {'category_id':2,'category_name':'IT | Serien'}]
        series=[{'series_id':100,'category_id':1},
                {'series_id':200,'category_id':2}]
        result=probe.run_report(cats,series,db)
        comparison=result['local']['legacy_rank0_vs_provider_de']
        self.assertEqual(comparison['rank0_4k_assets'],2)
        self.assertEqual(comparison['provider_de_assets'],2)
        self.assertFalse(comparison['exact_same_asset_set'])
        self.assertEqual(comparison['rank0_not_provider_de'],1)
        self.assertEqual(comparison['provider_de_not_rank0'],1)

    def test_wrong_catalogue_structure_fails_closed(self):
        db=sqlite3.connect(':memory:')
        with self.assertRaisesRegex(ValueError,'missing expected'):
            probe.local_coverage(db,{'1'})


if __name__=='__main__':
    unittest.main(verbosity=2)
