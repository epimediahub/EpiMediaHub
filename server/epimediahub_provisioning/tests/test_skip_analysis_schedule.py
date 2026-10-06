"""Playlist/series completion and resume against real SQLite and the worker."""
import hashlib
import json
from pathlib import Path
import sys
import time
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_skip_analysis_automation as fixtures
import skip_automation as auto
import skip_catalogue as catalogue
import skip_schedule as schedule
from skip_analysis_worker import process_one, process_batch, busy_check
from skip_markers import now, migrate, install


class ScheduleFixture(fixtures.AutomationFixture):
    def setUp(self):
        super().setUp()
        with self.db() as con:
            for identifier, name in ((1, 'IPTV The Best'), (2, '4K'), (3, 'FE IPTV')):
                con.execute('UPDATE customer_playlists SET name=? WHERE id=?', (name, identifier))
                con.execute('UPDATE skip_analysis_sources SET enabled=1 WHERE playlist_id=?', (identifier,))
                con.execute('INSERT OR REPLACE INTO skip_auto_settings VALUES(?,1,0,?)', (identifier, now()))

    def add(self, playlist, title, season, episode, language=0):
        with self.db() as con:
            stream = str(1000 + con.execute('SELECT COUNT(*) FROM skip_assets').fetchone()[0])
            key = hashlib.sha256(f'{playlist}:{title}'.encode()).hexdigest()
            data = self.descriptor(stream, episode, playlist_id=playlist, source_key=key,
                                   title=title, season=season)
            con.execute('INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                        (data['asset_key'], key, playlist, stream, 'mkv', 'episode', data['duration_ms'],
                         season, episode, title, '2009', now()))
            con.execute('INSERT INTO skip_auto_assets VALUES(?,?)', (data['asset_key'], now()))
            con.execute("INSERT INTO skip_jobs(asset_key,status,created_at,updated_at) VALUES(?,'queued',?,?)",
                        (data['asset_key'], now(), now()))
            catalogue.set_asset_language(con, data['asset_key'], language)
        return data

    def asset(self, job):
        with self.db() as con:
            return dict(con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (job['asset_key'],)).fetchone())

    def run_jobs(self, count=8, result=('no_match', 'checked')):
        seen = []
        def analyze(_db, job, **kwargs):
            row = self.asset(job)
            seen.append((row['playlist_id'], row['title'], row['season'], row['episode']))
            return result
        with mock.patch.object(auto, 'provider_api', side_effect=AssertionError('queued audio must not scan more series')), \
             mock.patch('skip_analysis_worker.analyze', side_effect=analyze):
            statuses = process_batch(self.db, max_jobs=count)
        return seen, statuses


