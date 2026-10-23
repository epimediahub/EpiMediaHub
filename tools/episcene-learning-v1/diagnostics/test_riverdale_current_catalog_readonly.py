#!/usr/bin/env python3
"""Offline-only test; no provider calls, filesystem writes or credentials."""
import sqlite3
import unittest
import riverdale_current_catalog_readonly as m

class RiverdaleCatalogueTests(unittest.TestCase):
    def test_title_is_discovery_not_implicit_identity(self):
        self.assertTrue(m.series_name_matches('Riverdale'))
        self.assertTrue(m.series_name_matches('IT: Riverdale'))
        self.assertTrue(m.series_name_matches('[DE] Riverdale (2017)'))
        self.assertFalse(m.series_name_matches('Riverdale Stories'))
        self.assertFalse(m.series_name_matches('Riverdale S7 E6'))

    def test_series_discovery_deduplicates_and_omits_ids_from_status(self):
        sample=[{'name':'Riverdale','series_id':123},
                {'name':'IT: Riverdale','series_id':456},
                {'name':'IT: Riverdale','series_id':456},
                {'name':'Riverdale 2','series_id':999}]
        ids,kind=m.candidate_series(sample)
        self.assertEqual(ids,['123','456'])
        self.assertEqual(kind,'OK')
        self.assertEqual(m.candidate_series([]),([], 'OK'))

    def test_api_episode_compares_real_stored_stream_id_only(self):
        class Asset(dict):
            pass
        episode=Asset(stream_id='900')
        contents={'episodes':{'7':[
            {'episode_num':6,'id':'1234','container_extension':'mp4'},
            {'episode_num':6,'id':'900','container_extension':'mkv'},
            {'episode_num':5,'id':'900','container_extension':'mp4'}]}}
        result=m.episode_comparison(contents,episode)
        self.assertEqual(result['season7_episode6_count'],2)
        self.assertTrue(result['original_stream_id_still_listed'])
        self.assertEqual(result['current_formats'],['mkv','mp4'])
        self.assertNotIn('900',str(result))
        episode['stream_id']='bad'
        self.assertFalse(m.episode_comparison(contents,episode)['original_stream_id_still_listed'])

    def test_exact_saved_series_id_mapping(self):
        with sqlite3.connect(':memory:') as db:
            db.row_factory=sqlite3.Row
            db.execute('CREATE TABLE skip_catalogue_episodes(playlist_id INTEGER,asset_key TEXT,series_id TEXT)')
            db.executemany('INSERT INTO skip_catalogue_episodes VALUES (?,?,?)',[
                (10,'riverdale','888'),(8,'riverdale','777')])
            self.assertEqual(m.known_series(db,{'asset_key':'riverdale'}),'888')
            db.execute("INSERT INTO skip_catalogue_episodes VALUES (10,'riverdale','999')")
            with self.assertRaises(RuntimeError):
                m.known_series(db,{'asset_key':'riverdale'})

if __name__=='__main__':unittest.main()
