"""HTTP responses must survive the pinned relay and remain distinct in SQLite."""
from __future__ import annotations

import email.utils
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest import mock
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_skip_analysis_automation import AutomationFixture
import skip_analysis as analysis
import skip_automation as auto
from skip_analysis_worker import busy_check, process_one
from skip_markers import now


class JSONProxyTests(unittest.TestCase):
    def setUp(self):
        self.status, self.headers, self.body = 404, {}, b'{"error":"NEVER_PRINT_BODY"}'
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                self.send_response(fixture.status)
                for key, value in fixture.headers.items():
                    self.send_header(key, value)
                self.send_header('Content-Length', str(len(fixture.body)))
                self.end_headers()
                self.wfile.write(fixture.body)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://public.test:{self.server.server_port}/json?api_key=NEVER_PRINT_KEY'
        self.address = mock.patch.object(analysis, 'public_address', return_value=('public.test', '93.184.216.34'))

        def pin(cls, host, address, **kwargs):
            self.assertEqual(address, '93.184.216.34')
            return http.client.HTTPConnection('127.0.0.1', self.server.server_port, **kwargs)

        self.pin = mock.patch.object(analysis, 'pinned_connection', side_effect=pin)
        self.address.start(); self.pin.start()

    def tearDown(self):
        self.pin.stop(); self.address.stop()
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)

    def test_json_client_receives_real_upstream_status_instead_of_local_502(self):
        for status in (400, 401, 403, 404, 429, 502, 503):
            with self.subTest(status=status):
                self.status = status
                with self.assertRaises(analysis.ProviderFailure) as caught:
                    auto.fetch_json(self.url)
                self.assertEqual(str(caught.exception), 'provider_http_' + str(status))
                self.assertNotIn('NEVER_PRINT', repr(caught.exception))

    def test_retry_headers_survive_relay_including_daily_budget_reset(self):
        self.status = 429
        self.headers = {'Retry-After': '10', 'X-UsageLimit-Reset': '43200'}
        with self.assertRaises(analysis.ProviderFailure) as caught:
            auto.fetch_json(self.url)
        self.assertEqual(caught.exception.retry_after, 43200)

    def test_success_is_json_and_busy_request_is_deferred(self):
        self.status, self.body = 200, b'{"type":"tv"}'
        self.assertEqual(auto.fetch_json(self.url), {'type': 'tv'})
        with self.assertRaisesRegex(ValueError, '^analysis_deferred$'):
            auto.fetch_json(self.url, lambda: True)

    def test_retry_headers_are_bounded_and_support_http_dates(self):
        error = urllib.error.HTTPError(self.url, 429, 'too many', {'Retry-After': '999999999'}, None)
        self.assertEqual(analysis.provider_retry_after(error), 86400)
        error.headers = {'Retry-After': email.utils.formatdate(time.time() + 100, usegmt=True)}
        self.assertIn(analysis.provider_retry_after(error), (99, 100))
        error.headers = {'Retry-After': 'not a date', 'X-UsageLimit-Reset': '-1'}
        self.assertEqual(analysis.provider_retry_after(error), 0)


