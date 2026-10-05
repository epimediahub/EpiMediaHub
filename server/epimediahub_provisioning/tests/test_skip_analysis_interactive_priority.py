"""Playback/reference events and global language preemption against real SQLite."""
import contextlib
import json
from pathlib import Path
import sys
import time
import types
import unittest
from unittest import mock

from test_skip_analysis_schedule import ScheduleFixture
from test_skip_analysis_references import ReferenceFixture, REAL_FLASK
import skip_catalogue as catalogue
import skip_schedule as schedule
import skip_analysis_worker as worker
from skip_markers import install, migrate, now, review_record


class InteractivePriorityTests(ScheduleFixture, unittest.TestCase):
    def test_language_order_beats_playlist_order_and_foreign_playback_requests(self):
        foreign = self.add(2,'[AR] Foreign',1,1,language=2)
        self.add(2,'[TR] Turkish',1,1,language=1)
        self.add(1,'[DE] German',1,1)
        self.add(3,'[IT] Italian',1,1)
        with self.db() as con:
            schedule.request_series(con,foreign['asset_key'],'reference')
        self.assertEqual([r[1] for r in self.run_jobs()[0]],
                         ['[DE] German','[IT] Italian','[TR] Turkish','[AR] Foreign'])

    def test_started_series_preempts_backlog_and_begins_at_watched_season(self):
        self.add(2,'Backlog',1,1); self.add(2,'Backlog',1,2)
        self.run_jobs(1)
        self.add(1,'Watched',1,1)
        watched = self.add(1,'Watched',2,4)
        self.add(1,'Watched',2,5)
        with self.db() as con:
            schedule.request_series(con,watched['asset_key'])
        self.assertEqual(self.run_jobs()[0],
          [(1,'Watched',2,4),(1,'Watched',2,5),(1,'Watched',1,1),(2,'Backlog',1,2)])

    def test_reference_precedes_playback_and_only_learns_short_complete_excerpt(self):
        self.add(2,'Backlog',1,1)
        watched = self.add(1,'Watched',1,1)
        reference = self.add(3,'Reference',2,8)
        self.add(3,'Reference',2,9)
        marker = self.marker(reference,status='pending')
        with self.db() as con:
            schedule.request_series(con,watched['asset_key'])
            row = con.execute('SELECT * FROM skip_records WHERE id=?',(marker,)).fetchone()
            review_record(con,row,'approve',row['start_ms'],row['end_ms'],False)
        with mock.patch.object(worker,'provider_proxy',return_value=contextlib.nullcontext('audio')), \
             mock.patch.object(worker,'probe',return_value=(reference['duration_ms'],[])), \
             mock.patch.object(worker,'fingerprint',return_value=(list(range(80)),125.0)) as fingerprint, \
             mock.patch.object(worker,'analyze') as analyze:
            self.assertEqual(worker.process_one(self.db),'done')
            analyze.assert_not_called()
            self.assertEqual(fingerprint.call_args.args[1:3],(285043,22530))
            self.assertTrue(fingerprint.call_args.kwargs['require_complete'])
        with self.db() as con:
            self.assertIsNotNone(con.execute('SELECT 1 FROM skip_auto_reference_checks WHERE record_id=?',(marker,)).fetchone())
            before = con.execute('SELECT status,attempts FROM skip_jobs WHERE asset_key=?',(reference['asset_key'],)).fetchone()[:]
            schedule.request_series(con,reference['asset_key'],'reference')
            self.assertEqual(con.execute('SELECT status,attempts FROM skip_jobs WHERE asset_key=?',(reference['asset_key'],)).fetchone()[:],before)
        self.assertEqual([r[1] for r in self.run_jobs()[0]],['Reference','Watched','Backlog'])

    def test_repeated_playback_lookup_cannot_replace_a_reference_anchor(self):
        reference = self.add(1,'Show',2,8)
        watched = self.add(1,'Show',1,1)
        with self.db() as con:
            schedule.request_series(con,reference['asset_key'],'reference')
            for _ in range(10):
                schedule.request_series(con,watched['asset_key'])
            row = con.execute('SELECT * FROM skip_schedule_requests').fetchone()
            self.assertEqual((row['reason'],row['season'],row['episode'],row['reference_asset']),
                             ('reference',2,8,reference['asset_key']))

    def test_new_playback_request_preempts_background_at_a_cancellation_check(self):
        background = self.add(2,'Backlog',1,1)
        def analyzing(db,job,busy_factory):
            watched = self.add(1,'Watched',1,1)
            with db() as con:
                schedule.request_series(con,watched['asset_key'])
                playlist=con.execute('SELECT * FROM customer_playlists WHERE id=2').fetchone()
            self.assertTrue(busy_factory(db,[playlist])())
            raise ValueError('analysis_deferred')
        with mock.patch.object(worker,'analyze',side_effect=analyzing):
            self.assertEqual(worker.process_one(self.db),'queued')
        self.assertEqual([r[1] for r in self.run_jobs()[0]],['Watched','Backlog'])

    def test_new_reference_learning_preempts_an_older_reference_series_followup(self):
        old=self.add(2,'Old reference series',1,2)
        reference=self.add(1,'New reference series',1,8)
        with self.db() as con:
            schedule.request_series(con,old['asset_key'],'reference')
            # The old reference is already learned; only its followup remains.
            con.execute("UPDATE skip_schedule_requests SET reference_asset='learned-file' WHERE source_key=?",(old['source_key'],))
            schedule.request_series(con,reference['asset_key'],'reference')
            self.assertTrue(schedule.should_pause(con,old['asset_key']))
            self.assertEqual(schedule.current_playlist(con),1)
            self.assertFalse(schedule.should_pause(con,reference['asset_key']))

    def test_marker_corrected_during_learning_is_requeued_without_attaching_stale_audio(self):
        reference=self.add(1,'Reference',1,8)
        marker=self.marker(reference,status='pending')
        with self.db() as con:
            row=con.execute('SELECT * FROM skip_records WHERE id=?',(marker,)).fetchone()
            review_record(con,row,'approve',row['start_ms'],row['end_ms'],False)
        def corrected(*args,**kwargs):
            with self.db() as con:
                row=con.execute('SELECT * FROM skip_records WHERE id=?',(marker,)).fetchone()
                review_record(con,row,'approve',row['start_ms']+1000,row['end_ms']+1000,False)
            return list(range(80)),125.0
        with mock.patch.object(worker,'provider_proxy',return_value=contextlib.nullcontext('audio')), \
             mock.patch.object(worker,'probe',return_value=(reference['duration_ms'],[])), \
             mock.patch.object(worker,'fingerprint',side_effect=corrected):
            self.assertEqual(worker.process_one(self.db),'queued')
        with self.db() as con:
            self.assertIsNone(con.execute('SELECT 1 FROM skip_fingerprints WHERE record_id=?',(marker,)).fetchone())
            self.assertEqual(con.execute('SELECT status,attempts FROM skip_jobs').fetchone()[:],('queued',0))

    def test_higher_language_work_cancels_running_foreign_analysis_without_attempt_or_budget(self):
        foreign = self.add(2,'[GR] Foreign',1,1,language=2)
        self.marker(foreign)
        with self.db() as con:
            markers = [tuple(r) for r in con.execute('SELECT * FROM skip_records')]
        def analyzing(db,job,busy_factory):
            preferred = self.add(1,'[DE] New',1,1)
            with db() as con:
                playlist = con.execute('SELECT * FROM customer_playlists WHERE id=2').fetchone()
            self.assertTrue(busy_factory(db,[playlist])())
            raise ValueError('analysis_deferred')
        with mock.patch.object(worker,'analyze',side_effect=analyzing):
            self.assertEqual(worker.process_one(self.db),'queued')
        with self.db() as con:
            self.assertEqual(con.execute('SELECT status,attempts FROM skip_jobs WHERE asset_key=?',(foreign['asset_key'],)).fetchone()[:],('queued',0))
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0],0)
            self.assertEqual([tuple(r) for r in con.execute('SELECT * FROM skip_records')],markers)
        self.assertEqual([r[1] for r in self.run_jobs()[0]],['[DE] New','[GR] Foreign'])

    def test_busy_account_does_not_hold_up_another_idle_account_in_same_language_stage(self):
        with self.db() as con:
            config = json.loads(con.execute('SELECT config_json FROM customer_playlists WHERE id=1').fetchone()[0])
            config['xtream_username'] = 'other-account'
            con.execute('UPDATE customer_playlists SET config_json=? WHERE id=1',(json.dumps(config),))
            con.execute('INSERT INTO skip_presence VALUES(1,2,?)',(int(time.time())+90,))
        self.add(2,'Busy',1,1)
        self.add(1,'Idle',1,1)
        self.add(3,'[TR] Later',1,1,language=1)
        seen,statuses = self.run_jobs()
        self.assertEqual(seen,[(1,'Idle',1,1)])
        self.assertEqual(statuses,['no_match','queued'])

    def test_language_label_recognition_keeps_turkish_between_preferred_and_other(self):
        for label in ('[TR] Show','TR: Show','[TUR] Show','TÜRKÇE - Show'):
            self.assertEqual(catalogue.language_priority({'name':label}),1)
        for label in ('Türkische Serien','TR Netflix Serien'):
            self.assertEqual(catalogue.language_priority({'category_name':label}),1)
        for label in ('[AR] Show','[GR] Show','[EL] Show','Unknown'):
            self.assertEqual(catalogue.language_priority({'name':label}),2)
        self.assertEqual(catalogue.language_priority({'audio_languages':['tr','it']}),0)

    def test_migration_of_old_binary_ranks_preserves_jobs_markers_focus_and_quota(self):
        german = self.add(1,'[DE] German',1,1)
        turkish = self.add(2,'[TR] Turkish',1,1,language=1)
        greek = self.add(3,'[GR] Greek',1,1,language=2)
        self.marker(greek)
        with self.db() as con:
            schedule.remember(con,con.execute('SELECT * FROM skip_jobs WHERE asset_key=?',(greek['asset_key'],)).fetchone())
            con.execute('INSERT INTO skip_analysis_budget VALUES(?,95)',(now()[:10],))
            jobs = [tuple(r) for r in con.execute('SELECT * FROM skip_jobs')]
            markers = [tuple(r) for r in con.execute('SELECT * FROM skip_records')]
            con.executescript('''DROP TABLE skip_language_priority;
              CREATE TABLE skip_language_priority(asset_key TEXT PRIMARY KEY REFERENCES skip_assets(asset_key) ON DELETE CASCADE,
                priority INTEGER NOT NULL CHECK(priority IN (0,1)));
              DROP TABLE skip_catalogue_languages;
              CREATE TABLE skip_catalogue_languages(playlist_id INTEGER NOT NULL REFERENCES customer_playlists(id) ON DELETE CASCADE,
                series_id TEXT NOT NULL,priority INTEGER NOT NULL CHECK(priority IN (0,1)),PRIMARY KEY(playlist_id,series_id));''')
            con.executemany('INSERT INTO skip_language_priority VALUES(?,?)',
                [(german['asset_key'],0),(turkish['asset_key'],1),(greek['asset_key'],1)])
            con.execute('DELETE FROM skip_auto_maintenance WHERE name=?',(catalogue.LANGUAGE_POLICY,))
            migrate(con); migrate(con)
            self.assertEqual(dict(con.execute('SELECT asset_key,priority FROM skip_language_priority')),
                {german['asset_key']:0,turkish['asset_key']:1,greek['asset_key']:2})
            self.assertEqual([tuple(r) for r in con.execute('SELECT * FROM skip_jobs')],jobs)
            self.assertEqual([tuple(r) for r in con.execute('SELECT * FROM skip_records')],markers)
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0],95)
            self.assertEqual(schedule.current_playlist(con),1)


