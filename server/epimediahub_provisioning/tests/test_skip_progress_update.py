"""Sequential timer batches, audio reuse and immediate, session-bound releases."""
import json
import random
import unittest
from unittest import mock
import contextlib

from test_skip_analysis_automation import AutomationFixture
import test_skip_markers as marker_tests
import skip_automation as auto
import skip_catalogue as catalogue
from skip_analysis_worker import process_batch, process_one, busy_check
from skip_markers import now
db = marker_tests.db


class BatchTests(AutomationFixture, unittest.TestCase):
    def ready(self):
        for stream, episode in [('81', 12), ('82', 13), ('83', 14)]:
            self.registered(self.descriptor(stream, episode))

    def patches(self):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(catalogue, 'advance', return_value='idle'))
        stack.enter_context(mock.patch.object(auto, 'discover_one', return_value='idle'))
        return stack

    def test_batch_checks_three_distinct_jobs_without_waiting_for_another_timer(self):
        self.ready()
        reported = []
        with self.patches(), mock.patch('skip_analysis_worker.analyze', return_value=('no_match', 'checked')) as analyze:
            self.assertEqual(process_batch(self.db, max_jobs=3, report=reported.append), ['no_match'] * 3)
        self.assertEqual(len({call.args[1]['id'] for call in analyze.call_args_list}), 3)
        self.assertEqual(reported, ['no_match'] * 3)

    def test_busy_job_is_not_repeated_and_stays_queued_without_spending_quota(self):
        self.ready()
        with self.patches(), mock.patch('skip_analysis_worker.analyze', return_value=('queued', 'playback')) as analyze:
            self.assertEqual(process_batch(self.db, max_jobs=3), ['queued'] * 3)
        self.assertEqual(len({call.args[1]['id'] for call in analyze.call_args_list}), 3)
        with self.db() as con:
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT SUM(attempts) FROM skip_jobs').fetchone()[0], 0)

    def test_batch_stops_at_the_existing_daily_limit(self):
        self.ready()
        with self.db() as con:
            con.execute('INSERT INTO skip_analysis_budget VALUES(?,23)', (now()[:10],))
        with self.patches(), mock.patch('skip_analysis_worker.analyze', return_value=('no_match', 'checked')) as analyze:
            self.assertEqual(process_batch(self.db), ['no_match', 'daily_limit'])
        self.assertEqual(analyze.call_count, 1)

    def test_batch_checks_its_time_limit_between_jobs(self):
        clock = [0.0]
        def process(*args, **kwargs):
            clock[0] += 2
            return 'no_match'
        with mock.patch('skip_analysis_worker.time.monotonic', side_effect=lambda: clock[0]), \
             mock.patch('skip_analysis_worker.process_one', side_effect=process) as process:
            self.assertEqual(process_batch(self.db, max_seconds=1), ['no_match'])
            self.assertEqual(process.call_count, 1)

    def test_expired_audio_budget_keeps_the_job_queued_without_using_an_attempt(self):
        self.registered(self.target)
        with self.patches(), mock.patch('skip_analysis_worker.time.monotonic', return_value=1000), \
             mock.patch.object(auto, 'provider_proxy', side_effect=AssertionError('expired job must not open provider')):
            self.assertEqual(process_one(self.db, deadline=999), 'queued')
        with self.db() as con:
            row = con.execute('SELECT attempts,detail FROM skip_jobs').fetchone()
            self.assertEqual(row['attempts'], 0)
            self.assertIn('Zeitbudget', row['detail'])
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0], 0)


class WindowCacheTests(AutomationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.registered(self.target)
        rng = random.Random(614)
        self.words = [rng.getrandbits(32) for _ in range(5760)]

    def store(self, kind='intro', length=720000):
        offset = 0 if kind == 'intro' else self.target['duration_ms'] - 720000
        with self.db() as con:
            auto.save_window(con, self.target, kind, self.words, 125, offset, length)

    def test_complete_recent_windows_avoid_both_audio_downloads_after_runtime_check(self):
        self.store(); self.store('outro')
        with mock.patch.object(auto, 'provider_proxy', side_effect=lambda *_: contextlib.nullcontext('fixture')), \
             mock.patch.object(auto, 'probe', return_value=(self.target['duration_ms'], [])) as probe, \
             mock.patch.object(auto, 'fingerprint', side_effect=AssertionError('cached audio must be reused')):
            self.assertEqual(auto.analyze(self.db, self.job(), busy_check)[0], 'no_match')
        self.assertEqual(probe.call_count, 1)

    def test_incomplete_expired_corrupt_and_changed_runtime_windows_are_not_reused(self):
        for update in ["length_ms=100000", "created_at='2000-01-01T00:00:00Z'",
                       "words_json='{}'", "duration_ms=duration_ms+1", "words_json='[1]'",
                       "offset_ms=1000"]:
            self.store()
            with self.db() as con:
                con.execute('UPDATE skip_auto_windows SET ' + update)
                self.assertIsNone(auto.cached_window(con, self.target, 'intro', 0, 720000))


class PresenceReleaseTests(unittest.TestCase):
    setUp = marker_tests.SkipMarkersTest.setUp
    playlist = marker_tests.SkipMarkersTest.playlist

    def presence(self, playlist, session, active=True, client=None, headers=None):
        return (client or self.a).post('/v1/device/skip/presence',
            json=dict(playlist_id=playlist, presence_id=session, active=active), headers=headers or self.ha)

    def test_releasing_playback_immediately_unblocks_the_provider(self):
        playlist = self.playlist(self.customers[0])
        recorded = self.presence(playlist, 'first')
        self.assertEqual(recorded.status_code, 200)
        self.assertTrue(recorded.get_json()['supports_release'])
        with db() as con:
            source = con.execute('SELECT * FROM customer_playlists WHERE id=?', (playlist,)).fetchone()
        self.assertTrue(busy_check(db, [source])())
        self.assertEqual(self.presence(playlist, 'first', False).get_json()['status'], 'released')
        self.assertFalse(busy_check(db, [source])())

    def test_previous_episode_cannot_release_new_playback(self):
        playlist = self.playlist(self.customers[0])
        self.presence(playlist, 'first'); self.presence(playlist, 'second')
        self.presence(playlist, 'first', False)
        with db() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_presence').fetchone()[0], 1)
        self.presence(playlist, 'second', False)
        with db() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_presence').fetchone()[0], 0)

    def test_one_devices_release_does_not_remove_another_devices_lease(self):
        first = self.playlist(self.customers[0]); second = self.playlist(self.customers[1])
        self.presence(first, 'a'); self.presence(second, 'b', client=self.b, headers=self.hb)
        self.presence(first, 'a', False)
        with db() as con:
            rows = con.execute('SELECT device_id FROM skip_presence').fetchall()
            self.assertEqual([row[0] for row in rows], [self.devices[1]])

    def test_legacy_heartbeat_and_invalid_requests(self):
        playlist = self.playlist(self.customers[0])
        self.assertEqual(self.a.post('/v1/device/skip/presence', json=dict(playlist_id=playlist), headers=self.ha).status_code, 200)
        self.assertEqual(self.presence(playlist, 'invalid/' ).status_code, 400)
        self.assertEqual(self.presence(playlist, 'a', active='false').status_code, 400)
