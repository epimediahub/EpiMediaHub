"""Provider comparison respects playback, private output, worker locks and read-only data."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import skip_analysis as audio
import skip_remote_client as remote
from test_skip_analysis_automation import AutomationFixture

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
