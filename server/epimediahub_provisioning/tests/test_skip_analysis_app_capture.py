"""Authenticated app PCM hashes, real consensus and provider-free live processing."""
import base64
import json
import random
import struct
import sys
import time
import types
import unittest
from unittest import mock

from test_skip_analysis_automation import AutomationFixture
from test_skip_analysis_references import REAL_FLASK
from skip_markers import install, now
from skip_analysis_worker import process_one
import skip_app_capture as capture
import skip_automation as auto


class AppCaptureTests(AutomationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.rng = random.Random(9881)
        self.common = self.words(250)
        self.site = REAL_FLASK('app-capture')
        self.site.secret_key = 'test'
        @self.site.get('/health', endpoint='health')
        def health():
            return {'status': 'ok'}
        backend = types.ModuleType('app')
        backend.digest = lambda value: value
        backend.web_auth = lambda: None
        with mock.patch.dict(sys.modules, {'app': backend}):
            install(self.site, self.db)
        self.client = self.site.test_client()
        self.headers = {'Authorization': 'Bearer fixture-token'}

    def words(self, n):
        return [self.rng.getrandbits(32) for _ in range(n)]

    def payload(self, episode=1, length=120_000, offset=0):
        data = self.descriptor(str(100+episode), episode)
        count = round((length-3000)/capture.STEP_MS)
        words = self.words(100+episode*7) + self.common
        words += self.words(count-len(words))
        return data | dict(algorithm='chromaprint-1',kind='intro',offset_ms=offset,length_ms=length,
            audio_key='c'*64,fingerprint=base64.b64encode(struct.pack('<' + str(len(words)) + 'I',*words)).decode())

    def post(self, raw=None, headers=None):
        return self.client.post('/v1/device/skip/fingerprint',json=raw or self.payload(),
                                headers=self.headers if headers is None else headers)

    def test_upload_is_scoped_and_does_not_publish_a_marker_or_spend_daily_budget(self):
        self.assertEqual(self.post().get_json()['status'],'accepted')
        with self.db() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_app_windows').fetchone()[0],1)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_records').fetchone()[0],0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_analysis_budget').fetchone()[0],0)
        self.assertEqual(self.post(headers={}).status_code,401)
        self.assertEqual(self.post(headers={'Authorization':'Bearer foreign-token'}).get_json()['status'],'unavailable')

    def test_invalid_algorithm_base64_bounds_silence_credentials_and_size_are_rejected(self):
        raw = self.payload()
        for change in [dict(algorithm='wrong'),dict(kind='outro'),dict(fingerprint='x!'),
                       dict(offset_ms=-1),dict(length_ms=True),dict(length_ms=720001),
                       dict(audio_key='z'*64),dict(url='https://example.invalid/private'),
                       dict(fingerprint=base64.b64encode(b'\0'*4000).decode())]:
            self.assertEqual(self.post(raw|change).status_code,400,change)
        self.assertEqual(self.post(raw|dict(padding='x'*64000)).status_code,413)

    def test_disabled_source_does_not_accept_capture(self):
        with self.db() as con: con.execute('UPDATE skip_analysis_sources SET enabled=0')
        self.assertEqual(self.post().get_json()['status'],'unavailable')

    def test_duplicate_and_shorter_upload_do_not_requeue_or_replace_longest_window(self):
        raw = self.payload(length=240000)
        self.assertEqual(self.post(raw).get_json()['status'],'accepted')
        with self.db() as con: con.execute('DELETE FROM skip_app_tasks')
        self.assertEqual(self.post(raw).get_json()['status'],'cached')
        self.assertEqual(self.post(self.payload(length=120000)).get_json()['status'],'cached')
        with self.db() as con:
            self.assertEqual(con.execute('SELECT length_ms FROM skip_app_windows').fetchone()[0],240000)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_app_tasks').fetchone()[0],0)

    def test_wrong_duration_number_and_playlist_cannot_replace_catalogue_file(self):
        raw = self.payload()
        self.registered(raw)
        for change in [dict(duration_ms=raw['duration_ms']+3000),dict(episode=3),dict(playlist_id=2)]:
            self.assertEqual(self.post(raw|change).get_json()['status'],'unavailable')

    def test_catalogue_source_identity_remains_authoritative(self):
        raw = self.payload()
        self.registered(raw)
        self.assertEqual(self.post(raw|dict(source_key='d'*64)).get_json()['status'],'accepted')
        with self.db() as con:
            self.assertEqual(con.execute('SELECT source_key FROM skip_assets').fetchone()[0],raw['source_key'])

    def test_complete_capture_replaces_media_download_only_for_current_runtime(self):
        raw = self.payload(length=720000)
        self.post(raw)
        with self.db() as con:
            asset=dict(con.execute('SELECT * FROM skip_assets').fetchone())
            self.assertIsNotNone(auto.cached_window(con,asset,'intro',0,720000))
            self.assertIsNone(auto.cached_window(con,asset|dict(duration_ms=asset['duration_ms']+1000),'intro',0,720000))
            self.assertIsNone(auto.cached_window(con,asset,'outro',0,720000))

    def test_partial_capture_is_used_for_consensus_but_not_as_a_complete_download(self):
        raw=self.payload()
        self.post(raw)
        with self.db() as con:
            asset=con.execute('SELECT * FROM skip_assets').fetchone()
            self.assertEqual(len(auto.detector_windows(con,asset,'intro')),1)
            self.assertIsNone(auto.cached_window(con,asset,'intro',0,720000))

    def test_real_four_episode_consensus_runs_while_playing_without_provider_io(self):
        with self.db() as con:
            con.execute('DELETE FROM skip_release_settings')
            con.execute('INSERT INTO skip_presence VALUES(1,1,?)',(int(time.time())+70,))
            con.execute('INSERT INTO skip_analysis_budget VALUES(?,500)',(now()[:10],))
        for episode in range(1,5): self.assertEqual(self.post(self.payload(episode)).status_code,200)
        with mock.patch.object(auto,'provider_proxy',side_effect=AssertionError('No media download')), \
             mock.patch.object(auto,'provider_api',side_effect=AssertionError('No catalogue call')):
            self.assertEqual(process_one(self.db),'app_compared')
        with self.db() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_records WHERE status="approved"').fetchone()[0],4)
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0],500)
            evidence=json.loads(con.execute('SELECT evidence_json FROM skip_auto_evidence LIMIT 1').fetchone()[0])
            self.assertEqual(evidence['method'],'episode_consensus_v3')
            self.assertEqual(set(w['origin'] for w in evidence['windows']),{'app'})

    def test_same_episode_versions_do_not_make_independent_partners(self):
        for i in range(4):
            raw=self.payload(1)|dict(stream_id=str(200+i))
            from skip_analysis import source_url,provider_asset_key
            raw['asset_key']=provider_asset_key(source_url({'config_json':json.dumps(self.config)},raw),'episode')
            self.post(raw)
        self.assertTrue(capture.process_one(self.db))
        with self.db() as con: self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_records').fetchone()[0],0)

    def test_rate_limit_and_capability(self):
        raw=self.payload()
        for i in range(6): self.assertEqual(self.post(raw).status_code,200)
        self.assertEqual(self.post(raw).status_code,429)
        result=self.client.post('/v1/device/skip/lookup',json=self.descriptor('101',1),headers=self.headers)
        self.assertTrue(result.get_json()['fingerprint_capture'])
        with self.db() as con: con.execute('UPDATE skip_auto_settings SET enabled=0')
        result=self.client.post('/v1/device/skip/lookup',json=self.descriptor('101',1),headers=self.headers)
        self.assertFalse(result.get_json()['fingerprint_capture'])
