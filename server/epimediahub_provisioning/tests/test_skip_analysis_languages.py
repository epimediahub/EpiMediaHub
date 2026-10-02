"""Real queue/inventory ordering without live providers or extra audio downloads."""
from __future__ import annotations

import json
import time
import unittest
from unittest import mock

from test_skip_analysis_catalogue import CatalogueFixture, START
from test_skip_analysis_automation import AutomationFixture
import skip_catalogue as catalogue
import skip_automation as auto
from skip_analysis_worker import busy_check, process_one
from skip_markers import migrate, now


class LanguageLabels(unittest.TestCase):
    def test_provider_title_tags_recognize_both_languages_without_guessing_plain_titles(self):
        for name in ('[DE] Dark', '(GER) Dark', 'DE: Dark', '[HD] [ITA] Gomorra',
                     'IT | Gomorra', 'Gomorra [IT] [4K]', '[DE/IT] Show', 'ITALIANO - Show'):
            with self.subTest(name=name):
                self.assertEqual(catalogue.language_priority({'name': name}), 0)
        for name in ('It', 'It Takes Two', 'German Crime Story', 'Deutschland 83',
                     'Digital Show', '[HD] Story', 'DEAD - Show', 'Unknown', '[EN] Dark'):
            with self.subTest(name=name):
                self.assertEqual(catalogue.language_priority({'name': name}), 1)

    def test_declared_audio_language_overrides_title_category_and_original_language(self):
        self.assertEqual(catalogue.language_priority({'audio_language': 'en', 'name': '[DE] Show',
                                                     'category_name': 'DE SERIES'}), 1)
        self.assertEqual(catalogue.language_priority({'audio_languages': ['en', {'iso_639_1': 'it'}]}), 0)
        self.assertEqual(catalogue.language_priority({'language': 'de-DE', 'original_language': 'en'}), 0)
        self.assertEqual(catalogue.language_priority({'original_language': 'it', 'country': 'DE'}), 1)
        self.assertEqual(catalogue.language_priority({'language': False, 'audio_languages': ['not-a-language']}), 1)

    def test_provider_category_labels_and_ambiguous_categories(self):
        rows = [{'category_id': 1, 'category_name': 'DE | Serien'},
                {'category_id': 2, 'category_name': 'SERIE TV ITALIA'},
                {'category_id': 3, 'category_name': 'English series'},
                {'category_id': 4, 'category_name': 'Series de España'},
                {'category_id': 5, 'category_name': 'DEUTSCHE SERIEN'},
                {'category_id': 5, 'category_name': 'English series'}]
        ranks = catalogue.category_priorities(rows)
        self.assertEqual(ranks, {'1': 0, '2': 0, '3': 1, '4': 1})
        self.assertEqual(catalogue.language_priority({'category_ids': ['2', '3']}, ranks), 0)
        self.assertEqual(catalogue.language_priority({'category_id': 999}, ranks), 1)

    def test_country_prefixes_include_the_users_lowercase_and_netflix_category_examples(self):
        for name in ('de Serien', 'deutsche Seiten', 'DE: Netflix Serien', 'it Serie',
                     'IT: Netflix Serie', 'Italiane Netflix', 'SERIE TV ITALIA'):
            with self.subTest(name=name):
                self.assertEqual(catalogue.language_priority({'category_name': name}), 0)
        for name in ('Series de España', 'Séries de France', 'en Netflix Serien'):
            with self.subTest(name=name):
                self.assertEqual(catalogue.language_priority({'category_name': name}), 1)

    def test_storage_retains_only_priority_and_existing_safe_metadata(self):
        row = {'series_id': 7, 'name': 'Show', 'audio_languages': [{'iso_639_1': 'de', 'secret': 'PRIVATE'}],
               'category_name': 'https://PRIVATE', 'password': 'PRIVATE', 'original_language': 'en'}
        data = catalogue.listing([row])[0][0]
        self.assertEqual(data['language_priority'], 0)
        self.assertNotIn('PRIVATE', json.dumps(data))
        self.assertEqual(set(data), {'series_id', 'name', 'year', 'release', 'language_priority'})


