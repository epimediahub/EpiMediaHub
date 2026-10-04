"""Real private RPC, identical detector decisions, fail-closed and lease cancellation."""
import contextlib
import dataclasses
import json
import os
import random
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import wave
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import skip_analysis as audio
import skip_automation as auto
import skip_remote_client as remote
from skip_remote_protocol import PROTOCOL, versions, window_payload
from skip_remote_worker import Server, Tasks, Busy, execute
from skip_detector_v3 import Config, FpWindow, PairCache, detect, DEFAULT_ITEM_SEC
from skip_analysis_worker import process_one
from test_skip_analysis_automation import AutomationFixture
import skip_catalogue as catalogue
import skip_remote_verify as migration


class RpcFixture:
    def start_server(self, executor=execute, peers=('127.0.0.1',)):
        self.server = Server(('127.0.0.1', 0), peers=peers, tasks=Tasks(executor))
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': .02}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.endpoint = 'http://127.0.0.1:' + str(self.server.server_port)
        patch = mock.patch.dict(os.environ, SKIP_ANALYSIS_REMOTE_URL=self.endpoint)
        patch.start(); self.addCleanup(patch.stop)

    def close_server(self):
        self.server.tasks.stopping.set()
        self.server.shutdown(); self.server.server_close()
        self.thread.join(timeout=2)

    def post(self, value):
        request = urllib.request.Request(self.endpoint + '/v1/tasks',
            data=json.dumps(value).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error)


