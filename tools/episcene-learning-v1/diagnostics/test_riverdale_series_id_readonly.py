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


    def test_unexpected_json_shapes_classified_without_private_content(self):
        import json
        from contextlib import contextmanager
        from unittest.mock import patch

        class FakeAnalysis:
            @staticmethod
            @contextmanager
            def _provider_proxy_local(source, predicate):
                yield 'http://127.0.0.1:55555/opaque'

        for response, expected in (
            ([], 'XTREAM_EMPTY_ARRAY'),
            ([{'private_password':'DO_NOT_EXPORT'}], 'XTREAM_NONEMPTY_ARRAY'),
            (None, 'XTREAM_JSON_NULL'),
            (False, 'XTREAM_JSON_FALSE'),
            ('PRIVATE_MESSAGE', 'XTREAM_JSON_STRING'),
            ({'episodes':{}}, 'OK'),
        ):
            class Response:
                status=200
                def __enter__(self): return self
                def __exit__(self, *_): return False
                def read(self, max_length): return json.dumps(response).encode()[:max_length]
            class Opener:
                def open(self,*_,**__): return Response()
            with self.subTest(expected=expected):
                with patch('urllib.request.build_opener',return_value=Opener()):
                    kind, data=module.api_fetch(FakeAnalysis,'PRIVATE_PROVIDER_URL')
                self.assertEqual(kind,expected)
                self.assertNotIn('DO_NOT_EXPORT',str((kind,data)))
                self.assertNotIn('PRIVATE_PROVIDER_URL',str((kind,data)))


    def test_controls_use_distinct_analysis_series_only(self):
        with sqlite3.connect(':memory:') as db:
            db.row_factory=sqlite3.Row
            db.executescript("""
                CREATE TABLE skip_catalogue_episodes(
                    playlist_id INTEGER,series_id TEXT,asset_key TEXT,seen_generation INTEGER);
                CREATE TABLE skip_assets(
                    playlist_id INTEGER,asset_key TEXT,media_type TEXT);
            """)
            values=[(10,'100','riverdale','episode'),
                    (10,'200','a1','episode'),(10,'200','a2','episode'),
                    (10,'300','b1','episode'),(10,'300','b2','episode'),
                    (8,'400','c1','episode'),(8,'400','c2','episode'),
                    (10,'500','x1','movie'),(10,'500','x2','movie')]
            for pid,sid,asset,media in values:
                db.execute("INSERT INTO skip_catalogue_episodes VALUES (?,?,?,?)",
                           (pid,sid,asset,42))
                db.execute("INSERT INTO skip_assets VALUES (?,?,?)",(pid,asset,media))
            self.assertEqual(module.control_series_ids(db,'100'),['200','300'])

    def test_controls_absent_without_verified_catalogue_schema(self):
        with sqlite3.connect(':memory:') as db:
            db.row_factory=sqlite3.Row
            db.execute("CREATE TABLE skip_catalogue_episodes(playlist_id INTEGER,series_id TEXT,asset_key TEXT)")
            self.assertEqual(module.control_series_ids(db,'100'),[])

if __name__=='__main__':unittest.main()