class LanguageQueueTests(CatalogueFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.categories = []
        self.listing.append({'series_id': 503, 'name': 'IT | Gomorra', 'year': '2014', 'last_modified': 2})
        self.infos['503'] = {'info': {'name': 'IT | Gomorra', 'year': '2014'}, 'episodes': {
            '1': [{'id': 301, 'episode_num': 1, 'container_extension': 'mkv'}]}}

    def provider(self, playlist, action, busy, **params):
        if action == 'get_series_categories':
            if isinstance(self.categories, Exception):
                raise self.categories
            return self.categories
        return super().provider(playlist, action, busy, **params)

    def run_audio(self, count=1):
        with mock.patch.object(catalogue, 'advance', return_value='idle'), \
             mock.patch.object(auto, 'discover_one', return_value='idle'), \
             mock.patch('skip_analysis_worker.analyze', return_value=('no_match', 'checked')) as analyze:
            for _ in range(count):
                self.assertEqual(process_one(self.db), 'no_match')
        with self.db() as con:
            return [con.execute('SELECT stream_id FROM skip_assets WHERE asset_key=?',
                                (call.args[1]['asset_key'],)).fetchone()[0] for call in analyze.call_args_list]

    def test_full_inventory_fetches_de_and_it_before_other_series(self):
        _, fetch = self.advance()
        ids = [call.kwargs['series_id'] for call in fetch.call_args_list if call.args[1] == 'get_series_info']
        self.assertEqual(ids, ['501', '503', '502'])
        with self.db() as con:
            rows = con.execute('SELECT stream_id,priority FROM skip_assets JOIN skip_language_priority USING(asset_key)').fetchall()
            self.assertEqual(dict(rows), {'101': 0, '102': 0, '103': 0, '110': 0, '301': 0, '201': 1})

    def test_both_preferred_languages_run_before_new_other_language_and_rest_is_not_excluded(self):
        self.advance()
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET updated_at='2020-01-01T00:00:00' WHERE asset_key IN (SELECT asset_key FROM skip_assets WHERE stream_id='201')")
            con.execute("UPDATE skip_catalogue_priority SET priority=0 WHERE asset_key IN (SELECT asset_key FROM skip_assets WHERE stream_id='201')")
        streams = self.run_audio(6)
        self.assertEqual(set(streams[:5]), {'101', '102', '103', '110', '301'})
        self.assertEqual(streams[-1], '201')

    def test_new_italian_episode_keeps_new_episode_priority_inside_preferred_group(self):
        self.advance()
        self.listing[2]['last_modified'] += 1
        self.infos['503']['episodes']['1'].append({'id': 302, 'episode_num': 2, 'container_extension': 'mkv'})
        self.advance(catalogue.next_night(START))
        self.assertEqual(self.run_audio(), ['302'])

    def test_categories_can_prioritize_an_untagged_italian_series(self):
        self.listing[1].update(category_id=22)
        self.categories = [{'category_id': 22, 'category_name': 'SERIE ITALIANE'}]
        self.advance()
        with self.db() as con:
            rank = con.execute("SELECT priority FROM skip_language_priority JOIN skip_assets USING(asset_key) WHERE stream_id='201'").fetchone()[0]
        self.assertEqual(rank, 0)

    def test_missing_category_api_falls_back_to_tags_and_processes_unknown_series(self):
        self.listing[1].update(category_id=22)
        self.categories = ValueError('provider_http_404')
        self.advance()
        self.assertEqual(self.run_audio(6)[-1], '201')

    def test_category_lookup_is_deferred_during_playback(self):
        self.listing[1].update(category_id=22)
        self.categories = ValueError('analysis_deferred')
        self.assertEqual(self.advance()[0], 'queued')
        with self.db() as con:
            self.assertFalse(con.execute('SELECT 1 FROM skip_catalogue_series').fetchone())

    def test_migration_reorders_existing_queue_without_requeuing_finished_work_or_resetting_budget(self):
        self.advance()
        self.finish_jobs()
        self.marker()
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='queued',attempts=2,detail='existing' WHERE asset_key IN (SELECT asset_key FROM skip_assets WHERE stream_id='301')")
            con.execute('INSERT INTO skip_analysis_budget VALUES(?,95)', (now()[:10],))
            before = [tuple(row) for row in con.execute('SELECT * FROM skip_jobs ORDER BY id')]
            records = [tuple(row) for row in con.execute('SELECT * FROM skip_records')]
            for row in con.execute('SELECT playlist_id,series_id,payload_json FROM skip_catalogue_series').fetchall():
                data = json.loads(row['payload_json']); data.pop('language_priority')
                con.execute('UPDATE skip_catalogue_series SET payload_json=? WHERE playlist_id=? AND series_id=?',
                            (json.dumps(data), row['playlist_id'], row['series_id']))
            con.execute('DROP TABLE skip_language_priority')
            con.execute('DROP TABLE skip_catalogue_languages')
            con.execute('DELETE FROM skip_auto_maintenance WHERE name=?', (catalogue.LANGUAGE_POLICY,))
            migrate(con); migrate(con)
            self.assertEqual([tuple(row) for row in con.execute('SELECT * FROM skip_jobs ORDER BY id')], before)
            self.assertEqual([tuple(row) for row in con.execute('SELECT * FROM skip_records')], records)
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0], 95)
            self.assertEqual(con.execute("SELECT priority FROM skip_language_priority JOIN skip_assets USING(asset_key) WHERE stream_id='301'").fetchone()[0], 0)

    def test_language_metadata_change_updates_rank_without_reanalysing_unchanged_audio(self):
        self.advance(); before = self.finish_jobs()
        self.listing[0]['audio_language'] = 'en'
        self.infos['501']['info']['audio_language'] = 'en'
        self.advance(catalogue.next_night(START))
        with self.db() as con:
            self.assertEqual([tuple(row) for row in con.execute('SELECT * FROM skip_jobs ORDER BY id')], before)
            self.assertEqual(con.execute("SELECT priority FROM skip_language_priority JOIN skip_assets USING(asset_key) WHERE stream_id='101'").fetchone()[0], 1)

    def test_existing_catalogue_refreshes_categories_without_resetting_cursor_schedule_jobs_or_markers(self):
        self.advance(); jobs = self.finish_jobs(); self.marker()
        with self.db() as con:
            state = con.execute('SELECT * FROM skip_catalogue_runs').fetchone()[:]
            records = [row[:] for row in con.execute('SELECT * FROM skip_records')]
            con.execute('UPDATE skip_catalogue_language_refresh SET checked_at=0')
        self.listing[1]['category_id'] = 22
        self.categories = [{'category_id': 22, 'category_name': 'de Serien'}]
        result, fetch = self.advance(START + 60)
        self.assertEqual(result, 'language_refreshed')
        self.assertEqual([call.args[1] for call in fetch.call_args_list], ['get_series', 'get_series_categories'])
        with self.db() as con:
            self.assertEqual(con.execute('SELECT * FROM skip_catalogue_runs').fetchone()[:], state)
            self.assertEqual([row[:] for row in con.execute('SELECT * FROM skip_records')], records)
            self.assertEqual([row[:] for row in con.execute('SELECT * FROM skip_jobs ORDER BY id')], jobs)
            self.assertEqual(con.execute("SELECT priority FROM skip_language_priority JOIN skip_assets USING(asset_key) WHERE stream_id='201'").fetchone()[0], 0)
        self.advance(START + 120)[1].assert_not_called()

    def test_failed_one_time_language_refresh_preserves_existing_run_and_retries_metadata_later(self):
        self.advance()
        with self.db() as con:
            state = con.execute('SELECT * FROM skip_catalogue_runs').fetchone()[:]
            con.execute('UPDATE skip_catalogue_language_refresh SET checked_at=0')
        with mock.patch.object(auto, 'provider_api', side_effect=ValueError('provider_dns')):
            self.assertEqual(catalogue.advance(self.db, busy_check, START + 60), 'failed')
        with self.db() as con:
            self.assertEqual(con.execute('SELECT * FROM skip_catalogue_runs').fetchone()[:], state)
            self.assertEqual(con.execute('SELECT retry_at FROM skip_catalogue_language_refresh').fetchone()[0], START + 3660)

    def test_partial_catalogue_language_refresh_preserves_pending_generation(self):
        self.advance(max_steps=1)
        with self.db() as con:
            state = con.execute('SELECT * FROM skip_catalogue_runs').fetchone()[:]
            pending = [row[:] for row in con.execute('SELECT series_id,pending_generation FROM skip_catalogue_series ORDER BY series_id')]
            con.execute('UPDATE skip_catalogue_language_refresh SET checked_at=0')
        self.advance(START + 60, max_steps=1)
        with self.db() as con:
            self.assertEqual(con.execute('SELECT * FROM skip_catalogue_runs').fetchone()[:], state)
            self.assertEqual([row[:] for row in con.execute('SELECT series_id,pending_generation FROM skip_catalogue_series ORDER BY series_id')], pending)

    def test_preferred_series_in_another_playlist_is_inventoried_first(self):
        with self.db() as con:
            con.execute("INSERT INTO skip_auto_settings VALUES(2,1,0,?)", (now(),))
            catalogue.start(con, 2)
        calls = []
        def fetch(playlist, action, busy, **params):
            calls.append((playlist['id'], action))
            if action == 'get_series':
                return [self.listing[1]] if playlist['id'] == 1 else [self.listing[2]]
            return self.infos[params['series_id']]
        with mock.patch.object(auto, 'provider_api', side_effect=fetch):
            catalogue.advance(self.db, busy_check, START, max_steps=3)
        self.assertEqual(calls, [(1, 'get_series'), (2, 'get_series'), (2, 'get_series_info')])

    def test_old_other_language_queue_waits_for_known_preferred_inventory(self):
        self.advance(max_steps=1)
        self.registered(self.descriptor('999', 99, source_key='c' * 64))
        with mock.patch.object(catalogue, 'advance', return_value='queued'), \
             mock.patch.object(auto, 'discover_one', return_value='idle'), \
             mock.patch('skip_analysis_worker.analyze') as analyze:
            self.assertEqual(process_one(self.db), 'catalogue_pending')
            analyze.assert_not_called()
        with self.db() as con:
            self.assertEqual(con.execute('SELECT status,attempts FROM skip_jobs').fetchone()[:], ('queued', 0))
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0], 0)

    def test_language_preference_does_not_bypass_the_daily_limit(self):
        self.advance()
        with self.db() as con:
            con.execute('INSERT INTO skip_analysis_budget VALUES(?,96)', (now()[:10],))
        with mock.patch.object(catalogue, 'advance', return_value='idle'), \
             mock.patch('skip_analysis_worker.analyze') as analyze:
            self.assertEqual(process_one(self.db), 'daily_limit')
            analyze.assert_not_called()


