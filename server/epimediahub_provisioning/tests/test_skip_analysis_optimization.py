"""Read-only latency, exact accelerated matching and stricter publication evidence."""
import contextlib
import dataclasses
import importlib.util
import json
from pathlib import Path
import random
import sqlite3
import sys
import types
import unittest
from unittest import mock

import numpy as np
from flask import Flask, abort, jsonify, session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_skip_analysis_references import ReferenceFixture
import test_skip_analysis_detector_v2 as detector_fixtures
import test_skip_analysis_automation as automation_fixtures
from skip_analysis import matching_offset
from skip_analysis_worker import busy_check
from skip_database import connect, enable_wal
from skip_detector_v3 import FpWindow, Config, PairCache, detect, pair_candidates, AUTO, REVIEW, REJECTED
from skip_markers import install
from skip_progress import overview, populate
from skip_progress_worker import update
from skip_release import accept_pending
import skip_automation as auto

ROOT = Path(__file__).resolve().parents[1]


class DashboardLatencyTests(ReferenceFixture, unittest.TestCase):
    def db(self):
        return connect(self.db_path, timeout=.05)

    def setUp(self):
        super().setUp()
        with self.db() as con:
            enable_wal(con)
            con.execute("ALTER TABLE customers ADD COLUMN name TEXT NOT NULL DEFAULT 'Customer'")
        self.waiting(status='done')
        self.site = Flask('progress-api', template_folder=str(ROOT/'templates'), static_folder=str(ROOT/'static'))
        self.site.secret_key = 'isolated-fixture'
        self.site.testing = True
        self.site.add_url_rule('/dashboard', 'dashboard', lambda: 'Dashboard')
        self.site.add_url_rule('/health', 'health', lambda: jsonify(status='ok'))
        backend = types.ModuleType('app')
        backend.digest = lambda value: value
        backend.web_auth = lambda: None if session.get('admin') else abort(401)
        with mock.patch.dict(sys.modules, {'app': backend}):
            install(self.site, self.db)
        self.client = self.site.test_client()
        with self.client.session_transaction() as value:
            value['admin'] = True
        with self.db() as con:
            populate(con)

    def test_page_and_json_read_under_writer_lock_without_touching_dirty_revision(self):
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='failed'")
            revision = con.execute('SELECT revision FROM skip_progress_dirty').fetchone()[0]
        with self.db() as writer:
            writer.execute('BEGIN IMMEDIATE')
            for path in ('/admin/skip', '/admin/skip/progress'):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertIn('Server-Timing', response.headers)
        with self.db() as con:
            self.assertEqual(con.execute('SELECT revision FROM skip_progress_dirty').fetchone()[0], revision)

    def test_json_requires_admin_and_never_contains_provider_credentials(self):
        self.assertEqual(self.site.test_client().get('/admin/skip/progress').status_code, 401)
        value = self.client.get('/admin/skip/progress').get_data(as_text=True)
        self.assertNotIn('TEST_PROVIDER_SECRET', value)
        self.assertNotIn('player_api.php', value)
        self.assertNotIn('source_url', value)

    def test_page_uses_only_cached_catalogue_counts_and_never_plans_the_queue(self):
        import skip_schedule as schedule
        import skip_catalogue as catalogue
        from skip_dashboard_stats import refresh as refresh_statistics
        original=catalogue.dashboard
        def cached_only(con,**kwargs):
            self.assertIsInstance(kwargs.get('counts_cache'),dict)
            return original(con,**kwargs)
        for warmed in (False,True):
            if warmed:
                with self.db() as con:refresh_statistics(con,force=True)
            with mock.patch.object(catalogue,'dashboard',side_effect=cached_only), \
                 mock.patch.object(schedule,'select_job',side_effect=AssertionError('No queue planning in GET')), \
                 mock.patch.object(schedule,'current_playlist',side_effect=AssertionError('No queue planning in GET')), \
                 mock.patch.object(schedule,'language_stage',side_effect=AssertionError('No global queue scan in GET')):
                response=self.client.get('/admin/skip')
                self.assertEqual(response.status_code,200)
                self.assertIn('catalogue;dur=',response.headers['Server-Timing'])
                self.assertIn('schedule;dur=',response.headers['Server-Timing'])

    def test_running_job_and_playlist_order_stay_live_when_statistics_are_stale(self):
        from skip_dashboard_stats import refresh as refresh_statistics,schedule_view,read
        with self.db() as con:
            refresh_statistics(con,force=True)
            con.execute("UPDATE skip_jobs SET status='running'")
            con.execute("UPDATE customer_playlists SET name='Renamed' WHERE id=1")
            value=schedule_view(con,read(con))
            self.assertEqual(value['current']['asset_key'],self.target['asset_key'])
            self.assertEqual(value['current']['playlist_name'],'Renamed')

    def test_running_schedule_snapshot_does_not_sort_the_remaining_queue(self):
        import skip_schedule as schedule
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='running'")
            with mock.patch.object(schedule,'select_job',side_effect=AssertionError('Already running')):
                self.assertEqual(schedule.overview(con)['current']['asset_key'],self.target['asset_key'])

    def test_background_statistics_keep_unique_catalogue_assets_and_job_states(self):
        from skip_dashboard_stats import refresh as refresh_statistics,catalogue_view,read
        with self.db() as con:
            con.execute("INSERT INTO skip_catalogue_settings VALUES(1,1,'now')")
            con.execute("INSERT INTO skip_catalogue_series VALUES(1,'501','{}','sig',0,1,0,0,'ok','')")
            con.execute("INSERT INTO skip_catalogue_series VALUES(1,'502','{}','sig',0,1,0,0,'ok','')")
            con.executemany('INSERT INTO skip_catalogue_episodes VALUES(1,?,?,?,1)',
                [(series,self.target['asset_key'],'sig') for series in ('501','502')])
            refresh_statistics(con,force=True)
            value=catalogue_view(con,read(con))[0]
            self.assertEqual((value['episodes'],value['analyzed'],value['waiting']),(1,1,0))
            con.execute("UPDATE skip_jobs SET status='queued'")
            refresh_statistics(con,force=True)
            value=catalogue_view(con,read(con))[0]
            self.assertEqual((value['episodes'],value['analyzed'],value['waiting']),(1,0,1))

    def test_background_refresh_defers_on_writer_then_updates_the_series(self):
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='failed'")
        with self.db() as writer:
            writer.execute('BEGIN IMMEDIATE')
            self.assertEqual(update(self.db_path), 0)
        self.assertEqual(update(self.db_path), 1)
        self.assertEqual(self.client.get('/admin/skip/progress').get_json()['progress']['rows'][0]['failed'], 1)

    def test_installation_latency_check_uses_read_only_database(self):
        spec=importlib.util.spec_from_file_location('latency_check',ROOT/'deploy/check_skip_latency.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='failed'")
            revision=con.execute('SELECT revision FROM skip_progress_dirty').fetchone()[0]
        with self.db() as writer:
            writer.execute('BEGIN IMMEDIATE')
            value=module.check(self.db_path)
        self.assertEqual([r['view'] for r in value],['page_first','page_warm','filter','search'])
        self.assertIn('database_ms',value[0])
        self.assertIn('render_ms',value[0])
        with self.db() as con:
            self.assertEqual(con.execute('SELECT revision FROM skip_progress_dirty').fetchone()[0],revision)

    def test_unicode_search_literal_percent_and_bounded_sql_pages(self):
        with self.db() as con:
            row = tuple(con.execute('SELECT * FROM skip_progress_series').fetchone())
            for index in range(45):
                title = 'Straße 100%' if index == 44 else f'Serie {index:02d}'
                con.execute('INSERT INTO skip_progress_series VALUES('+','.join('?' for _ in row)+')',
                            (row[0],f'{index:064x}',title,*row[3:]))
            def guard(action, table, *_):
                if action in (sqlite3.SQLITE_INSERT,sqlite3.SQLITE_DELETE,sqlite3.SQLITE_UPDATE):
                    return sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_READ and table in ('skip_assets','skip_records','skip_catalogue_episodes'):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            con.set_authorizer(guard)
            self.assertEqual(len(overview(con,page=2,refresh_cache=False)['rows']),20)
            found=overview(con,search='STRASSE 100%',refresh_cache=False)
            self.assertEqual(found['total'],1)
            self.assertEqual(found['rows'][0]['title'],'Straße 100%')
            self.assertEqual(overview(con,search='%',refresh_cache=False)['total'],1)


class MatchingPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(4817)

    def words(self, n):
        return [self.rng.getrandbits(32) for _ in range(n)]

    def test_exact_hamming_threshold_and_confidence_survive_fft_rounding(self):
        reference=self.words(100)
        target=[word ^ (7 | (256 if index<20 else 0)) for index,word in enumerate(reference)]
        self.assertEqual(matching_offset(reference,target,125),(0,.9))

    def test_noisy_shifts_agree_with_an_independent_full_hamming_scan(self):
        for _ in range(20):
            reference=self.words(100)
            before=self.rng.randrange(10,100)
            target=self.words(before)+[w^3 for w in reference]+self.words(70)
            costs=[sum((a^b).bit_count() for a,b in zip(reference,target[i:i+len(reference)]))/(32*len(reference))
                   for i in range(len(target)-len(reference)+1)]
            offset,confidence=matching_offset(reference,target,125)
            self.assertEqual(confidence,1-min(costs))
            self.assertLessEqual(abs(offset-costs.index(min(costs))*125),63)

    def test_repeated_reference_and_unrelated_audio_remain_rejected(self):
        reference=self.words(120)
        self.assertIsNone(matching_offset(reference,self.words(20)+reference+self.words(100)+reference,125))
        self.assertIsNone(matching_offset(reference,self.words(700),125))

    def windows(self,count=4,two_themes=False):
        theme,second=self.words(220),self.words(220)
        result=[]
        for index in range(count):
            before=100+index*17
            fp=self.words(before)+theme+self.words(200)
            if two_themes:fp+=second+self.words(100)
            result.append(FpWindow(np.asarray(fp),item_sec=.125,episode_id=str(index),duration_sec=2700))
        return result

    def test_equal_independent_recurring_sections_are_ambiguous(self):
        windows=self.windows(two_themes=True)
        result=detect(windows[0],windows[1:],'intro')
        self.assertEqual(result.status,REJECTED)
        self.assertTrue(result.details['ambiguous'])

    def test_constant_audio_and_tiny_loops_cannot_identify_an_intro(self):
        for fp in ([0]*400,list(range(8))*50):
            windows=[FpWindow(np.array(self.words(100)+fp+self.words(80)),item_sec=.125,episode_id=str(i)) for i in range(4)]
            self.assertEqual(detect(windows[0],windows[1:],'intro').status,REJECTED)

    def test_trust_applies_only_to_the_marked_reference_range(self):
        windows=self.windows(3)
        partner=windows[1]
        partner.trusted=True
        partner.trusted_ranges=((0,5),)
        self.assertEqual(detect(windows[0],windows[1:],'intro').status,REVIEW)
        partner.trusted_ranges=((117*.125,337*.125),)
        self.assertEqual(detect(windows[0],windows[1:],'intro').status,AUTO)

    def test_different_configurations_do_not_share_pair_results(self):
        windows=self.windows(2)
        cache=PairCache()
        full=pair_candidates(*windows,'intro',Config(),cache)
        short=pair_candidates(*windows,'intro',dataclasses.replace(Config(),max_seconds=20),cache)
        self.assertFalse(full[0].truncated)
        self.assertTrue(short[0].truncated)
        self.assertEqual(len(cache._d),2)

    def test_cache_content_is_immutable_and_memory_and_pairs_are_bounded(self):
        windows=self.windows(5)
        cache=PairCache(max_pairs=2,max_fft_bytes=500000)
        with self.assertRaises(ValueError):windows[0].fp[0]=0
        for partner in windows[1:]:pair_candidates(windows[0],partner,'intro',cache=cache)
        self.assertLessEqual(cache.stats()['pairs'],2)
        self.assertLessEqual(cache.stats()['fft_bytes'],500000)


class PublicationPrecisionTests(automation_fixtures.AutomationFixture, unittest.TestCase):
    cached = detector_fixtures.IntegrationTests.cached

    def setUp(self):
        super().setUp()
        with self.db() as con:
            con.execute('DELETE FROM skip_release_settings')

    def test_changed_trusted_reference_during_release_cannot_authorize_two_partner_result(self):
        items=self.cached(count=3)
        with self.db() as con:
            marker=auto.add_record(con,items[1],'intro',30000,57500,False,self.device)
            con.execute("UPDATE skip_records SET status='approved',reviewed_at='reviewed' WHERE id=?",(marker['id'],))
            self.assertTrue(auto.bootstrap(con,items[0],'intro'))
            evidence=json.loads(con.execute('SELECT evidence_json FROM skip_auto_evidence WHERE record_id IN '
                "(SELECT id FROM skip_records WHERE status='pending')").fetchone()[0])
            self.assertEqual(evidence['status'],'AUTO_CONFIRMED')
            self.assertTrue(evidence['trusted_markers'])
            con.execute('UPDATE skip_records SET start_ms=start_ms+1000 WHERE id=?',(marker['id'],))
            self.assertEqual(accept_pending(con,asset_key=items[0]['asset_key']),0)

    def test_weak_or_unconfirmed_reference_cannot_bypass_consensus(self):
        self.registered(self.target)
        for change in ({'confidence':.91},{'boundaries_confirmed':False}):
            vote=self.voted(12,'81')|change
            with self.db() as con:
                auto.store_proposal(con,self.target,'intro',vote['start'],vote['end'],'audio',.98,
                                    {'method':'reviewed_audio_match','vote':vote})
                self.assertEqual(accept_pending(con),0)
                self.assertEqual(con.execute("SELECT status FROM skip_records WHERE source='audio'").fetchone()[0],'pending')
                con.execute("DELETE FROM skip_records WHERE source='audio'")

    def test_disagreeing_strong_references_stay_pending(self):
        self.registered(self.target)
        votes=[self.voted(12,'81'),self.voted(11,'83')|{'start':58000,'end':84530}]
        with self.db() as con:
            for vote in votes:
                auto.store_proposal(con,self.target,'intro',vote['start'],vote['end'],'audio',.98,
                                    {'method':'reviewed_audio_match','vote':vote})
            self.assertEqual(accept_pending(con),0)

    def test_intro_is_published_before_outro_decode_and_online_metadata(self):
        items=self.cached()
        with self.db() as con:
            own=con.execute("SELECT words_json FROM skip_auto_windows WHERE asset_key=?",(items[0]['asset_key'],)).fetchone()
            job=dict(con.execute('SELECT * FROM skip_jobs WHERE asset_key=?',(items[0]['asset_key'],)).fetchone())
        seen=[]
        def approved():
            with self.db() as con:
                self.assertTrue(con.execute("SELECT 1 FROM skip_records WHERE asset_key=? AND segment_type='intro' AND status='approved'",(items[0]['asset_key'],)).fetchone())
        def fingerprint(source,offset,length,busy,**kwargs):
            if offset:
                approved();seen.append('outro')
                return [0]*5760,125,length
            return json.loads(own['words_json']),125,length
        def online(*args):
            approved();seen.append('online');return []
        with mock.patch.object(auto,'provider_proxy',side_effect=lambda *_:contextlib.nullcontext('fixture')), \
             mock.patch.object(auto,'probe',return_value=(items[0]['duration_ms'],[])), \
             mock.patch.object(auto,'fingerprint',side_effect=fingerprint), \
             mock.patch.object(auto,'online_segments',side_effect=online):
            self.assertEqual(auto.analyze(self.db,job,busy_check)[0],'done')
        self.assertEqual(seen,['outro','online'])


if __name__=='__main__':unittest.main()