class ScheduleTests(ScheduleFixture, unittest.TestCase):
    def test_language_stages_apply_globally_with_playlist_order_inside_each_stage(self):
        self.add(3, 'FE preferred', 1, 1)
        self.add(1, 'Best preferred', 1, 1)
        self.add(2, '4K other', 1, 1, language=1)
        self.add(2, '4K preferred', 1, 2)
        self.add(2, '4K preferred', 1, 1)
        seen, _ = self.run_jobs()
        self.assertEqual(seen, [(2,'4K preferred',1,1),(2,'4K preferred',1,2),
                                (1,'Best preferred',1,1),(3,'FE preferred',1,1),(2,'4K other',1,1)])

    def test_series_is_finished_in_numeric_season_episode_order_across_batches(self):
        self.add(2, 'First', 10, 2)
        self.add(2, 'Second', 1, 1)
        self.add(2, 'First', 2, 10)
        self.add(2, 'First', 2, 2)
        self.add(2, 'First', 1, 1)
        seen, _ = self.run_jobs(2)
        with self.db() as con:
            migrate(con)  # A fresh process/schema startup must retain focus.
        rest, _ = self.run_jobs()
        self.assertEqual(seen + rest, [(2,'First',1,1),(2,'First',2,2),(2,'First',2,10),
                                       (2,'First',10,2),(2,'Second',1,1)])

    def test_new_high_priority_series_does_not_interrupt_active_series(self):
        self.add(2, 'First', 1, 1); self.add(2, 'First', 1, 2)
        self.run_jobs(1)
        new = self.add(2, 'New', 1, 1)
        with self.db() as con:
            con.execute('INSERT INTO skip_catalogue_priority VALUES(?,0)', (new['asset_key'],))
        seen, _ = self.run_jobs()
        self.assertEqual([r[1] for r in seen], ['First', 'New'])

    def test_playback_pause_stops_batch_and_resumes_same_episode_without_budget(self):
        self.add(2, 'First', 1, 1); self.add(2, 'First', 1, 2); self.add(1, 'Later', 1, 1)
        seen, statuses = self.run_jobs(result=('queued', 'playback'))
        self.assertEqual((seen, statuses), ([(2,'First',1,1)], ['queued']))
        with self.db() as con:
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT SUM(attempts) FROM skip_jobs').fetchone()[0], 0)
        seen, _ = self.run_jobs(1)
        self.assertEqual(seen, [(2,'First',1,1)])

    def test_failed_episode_remains_visible_and_does_not_block_rest_of_series(self):
        first = self.add(2, 'First', 1, 1)
        self.add(2, 'First', 1, 2); self.add(1, 'Later', 1, 1)
        with mock.patch('skip_analysis_worker.analyze', side_effect=ValueError('provider_http_404')):
            self.assertEqual(process_one(self.db), 'failed')
        seen, _ = self.run_jobs()
        self.assertEqual(seen, [(2,'First',1,2),(1,'Later',1,1)])
        with self.db() as con:
            self.assertEqual(con.execute('SELECT status,attempts FROM skip_jobs WHERE asset_key=?',
                                         (first['asset_key'],)).fetchone()[:], ('failed',1))

    def test_explicit_playlist_order_applies_next_job_without_resetting_markers_or_500_budget(self):
        first = self.add(2, 'First', 1, 1); self.add(2, 'First', 1, 2); self.add(3, 'FE', 1, 1)
        self.run_jobs(1)
        with self.db() as con:
            con.execute("INSERT OR REPLACE INTO skip_catalogue_config VALUES('daily_limit',500,?)", (now(),))
            before = [row[:] for row in con.execute('SELECT * FROM skip_jobs')]
            schedule.save_order(con, [3,1,2])
            self.assertEqual([row[:] for row in con.execute('SELECT * FROM skip_jobs')], before)
            self.assertEqual(con.execute("SELECT value FROM skip_catalogue_config WHERE name='daily_limit'").fetchone()[0],500)
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0],1)
        self.assertEqual(self.run_jobs(1)[0], [(3,'FE',1,1)])

    def test_disabled_playlist_or_customer_is_skipped_without_opening_provider(self):
        self.add(2, '4K', 1, 1); self.add(1, 'Best', 1, 1); self.add(3, 'FE', 1, 1)
        with self.db() as con:
            con.execute('UPDATE customers SET enabled=0 WHERE id=2')
            con.execute('UPDATE skip_analysis_sources SET enabled=0 WHERE playlist_id=3')
        self.assertEqual(self.run_jobs()[0], [(1,'Best',1,1)])

    def test_new_preferred_series_preempts_lower_language_stage(self):
        self.add(2, 'Other', 1, 1, language=1); self.add(2, 'Other', 1, 2, language=1)
        self.run_jobs(1)
        self.add(2, 'Preferred', 1, 1)
        self.assertEqual([r[1] for r in self.run_jobs()[0]], ['Preferred','Other'])

    def test_new_jobs_in_an_earlier_playlist_do_not_interrupt_active_playlist(self):
        self.add(1,'Best',1,1); self.add(1,'Best',1,2)
        self.run_jobs(1)
        self.add(2,'New 4K',1,1)
        self.assertEqual([r[0] for r in self.run_jobs()[0]], [1,2])

    def test_500_daily_budget_is_used_without_legacy_24_limit_or_reset(self):
        for episode in range(1,31): self.add(2,'First',1,episode)
        with self.db() as con:
            catalogue.start(con,2)
            con.execute("INSERT OR REPLACE INTO skip_catalogue_config VALUES('daily_limit',500,?)", (now(),))
        for _ in range(3): self.assertEqual(self.run_jobs(8)[1], ['no_match']*8)
        self.assertEqual(self.run_jobs(1)[1], ['no_match'])
        with self.db() as con:
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0],25)
            self.assertEqual(catalogue.daily_limit(con),500)
            self.assertEqual(schedule.current_playlist(con),2)

    def test_real_playback_presence_pauses_before_any_provider_request(self):
        self.add(2,'First',1,1); self.add(1,'Later',1,1)
        with self.db() as con:
            con.execute('INSERT INTO skip_presence VALUES(?,?,?)',(1,1,int(time.time())+90))
        with mock.patch.object(auto,'provider_proxy',side_effect=AssertionError('playback must prevent provider read')):
            self.assertEqual(process_batch(self.db,max_jobs=8),['queued'])
        with self.db() as con:
            self.assertEqual(con.execute('SELECT SUM(attempts) FROM skip_jobs').fetchone()[0],0)
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0],0)
            self.assertEqual(schedule.current_playlist(con),2)

    def test_preferred_inventory_in_other_playlist_holds_lower_language_jobs(self):
        self.add(2, '4K other', 1, 1, language=1)
        with self.db() as con:
            catalogue.start(con,1)
            con.execute("INSERT INTO skip_catalogue_series VALUES(1,'501','{}','sig',0,1,1,0,'','')")
            catalogue.set_series_language(con,1,'501',0)
            con.execute("UPDATE skip_catalogue_runs SET phase='full',generation=1 WHERE playlist_id=1")
        with mock.patch.object(catalogue,'advance',return_value='queued'), mock.patch('skip_analysis_worker.analyze') as analyze:
            self.assertEqual(process_one(self.db),'preferred_pending')
            analyze.assert_not_called()

    def test_queued_preferred_jobs_run_before_fetching_another_playlist_inventory(self):
        self.add(1, 'Best', 1, 1)
        with self.db() as con:
            catalogue.start(con,2)
        calls, analyzed = [], []
        def provider(playlist, action, busy, **params):
            calls.append((playlist['id'],action))
            if action=='get_series': return [{'series_id':501,'name':'[DE] 4K series'}]
            return {'info':{'name':'[DE] 4K series'},'episodes':{'1':[
                {'id':3001,'episode_num':1,'container_extension':'mkv'},
                {'id':3002,'episode_num':2,'container_extension':'mkv'}]}}
        def analyze(_db,job,**kwargs):
            analyzed.append(self.asset(job)['playlist_id'])
            return 'no_match','checked'
        with mock.patch.object(auto,'provider_api',side_effect=provider), \
             mock.patch('skip_analysis_worker.analyze',side_effect=analyze):
            self.assertEqual(process_one(self.db),'no_match')
            self.assertEqual(calls,[])
            self.assertEqual(process_one(self.db),'no_match')
            self.assertEqual(calls,[(2,'get_series'),(2,'get_series_info')])
            self.assertEqual(len(calls),2)
            self.assertEqual(process_one(self.db),'no_match')
        self.assertEqual(analyzed,[1,2,2])
        with mock.patch.object(auto,'provider_api',side_effect=provider):
            self.assertEqual(process_one(self.db),'idle')
        with self.db() as con:
            self.assertEqual(con.execute('SELECT full_done FROM skip_catalogue_runs WHERE playlist_id=2').fetchone()[0],1)

    def test_preferred_inventory_in_current_playlist_waits_before_other_languages(self):
        self.add(2,'Other',1,1,language=1)
        with self.db() as con:
            catalogue.start(con,2)
            con.execute("INSERT INTO skip_catalogue_series VALUES(2,'501','{}','sig',0,1,1,0,'','')")
            catalogue.set_series_language(con,2,'501',0)
            con.execute("UPDATE skip_catalogue_runs SET phase='full',generation=1 WHERE playlist_id=2")
        with mock.patch.object(catalogue,'advance',return_value='queued'), \
             mock.patch('skip_analysis_worker.analyze') as analyze:
            self.assertEqual(process_one(self.db),'preferred_pending'); analyze.assert_not_called()

    def test_migration_is_idempotent_and_keeps_focus_order_jobs_and_budget(self):
        self.add(2,'First',1,1); self.add(2,'First',1,2)
        self.run_jobs(1)
        with self.db() as con:
            schedule.save_order(con,[2,1,3])
            rows = [row[:] for row in con.execute('SELECT * FROM skip_jobs')]
            for _ in range(2): migrate(con)
            self.assertEqual([r['id'] for r in schedule.playlists(con)],[2,1,3])
            self.assertEqual([row[:] for row in con.execute('SELECT * FROM skip_jobs')],rows)
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0],1)