class OnlineErrorTests(AutomationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.registered(self.target)
        with self.db() as con:
            con.execute('UPDATE skip_auto_settings SET online_enabled=1')
            con.execute("UPDATE skip_jobs SET status='no_match',attempts=2,detail='audio result'")
            con.execute("INSERT INTO skip_identities VALUES(?, 'tt1235099', 8358, 'Lie to Me', '2009', ?)",
                        (self.target['source_key'], now()))

    def cache(self):
        with self.db() as con:
            return con.execute('SELECT * FROM skip_auto_online WHERE asset_key=?', (self.target['asset_key'],)).fetchone()

    def error(self, code, retry_after=0):
        with mock.patch.object(auto, 'fetch_json', side_effect=analysis.ProviderFailure(code, retry_after)):
            return auto.online_segments(self.db, self.target, lambda: False)

    def legacy(self):
        with self.db() as con:
            con.execute('INSERT INTO skip_auto_online VALUES(?,?,?,?,?)',
                        (self.target['asset_key'], self.target['duration_ms'], '[]', auto.LEGACY_ONLINE_ERROR, int(time.time())))
            auto.migrate(con)

    def test_404_is_missing_data_and_cached_without_retry_or_service_pause(self):
        self.assertEqual(self.error('provider_http_404'), [])
        self.assertIn('Keine Online-Zeitmarken', self.cache()['detail'])
        self.assertNotIn('nicht erreichbar', self.cache()['detail'])
        with mock.patch.object(auto, 'fetch_json') as fetch:
            self.assertEqual(auto.online_segments(self.db, self.target, lambda: False), [])
            fetch.assert_not_called()
        with self.db() as con:
            self.assertFalse(con.execute('SELECT 1 FROM skip_auto_online_retry').fetchone())
            self.assertFalse(con.execute('SELECT 1 FROM skip_auto_online_cooldown').fetchone())

    def test_tmdb_404_is_a_numbering_or_identity_problem(self):
        with self.db() as con:
            con.execute('DELETE FROM skip_identities')
        with mock.patch.dict('os.environ', {'EPIMEDIAHUB_TMDB_API_KEY': 'NEVER_PRINT_KEY'}):
            self.error('provider_http_404')
        self.assertIn('TMDB kennt diese Serien-/Folgenzuordnung nicht', self.cache()['detail'])
        self.assertNotIn('NEVER_PRINT', self.cache()['detail'])

    def test_invalid_tmdb_key_is_separate_from_time_database_access_denied(self):
        self.error('provider_http_403')
        self.assertIn('Online-Zeitdatenbank verweigert den Zugriff (HTTP 403)', self.cache()['detail'])
        with self.db() as con:
            con.execute('DELETE FROM skip_auto_online')
            con.execute('DELETE FROM skip_auto_online_retry')
            con.execute('DELETE FROM skip_identities')
        with mock.patch.dict('os.environ', {'EPIMEDIAHUB_TMDB_API_KEY': 'NEVER_PRINT_KEY'}):
            self.error('provider_http_401')
        self.assertIn('TMDB-Schlüssel wird nicht akzeptiert (HTTP 401)', self.cache()['detail'])

    def test_429_parks_every_episode_until_advertised_daily_reset(self):
        self.error('provider_http_429', 43200)
        self.assertIn('Abfragelimit erreicht', self.cache()['detail'])
        other = self.descriptor('83', 14)
        self.registered(other)
        with mock.patch.object(auto, 'fetch_json') as fetch:
            auto.online_segments(self.db, other, lambda: False)
            self.assertEqual(auto.refresh_online_one(self.db, busy_check), 'idle')
            fetch.assert_not_called()
        with self.db() as con:
            until = con.execute('SELECT retry_at FROM skip_auto_online_cooldown').fetchone()[0]
            self.assertGreater(until - time.time(), 43190)

    def test_network_errors_have_safe_specific_cause_and_retry(self):
        for code, phrase in (('provider_dns','DNS-Fehler'), ('provider_tls','TLS-Fehler'),
                             ('provider_timeout','Zeitüberschreitung'), ('provider_http_503','HTTP 503')):
            with self.subTest(code=code):
                with self.db() as con:
                    con.execute('DELETE FROM skip_auto_online')
                    con.execute('DELETE FROM skip_auto_online_retry')
                    con.execute('DELETE FROM skip_auto_online_cooldown')
                self.error(code)
                self.assertIn(phrase, self.cache()['detail'])
                with self.db() as con:
                    retry = con.execute('SELECT * FROM skip_auto_online_retry').fetchone()
                    self.assertEqual(retry['error_code'], code)
                    self.assertGreater(retry['retry_at'], time.time())

    def test_bad_json_is_not_reported_as_missing_data_or_leaked(self):
        with mock.patch.object(auto, 'fetch_json', side_effect=json.JSONDecodeError('NEVER_PRINT_KEY','secret',0)):
            auto.online_segments(self.db, self.target, lambda: False)
        self.assertIn('ungültige Antwort', self.cache()['detail'])
        self.assertNotIn('NEVER_PRINT', self.cache()['detail'])

    def test_playback_started_during_request_does_not_cache_failure_or_pause_service(self):
        with mock.patch.object(auto, 'fetch_json', side_effect=analysis.ProviderFailure('provider_http_503')):
            with self.assertRaisesRegex(ValueError, '^analysis_deferred$'):
                auto.online_segments(self.db, self.target, mock.Mock(side_effect=[False, True]))
        self.assertIsNone(self.cache())
        with self.db() as con:
            self.assertFalse(con.execute('SELECT 1 FROM skip_auto_online_cooldown').fetchone())

    def test_legacy_error_recheck_keeps_audio_job_marker_and_key_unchanged(self):
        self.marker(self.target)
        with self.db() as con:
            con.execute("INSERT INTO skip_auto_metadata_config VALUES('tmdb_api_key',?,'before')", ('a'*32,))
            before = tuple(con.execute('SELECT status,attempts,detail,updated_at FROM skip_jobs').fetchone())
        self.legacy()
        with mock.patch.object(auto, 'fetch_json', side_effect=analysis.ProviderFailure('provider_http_404')) as fetch, \
             mock.patch.object(auto, 'provider_proxy') as video:
            self.assertEqual(auto.refresh_online_one(self.db, busy_check), 'online_checked')
            self.assertEqual(fetch.call_count, 1)
            video.assert_not_called()
        with self.db() as con:
            self.assertEqual(tuple(con.execute('SELECT status,attempts,detail,updated_at FROM skip_jobs').fetchone()), before)
            self.assertEqual(con.execute('SELECT status,start_ms FROM skip_records').fetchone()[:], ('approved',283043))
            self.assertEqual(con.execute("SELECT value FROM skip_auto_metadata_config WHERE name='tmdb_api_key'").fetchone()[0], 'a'*32)
            self.assertFalse(con.execute('SELECT 1 FROM skip_analysis_budget').fetchone())

    def test_recheck_creates_pending_online_proposal_but_cannot_approve_it(self):
        self.legacy()
        body = {'type':'tv','tmdb_id':8358,'intro':[{'start_ms':48000,'end_ms':74530}]}
        with mock.patch.object(auto, 'fetch_json', return_value=body):
            self.assertEqual(auto.refresh_online_one(self.db, busy_check), 'online_checked')
        with self.db() as con:
            self.assertEqual(con.execute('SELECT source,status FROM skip_records').fetchone()[:], ('theintrodb','pending'))

    def test_recheck_respects_manual_rejection_busy_playback_and_disabled_sources(self):
        self.legacy()
        body = {'type':'tv','tmdb_id':8358,'intro':[{'start_ms':48000,'end_ms':74530}]}
        with mock.patch.object(auto, 'fetch_json', return_value=body) as fetch:
            with self.db() as con:
                con.execute('INSERT INTO skip_presence VALUES(1,1,?)', (int(time.time())+70,))
            self.assertEqual(auto.refresh_online_one(self.db, busy_check), 'queued')
            fetch.assert_not_called()
            with self.db() as con:
                con.execute('DELETE FROM skip_presence')
                con.execute('UPDATE skip_auto_settings SET online_enabled=0')
            self.assertEqual(auto.refresh_online_one(self.db, busy_check), 'idle')
            fetch.assert_not_called()
            with self.db() as con:
                con.execute('UPDATE skip_auto_settings SET online_enabled=1')
            self.marker(self.target, status='rejected')
            self.assertEqual(auto.refresh_online_one(self.db, busy_check), 'online_checked')
        with self.db() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_records').fetchone()[0], 1)

    def test_rechecks_are_bounded_independently_of_audio_quota(self):
        self.legacy()
        with self.db() as con:
            con.execute('INSERT INTO skip_auto_online_budget VALUES(?,?)', (now()[:10],auto.ONLINE_RECHECK_LIMIT))
        with mock.patch.object(auto, 'fetch_json') as fetch:
            self.assertEqual(auto.refresh_online_one(self.db, busy_check), 'daily_limit')
            fetch.assert_not_called()

    def test_worker_can_refresh_online_after_audio_daily_limit_without_fetching_video(self):
        self.legacy()
        with self.db() as con:
            con.execute('INSERT INTO skip_analysis_budget VALUES(?,1000)', (now()[:10],))
        with mock.patch.object(auto, 'fetch_json', side_effect=analysis.ProviderFailure('provider_http_404')) as fetch, \
             mock.patch.object(auto, 'provider_proxy') as video:
            self.assertEqual(process_one(self.db), 'daily_limit')
            self.assertEqual(fetch.call_count, 1)
            video.assert_not_called()
        self.assertIn('Keine Online-Zeitmarken', self.cache()['detail'])


if __name__ == '__main__':
    unittest.main()