@unittest.skipUnless(REAL_FLASK,'Flask required')
class PriorityEventRoutes(ReferenceFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        site = REAL_FLASK('priority-event-fixture')
        site.secret_key='fixture-session'
        site.add_url_rule('/health','health',lambda:site.json.response({'status':'ok'}))
        backend=types.ModuleType('app'); backend.digest=lambda x:x; backend.web_auth=lambda:None
        with mock.patch.dict(sys.modules,{'app':backend}):
            install(site,self.db)
        self.client=site.test_client()
        self.headers={'Authorization':'Bearer fixture-token'}

    def test_authenticated_lookup_registers_series_priority_without_an_app_update(self):
        response=self.client.post('/v1/device/skip/lookup',json=self.seed,headers=self.headers)
        self.assertEqual(response.status_code,200)
        with self.db() as con:
            row=con.execute('SELECT * FROM skip_schedule_requests').fetchone()
            self.assertEqual((row['source_key'],row['season'],row['episode'],row['reason']),
              (self.seed['source_key'],2,12,'playback'))

    def test_foreign_or_unauthenticated_lookup_cannot_boost_queue(self):
        self.assertEqual(self.client.post('/v1/device/skip/lookup',json=self.seed).status_code,401)
        response=self.client.post('/v1/device/skip/lookup',json=self.seed|{'playlist_id':2},headers=self.headers)
        self.assertEqual(response.get_json()['analysis'],'unavailable')
        with self.db() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_schedule_requests').fetchone()[0],0)

    def test_new_customer_marker_is_prioritized_when_automatic_acceptance_is_enabled(self):
        with self.db() as con:
            con.execute('UPDATE skip_release_settings SET enabled=1 WHERE playlist_id=1')
        raw=self.seed|dict(segment_type='intro',start_ms=283043,end_ms=309573)
        response=self.client.post('/v1/device/skip/submit',json=raw,headers=self.headers)
        self.assertEqual(response.get_json()['status'],'approved')
        with self.db() as con:
            self.assertEqual(con.execute('SELECT reason,reference_asset FROM skip_schedule_requests').fetchone()[:],
                             ('reference',self.seed['asset_key']))
