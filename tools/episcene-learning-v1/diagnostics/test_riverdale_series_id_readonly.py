#!/usr/bin/env python3
"""Offline regression checks for Riverdale analysis-catalog identity comparison."""
import sqlite3
import unittest
import riverdale_series_id_readonly as module

class SeriesLookupTests(unittest.TestCase):
    def test_exact_catalogue_mapping_only(self):
        with sqlite3.connect(':memory:') as db:
            db.row_factory=sqlite3.Row
            db.execute('CREATE TABLE skip_catalogue_episodes(playlist_id INTEGER,series_id TEXT,episode_id TEXT)')
            db.executemany('INSERT INTO skip_catalogue_episodes VALUES(?,?,?)',[
                (10,'123','456'), (8,'999','456'), (10,'123','457')])
            candidates,tables=module.candidate_series_ids(db,{'stream_id':'456','source_key':'some-key'})
            self.assertEqual(candidates,['123'])
            self.assertIn('skip_catalogue_episodes:has_series_id',tables)

    def test_unknown_mapping_is_not_fabricated(self):
        with sqlite3.connect(':memory:') as db:
            db.row_factory=sqlite3.Row
            candidates,_=module.candidate_series_ids(db,{'stream_id':'456','source_key':'Riverdale'})
            self.assertEqual(candidates,[])

    def test_multilanguage_episode_id_difference(self):
        catalog={'episodes':{'7':[
            {'season':7,'episode_num':6,'id':'789','container_extension':'mp4'},
            {'season':7,'episode_num':6,'id':'456','container_extension':'mkv'}]}}
        same=module.evaluate(catalog,{'stream_id':'456','extension':'mkv'})
        self.assertTrue(same['analysis_stream_id_matches_catalog'])
        self.assertEqual(same['season7_episode6_candidates'],2)
        stale=module.evaluate(catalog,{'stream_id':'555','extension':'mkv'})
        self.assertFalse(stale['analysis_stream_id_matches_catalog'])
        self.assertNotIn('789',str(stale))
        self.assertNotIn('456',str(stale))

if __name__=='__main__':unittest.main()
