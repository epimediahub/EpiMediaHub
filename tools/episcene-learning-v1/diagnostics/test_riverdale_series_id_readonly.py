#!/usr/bin/env python3
"""Offline regression checks for Riverdale analysis-catalog identity comparison."""
import sqlite3
import unittest
import riverdale_series_id_readonly as module

class SeriesLookupTests(unittest.TestCase):
    def test_exact_asset_key_and_playlist_join(self):
        with sqlite3.connect(':memory:') as db:
            db.row_factory=sqlite3.Row
            db.execute('CREATE TABLE skip_catalogue_episodes(playlist_id INTEGER,series_id TEXT,asset_key TEXT,signature TEXT,seen_generation INTEGER)')
            db.executemany('INSERT INTO skip_catalogue_episodes VALUES(?,?,?,?,?)',[
                (10,'123','target','private-signature',1),
                (8,'999','target','private-signature',1),
                (10,'777','different','other-signature',1)])
            candidates,tables=module.candidate_series_ids(db,{
                'playlist_id':10,'asset_key':'target','stream_id':'episode-456','source_key':'no-guess'})
            self.assertEqual(candidates,['123'])
            self.assertEqual(tables,['skip_catalogue_episodes:exact_asset_key_link'])
            self.assertNotIn('target',str(tables))
            self.assertNotIn('123',str(tables))

    def test_unknown_mapping_is_not_fabricated(self):
        with sqlite3.connect(':memory:') as db:
            db.row_factory=sqlite3.Row
            db.execute('CREATE TABLE skip_catalogue_episodes(playlist_id INTEGER,series_id TEXT,asset_key TEXT)')
            db.execute("INSERT INTO skip_catalogue_episodes VALUES (10,'123','other-episode')")
            candidates,status=module.candidate_series_ids(db,{
                'playlist_id':10,'asset_key':'missing','stream_id':'456'})
            self.assertEqual(candidates,[])
            self.assertEqual(status,['skip_catalogue_episodes:asset_link_absent'])

    def test_conflicting_id_and_wrong_schema_fail_closed(self):
        with sqlite3.connect(':memory:') as db:
            db.row_factory=sqlite3.Row
            db.execute('CREATE TABLE skip_catalogue_episodes(playlist_id INTEGER,series_id TEXT,asset_key TEXT)')
            db.executemany('INSERT INTO skip_catalogue_episodes VALUES (?,?,?)',[
                (10,'123','same'),(10,'456','same')])
            self.assertEqual(module.candidate_series_ids(db,{'playlist_id':10,'asset_key':'same'})[0],[])
            self.assertEqual(module.candidate_series_ids(db,{'playlist_id':10,'asset_key':'same'})[1],[
                'skip_catalogue_episodes:conflicting_asset_links'])

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