class OnlineLanguageTests(AutomationFixture, unittest.TestCase):
    def test_due_metadata_retries_use_the_same_language_preference_without_touching_audio(self):
        other = self.descriptor('90', 1, source_key='c' * 64)
        self.registered(other); self.registered(self.target)
        with self.db() as con:
            con.execute('UPDATE skip_auto_settings SET online_enabled=1')
            con.execute("UPDATE skip_jobs SET status='no_match',attempts=2")
            con.execute('INSERT INTO skip_auto_online_retry VALUES(?,?,?,?)', (other['asset_key'], 'theintrodb', 'provider_http_503', 1))
            con.execute('INSERT INTO skip_auto_online_retry VALUES(?,?,?,?)', (self.target['asset_key'], 'theintrodb', 'provider_http_503', 2))
            catalogue.set_asset_language(con, self.target['asset_key'], 0)
        with mock.patch.object(auto, 'online_segments', return_value=[]) as online:
            self.assertEqual(auto.refresh_online_one(self.db, busy_check), 'online_checked')
        self.assertEqual(online.call_args.args[1]['asset_key'], self.target['asset_key'])
        with self.db() as con:
            self.assertEqual([row[:] for row in con.execute('SELECT status,attempts FROM skip_jobs')], [('no_match', 2), ('no_match', 2)])


if __name__ == '__main__':
    unittest.main()