@unittest.skipUnless(fixtures.REAL_FLASK, 'Flask required')
class ScheduleApiTests(ScheduleFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        with self.db() as con:
            con.execute("ALTER TABLE customers ADD COLUMN name TEXT NOT NULL DEFAULT 'Customer'")
        site = fixtures.REAL_FLASK('schedule-fixture',template_folder=str(Path(__file__).resolve().parents[1]/'templates'))
        site.secret_key='fixture-session'
        site.add_url_rule('/dashboard','dashboard',lambda:'Dashboard')
        site.add_url_rule('/health','health',lambda:site.json.response({'status':'ok'}))
        backend=types.ModuleType('app'); backend.digest=lambda x:x; backend.web_auth=lambda:None
        with mock.patch.dict(sys.modules,{'app':backend}): install(site,self.db)
        self.client=site.test_client()
        with self.client.session_transaction() as session: session['skip_csrf']='fixture-csrf'

    def refreshed_view(self):
        from skip_dashboard_stats import refresh
        with self.db() as con:refresh(con,force=True)
        return self.client.get('/admin/skip')

    def test_dashboard_shows_playlist_series_episode_and_editable_order(self):
        self.add(2,'First',2,1)
        response=self.refreshed_view()
        self.assertEqual(response.status_code,200)
        text=response.get_data(as_text=True)
        self.assertIn('Aktuelle Playlist: 4K',text)
        self.assertIn('Staffel 2 · Folge 1',text)
        self.assertIn('Bearbeitet: 0 / 1',text)
        self.assertLess(text.index('name="position_2"'),text.index('name="position_1"'))
        self.assertLess(text.index('name="position_1"'),text.index('name="position_3"'))

    def test_order_form_saves_and_rejects_csrf_duplicates_missing_and_foreign_playlists(self):
        data=dict(csrf='fixture-csrf',position_1='2',position_2='3',position_3='1')
        self.assertEqual(self.client.post('/admin/skip/order',data=data|{'csrf':'bad'}).status_code,403)
        for invalid in (data|{'position_1':'1'},data|{'position_2':'0'},data|{'position_99':'4'},
                        {k:v for k,v in data.items() if k!='position_2'}):
            self.assertEqual(self.client.post('/admin/skip/order',data=invalid).status_code,400)
        self.assertEqual(self.client.post('/admin/skip/order',data=data).status_code,302)
        with self.db() as con: self.assertEqual([r['id'] for r in schedule.playlists(con)],[3,1,2])

    def test_current_progress_keeps_failed_and_review_results_distinct(self):
        self.add(2,'First',1,1); self.add(2,'First',1,2); self.add(2,'First',1,3)
        self.run_jobs(1,result=('failed','provider'))
        self.run_jobs(1,result=('review','proposal'))
        response=self.refreshed_view()
        self.assertEqual(response.status_code,200)
        text=response.get_data(as_text=True)
        self.assertIn('Bearbeitet: 2 / 3',text)
        self.assertIn('1 Vorschläge zur Prüfung',text)
        self.assertIn('1 Zugriffs-/Referenzprobleme',text)

    def test_order_change_during_job_still_shows_actual_running_playlist(self):
        active=self.add(2,'Running 4K',1,1); self.add(3,'FE',1,1)
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='running' WHERE asset_key=?",(active['asset_key'],))
            schedule.save_order(con,[3,1,2])
            self.assertEqual(schedule.overview(con)['current']['playlist_id'],2)
