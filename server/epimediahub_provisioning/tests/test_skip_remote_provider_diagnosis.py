"""Provider comparison respects playback, private output, worker locks and read-only data."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import skip_analysis as audio
import skip_remote_client as remote
from test_skip_analysis_automation import AutomationFixture
from test_skip_remote_analysis import RpcFixture
import skip_remote_protocol as protocol

spec = importlib.util.spec_from_file_location('provider_diagnosis',
                                            ROOT / 'deploy/diagnose_skip_remote_provider.py')
diagnosis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnosis)


class ComparisonTests(AutomationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.registered(self.target)
        self.output = io.StringIO()
        self.emit = lambda value: print(value, file=self.output)

    @contextlib.contextmanager
    def network(self, probe):
        with mock.patch.dict('os.environ', SKIP_ANALYSIS_REMOTE_URL='http://10.87.26.1:8790'), \
             mock.patch.object(remote, 'health', return_value={'active': False}), \
             mock.patch.object(diagnosis, 'remote_idle'), \
             mock.patch.object(audio, 'provider_proxy', side_effect=lambda *a: contextlib.nullcontext('fixture')), \
             mock.patch.object(audio, 'probe', side_effect=probe), \
             mock.patch.object(audio, 'fingerprint', return_value=([9]*100, 125)):
            yield

    def test_same_file_comparison_identifies_hetzner_failure_and_preserves_all_tables(self):
        with self.db() as con:
            before = '\n'.join(con.iterdump())
        calls = []
        def probe(*_):
            calls.append(remote.configured())
            if remote.configured():
                raise ValueError('provider_timeout')
            return self.target['duration_ms'], []
        with self.network(probe):
            self.assertEqual(diagnosis.compare(self.db, self.emit), 0)
        self.assertEqual(calls, [True, False])
        self.assertIn('HETZNER: Laufzeit = provider_timeout', self.output.getvalue())
        self.assertIn('RASPBERRY: Audio = ok', self.output.getvalue())
        self.assertIn('Raspberry liest die Folge; Hetzner scheitert', self.output.getvalue())
        with self.db() as con:
            self.assertEqual('\n'.join(con.iterdump()), before)

    def test_corrupt_first_file_does_not_hide_working_second_episode(self):
        self.registered(self.seed)
        calls = []
        def probe(*_):
            calls.append(remote.configured())
            if len(calls)<=2:
                raise ValueError('provider_http_404')
            return self.target['duration_ms'], []
        with self.network(probe):
            self.assertEqual(diagnosis.compare(self.db, self.emit), 0)
        self.assertEqual(calls, [True, False, True, False])
        self.assertIn('Mindestens eine Folge funktioniert auf beiden Geräten', self.output.getvalue())

    def test_active_playback_opens_no_provider_connection(self):
        with self.network(lambda *_: self.fail('Provider must stay closed')), \
             mock.patch('skip_analysis_worker.busy_check', return_value=lambda: True):
            self.assertEqual(diagnosis.compare(self.db, self.emit), 2)

    def test_health_failure_prevents_both_provider_reads(self):
        with self.network(lambda *_: self.fail('Provider must stay closed')), \
             mock.patch.object(remote, 'health', side_effect=remote.RemoteDeferred()):
            with self.assertRaises(remote.RemoteDeferred):
                diagnosis.compare(self.db, self.emit)

    def test_unknown_exception_never_prints_url_credentials_or_raw_messages(self):
        secret = 'https://provider.invalid/user/PASSWORD_SECRET/media.mkv'
        with self.network(lambda *_: (_ for _ in ()).throw(ValueError(secret))):
            diagnosis.compare(self.db, self.emit)
        text = self.output.getvalue()
        self.assertNotIn(secret, text)
        self.assertNotIn('PASSWORD_SECRET', text)
        self.assertIn('analysis_failed', text)

    def test_gateway_comparison_names_the_private_path_and_observes_both_failed_attempts(self):
        def probe(*_):
            if remote.configured(): raise ValueError('analysis_failed')
            return self.target['duration_ms'],[]
        with self.network(probe),mock.patch.dict('os.environ',SKIP_ANALYSIS_PROVIDER_PATH='raspberry'):
            self.assertEqual(diagnosis.compare(self.db,self.emit),0)
        text=self.output.getvalue()
        self.assertIn('Hetzner liest die echten Folgen über den privaten Raspberry-Abruf',text)
        self.assertIn('PRIVATER ABRUF: Anfragen=0, Range=0, Medienbytes=0, HTTP=-',text)
        self.assertIn('Hetzner scheitert am privaten Medienabruf',text)


class RelayDiagnosisTests(RpcFixture,unittest.TestCase):
    def setUp(self):
        self.start_server()
        self.output=io.StringIO()
        self.emit=lambda value:print(value,file=self.output)

    def test_native_testaudio_uses_the_remote_decoder_and_no_provider_connection(self):
        parent=threading.get_ident()
        calls=[]
        original=audio.run
        def run(*args,**kwargs):
            self.assertNotEqual(threading.get_ident(),parent,'Testaudio must decode on Hetzner')
            calls.append(args[0][0])
            return original(*args,**kwargs)
        with mock.patch.object(protocol,'CLIENT_IP','127.0.0.1'), \
             mock.patch.object(protocol,'SERVER_IP','127.0.0.1'), \
             mock.patch.object(audio,'public_address',side_effect=AssertionError('No provider contact')), \
             mock.patch.object(audio,'run',side_effect=run):
            self.assertTrue(diagnosis.relay_test(audio,remote,self.emit))
        self.assertEqual(calls,['ffprobe','ffmpeg'])
        text=self.output.getvalue()
        self.assertIn('TUNNEL-TEST: Audio=ok',text)
        self.assertIn('Audiodekodierung auf Hetzner: OK',text)
        self.assertNotIn('http://',text)

    def test_missing_reverse_connection_is_reported_without_opening_a_provider(self):
        with mock.patch.object(protocol,'CLIENT_IP','127.0.0.1'), \
             mock.patch.object(protocol,'SERVER_IP','127.0.0.1'), \
             mock.patch.object(audio,'public_address',side_effect=AssertionError('No provider contact')), \
             mock.patch.object(audio,'probe',side_effect=ValueError('analysis_failed')):
            self.assertFalse(diagnosis.relay_test(audio,remote,self.emit))
        text=self.output.getvalue()
        self.assertIn('Anfragen=0, Abgewiesen=0, Testbytes=0',text)
        self.assertIn('kam keine Hetzner-Anfrage an',text)
        self.assertNotIn('http://',text)

    def test_audio_failure_after_successful_probe_keeps_the_exact_phase(self):
        with mock.patch.object(protocol,'CLIENT_IP','127.0.0.1'), \
             mock.patch.object(protocol,'SERVER_IP','127.0.0.1'), \
             mock.patch.object(audio,'probe',return_value=(24000,[])), \
             mock.patch.object(audio,'fingerprint',side_effect=ValueError('https://host/user/SECRET')):
            self.assertFalse(diagnosis.relay_test(audio,remote,self.emit))
        text=self.output.getvalue()
        self.assertIn('TUNNEL-TEST: Audio=analysis_failed',text)
        self.assertNotIn('SECRET',text)

    def test_observer_preserves_media_bytes_and_excludes_error_pages_and_private_urls(self):
        payload=b'binary-media'*7000
        class Provider(BaseHTTPRequestHandler):
            def log_message(self,*_): pass
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length',str(len(payload)))
                self.end_headers();self.wfile.write(payload)
        provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
        thread=threading.Thread(target=provider.serve_forever,daemon=True);thread.start()
        url=f'http://media.fixture:{provider.server_port}/user/SECRET/episode.mp4'
        try:
            with mock.patch.object(audio,'public_address',return_value=(urllib.parse.urlsplit(url),('127.0.0.1',))), \
                 diagnosis.relay_observation(audio,self.emit) as stats:
                with audio._provider_proxy_local(url,lambda:False) as source:
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(source+'wrong',timeout=2)
                    self.assertEqual(error.exception.code,503);error.exception.close()
                    with urllib.request.urlopen(source,timeout=2) as response:
                        self.assertEqual(response.read(),payload)
                self.assertEqual(stats,dict(requests=2,ranges=0,bytes=len(payload),statuses={503:1,200:1}))
            text=self.output.getvalue()
            self.assertIn(f'Medienbytes={len(payload)}',text)
            self.assertIn('HTTP=200:1,503:1',text)
            self.assertNotIn('SECRET',text)
            self.assertNotIn('http://',text)
        finally:
            provider.shutdown();provider.server_close();thread.join(timeout=2)


class CoordinationTests(unittest.TestCase):
    def test_local_baseline_waits_for_remote_cleanup(self):
        peer = types.SimpleNamespace(health=mock.Mock(side_effect=[{'active':True}, {'active':False}]))
        diagnosis.remote_idle(peer, lambda: False, timeout=1, quiet=0)
        self.assertEqual(peer.health.call_count, 2)

    def test_playback_start_while_waiting_prevents_local_connection(self):
        peer = types.SimpleNamespace(health=mock.Mock())
        with self.assertRaisesRegex(ValueError, '^analysis_deferred$'):
            diagnosis.remote_idle(peer, lambda: True)
        peer.health.assert_not_called()

    def test_timer_is_resumed_and_worker_lock_released_after_diagnostic_failure(self):
        import fcntl
        events = []
        def command(args, **_):
            events.append(args)
            return types.SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as path, mock.patch.object(diagnosis.subprocess,'run',command):
            directory = Path(path)
            with self.assertRaisesRegex(ValueError, 'fixture_failure'):
                with diagnosis.worker_pause(directory, lambda _: None):
                    with (directory / 'skip-analysis.lock').open('a') as other:
                        with self.assertRaises(BlockingIOError):
                            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    raise ValueError('fixture_failure')
            with (directory / 'skip-analysis.lock').open('a') as other:
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual([item[1] for item in events], ['is-active','stop','start'])

    def test_data_directory_reads_quoted_environment_without_shell_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'server.env'
            file.write_text('EPIMEDIAHUB_DATA_DIR="/tmp/quoted path/$(unused)"\n')
            self.assertEqual(diagnosis.data_directory(file), Path('/tmp/quoted path/$(unused)'))


if __name__=='__main__':
    unittest.main()