class RpcTests(RpcFixture, unittest.TestCase):
    def setUp(self):
        self.start_server()

    def test_old_reference_and_boundary_match_are_computed_over_http_without_recursion(self):
        rng = random.Random(51)
        reference = [rng.getrandbits(32) for _ in range(100)]
        target = [rng.getrandbits(32) for _ in range(23)] + reference + [rng.getrandbits(32) for _ in range(30)]
        with remote.local_execution():
            expected = audio.matching_offset(reference, target, 125)
            ends = auto.matching_boundaries(reference, target, 125, expected[0])
        self.assertEqual(audio.matching_offset(reference, target, 125), expected)
        self.assertEqual(auto.matching_boundaries(reference, target, 125, expected[0]), ends)
        self.assertEqual(remote.health()['completed'], 2)

    def test_remote_fft_preserves_every_detection_field(self):
        rng = np.random.default_rng(89)
        count = int(200 / DEFAULT_ITEM_SEC)
        theme = rng.integers(0, 2**32, size=int(60 / DEFAULT_ITEM_SEC), dtype=np.uint32)
        windows = []
        for i, start in enumerate((31, 38, 46, 53)):
            fp = rng.integers(0, 2**32, size=count, dtype=np.uint32)
            begin = int(start / DEFAULT_ITEM_SEC)
            fp[begin:begin + len(theme)] = theme
            windows.append(FpWindow(fp, episode_id=str(i), duration_sec=1500))
        expected = detect(windows[0], windows[1:], 'intro', Config(), PairCache())
        actual = remote.detect(windows[0], windows[1:], 'intro', Config())
        self.assertTrue(expected.found)
        self.assertEqual(dataclasses.asdict(actual), dataclasses.asdict(expected))

    def test_real_decoder_and_chromaprint_run_on_worker_thread_and_return_identical_fingerprints(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'episode.wav'
            sample_rate = 11025
            t = np.arange(sample_rate * 24) / sample_rate
            frequency = 220 + 55 * (np.floor(t / 3) % 5)
            pcm = (12000 * (np.sin(2 * np.pi * frequency * t)
                           + .3 * np.sin(2 * np.pi * 1.5 * frequency * t))).astype('<i2')
            with wave.open(str(path), 'wb') as writer:
                writer.setparams((1, 2, sample_rate, 0, 'NONE', 'not compressed'))
                writer.writeframes(pcm.tobytes())
            with remote.local_execution():
                expected = audio.fingerprint(str(path), 0, 20000, with_coverage=True, require_complete=True)
            @contextlib.contextmanager
            def provider(*_):
                yield str(path)
            original_run = audio.run
            parent = threading.get_ident()
            calls = []
            def record(*args, **kwargs):
                self.assertNotEqual(threading.get_ident(), parent)
                calls.append(args[0][0])
                return original_run(*args, **kwargs)
            with mock.patch.object(audio, 'provider_proxy', provider), mock.patch.object(audio, 'run', record):
                source = remote.RemoteSource('https://fixture.example/series/44.mp4', lambda: False)
                self.assertEqual(remote.probe(source, lambda: False), (24000, []))
                self.assertEqual(remote.fingerprint(source, 0, 20000, lambda: False,
                    with_coverage=True, require_complete=True), expected)
            self.assertEqual(calls, ['ffprobe', 'ffmpeg'])
            self.assertGreater(len(expected[0]), 100)

    def test_probe_and_fingerprint_use_the_real_url_on_the_remote_side_only(self):
        started = []
        def executor(operation, payload, busy):
            started.append((operation, payload['url']))
            if operation == 'probe':
                return dict(duration_ms=1200000, chapters=[])
            return dict(words=[17] * 300, step_ms=125, coverage_ms=40000)
        self.server.tasks.executor = executor
        url = 'https://provider.example/series/private-user/private-password/44.mp4'
        with mock.patch.object(audio, 'public_address', side_effect=AssertionError('Pi must not resolve provider')), \
             mock.patch.object(audio, 'run', side_effect=AssertionError('Pi must not launch decoder')):
            with audio.provider_proxy(url) as source:
                self.assertNotIn('private-password', repr(source))
                self.assertEqual(audio.probe(source), (1200000, []))
                self.assertEqual(audio.fingerprint(source, 0, 40000, with_coverage=True),
                                 ([17] * 300, 125, 40000))
        self.assertEqual(started, [('probe', url), ('fingerprint', url)])

    def test_mismatched_code_is_rejected_before_execution(self):
        code = versions(); code['skip_detector_v3.py'] = 'outdated'
        with mock.patch.object(self.server.tasks, 'executor') as executor:
            status, value = self.post(dict(protocol=PROTOCOL, versions=code, operation='probe',
                                          payload={'url': 'https://example.org/media.mp4'}))
            self.assertEqual(status, 412)
            self.assertEqual(value['error'], 'version_mismatch')
            executor.assert_not_called()

    def test_api_rejects_non_peer_and_oversized_inputs(self):
        self.server.peers = frozenset({'10.87.26.2'})
        self.assertEqual(self.post({})[0], 403)
        self.server.peers = frozenset({'127.0.0.1'})
        data = dict(protocol=PROTOCOL, versions=versions(), operation='match',
                    payload=dict(reference=[1] * 10001, target=[1] * 10001, step_ms=125))
        self.assertEqual(self.post(data)[0], 400)

    def test_unsafe_remote_source_still_uses_existing_provider_address_guard(self):
        with audio.provider_proxy('http://localhost/private') as source:
            with self.assertRaisesRegex(ValueError, 'unsafe_source'):
                audio.probe(source)

    def test_unreachable_worker_never_falls_back_to_the_pi_decoder(self):
        with mock.patch.dict(os.environ, SKIP_ANALYSIS_REMOTE_URL='http://127.0.0.1:1'), \
             mock.patch.object(audio, 'run', side_effect=AssertionError('local decoder forbidden')):
            with audio.provider_proxy('https://example.org/media.mp4') as source:
                with self.assertRaises(remote.RemoteDeferred):
                    audio.probe(source)

    def test_invalid_remote_endpoint_and_raw_local_file_fail_closed(self):
        for url in ('http://8.8.8.8:8790', 'http://user:password@10.87.26.1:8790',
                    'https://10.87.26.1:8790', 'http://10.87.26.1:8790/path',
                    'http://10.87.26.1:invalid', 'http://[malformed'):
            with mock.patch.dict(os.environ, SKIP_ANALYSIS_REMOTE_URL=url):
                with self.assertRaises(remote.RemoteDeferred):
                    remote.endpoint()
        with self.assertRaises(remote.RemoteDeferred):
            audio.probe('/tmp/local-media.wav')

    def test_persistent_role_keeps_manual_worker_invocations_remote_even_without_service_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'role.json'
            path.write_text(json.dumps(dict(protocol=PROTOCOL, url=self.endpoint)))
            with mock.patch.dict(os.environ, SKIP_ANALYSIS_REMOTE_URL=''), \
                 mock.patch.object(remote, 'role_path', return_value=path):
                self.assertTrue(remote.configured())
                self.assertEqual(remote.health()['status'], 'ok')
                path.write_text('broken json')
                self.assertTrue(remote.configured())
                with self.assertRaises(remote.RemoteDeferred):
                    remote.health()


class CancellationTests(RpcFixture, unittest.TestCase):
    def test_playback_cancellation_reaches_remote_operation_and_holds_its_slot_until_done(self):
        started, cancelled, release = threading.Event(), threading.Event(), threading.Event()
        def executor(operation, payload, busy):
            started.set()
            while not busy():
                time.sleep(.005)
            cancelled.set()
            release.wait(2)
            raise ValueError('analysis_deferred')
        self.start_server(executor)
        caught = []
        def client():
            try:
                remote.call('probe', {'url': 'https://example.org/media.mp4'}, started.is_set)
            except ValueError as error:
                caught.append(str(error))
        thread = threading.Thread(target=client); thread.start()
        self.assertTrue(cancelled.wait(3))
        self.assertEqual(self.post(dict(protocol=PROTOCOL, versions=versions(), operation='probe',
            payload={'url': 'https://example.org/other.mp4'}))[0], 409)
        release.set(); thread.join(3)
        self.assertEqual(caught, ['analysis_deferred'])
        self.assertFalse(thread.is_alive())

    def test_abandoned_client_operation_expires_without_another_heartbeat(self):
        finished = threading.Event()
        def executor(operation, payload, busy):
            while not busy():
                time.sleep(.005)
            finished.set()
            raise ValueError('analysis_deferred')
        tasks = Tasks(executor)
        with mock.patch('skip_remote_worker.LEASE_SECONDS', .05):
            identity = tasks.submit('probe', {'url': 'https://example.org/media.mp4'})
            self.assertTrue(finished.wait(1))
        for _ in range(100):
            item = tasks.get(identity)
            if item['state'] == 'failed':
                break
            time.sleep(.005)
        self.assertEqual(item['error'], 'analysis_deferred')


class QueueTests(AutomationFixture, unittest.TestCase):
    def test_real_provider_preflight_does_not_write_markers_jobs_or_quota(self):
        self.registered(self.target)
        with self.db() as con:
            before = [tuple(row) for row in con.execute('SELECT * FROM skip_jobs')]
        with mock.patch.object(migration, 'configured', return_value=True), \
             mock.patch.object(migration, 'health'), \
             mock.patch.object(migration, 'provider_proxy', return_value=contextlib.nullcontext('fixture')), \
             mock.patch.object(migration, 'probe', return_value=(self.target['duration_ms'], [])), \
             mock.patch.object(migration, 'fingerprint', return_value=([3] * 100, 125)) as fingerprint:
            migration.verify(self.db)
        self.assertEqual(fingerprint.call_args.args[1:3], (0, 20000))
        self.assertTrue(fingerprint.call_args.kwargs['require_complete'])
        with self.db() as con:
            self.assertEqual([tuple(row) for row in con.execute('SELECT * FROM skip_jobs')], before)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_records').fetchone()[0], 0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_analysis_budget').fetchone()[0], 0)

    def test_provider_preflight_cannot_open_an_account_with_active_playback(self):
        self.registered(self.target)
        with mock.patch.object(migration, 'configured', return_value=True), \
             mock.patch.object(migration, 'health'), \
             mock.patch.object(migration, 'busy_check', return_value=lambda: True), \
             mock.patch.object(migration, 'provider_proxy') as provider:
            with self.assertRaisesRegex(ValueError, 'no_idle_matching_episode'):
                migration.verify(self.db)
        provider.assert_not_called()

    def test_transport_failure_keeps_attempts_budget_and_existing_markers(self):
        self.registered(self.target)
        with mock.patch.object(catalogue, 'advance', return_value='idle'), \
             mock.patch.object(auto, 'discover_one', return_value='idle'), \
             mock.patch('skip_analysis_worker.analyze', side_effect=remote.RemoteDeferred()):
            self.assertEqual(process_one(self.db), 'queued')
        with self.db() as con:
            record = con.execute('SELECT status,attempts,detail FROM skip_jobs').fetchone()
            self.assertEqual(record['status'], 'queued')
            self.assertEqual(record['attempts'], 0)
            self.assertIn('Hetzner', record['detail'])
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
