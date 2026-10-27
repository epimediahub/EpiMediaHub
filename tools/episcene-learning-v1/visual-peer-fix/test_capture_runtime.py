#!/usr/bin/env python3
"""Run the actual patched capture function with faked database/provider dependencies."""
import ast
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
import sys
import unittest

TARGET = Path('/root/skip_scene-optimized-v2.py')


class CaptureRuntimeTests(unittest.TestCase):
    def run_capture(self, fail_at=None):
        tree = ast.parse(TARGET.read_text())
        func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'capture')
        func.decorator_list = []
        code = compile(ast.Module(body=[func], type_ignores=[]), str(TARGET), 'exec')
        stats = {'opened': 0, 'closed': 0, 'calls': [], 'saves': [], 'probes': 0}
        playlist = {'id': 8}
        asset = {'playlist_id': 8, 'duration_ms': 240000}

        class DB:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, *args): return self
            def fetchone(self): return playlist

        @contextmanager
        def proxy(url, busy):
            stats['opened'] += 1
            try:
                yield object()
            finally:
                stats['closed'] += 1

        def fingerprint(source, cursor, part, step, busy):
            stats['calls'].append(cursor)
            if fail_at is not None and cursor == fail_at:
                raise RuntimeError('simulated_provider_failure')
            return [cursor]

        def save(con, asset, kind, cursor, part, frames):
            stats['saves'].append((cursor, part))
            return list(frames)

        analysis = ModuleType('skip_analysis')
        analysis.probe = lambda source, busy: (240000, [])
        analysis.provider_proxy = proxy
        analysis.source_url = lambda playlist, asset: 'fake://local'
        client = ModuleType('skip_remote_client')
        client.visual_fingerprint = fingerprint
        worker = ModuleType('skip_analysis_worker')
        worker.busy_check = lambda db, playlists: (lambda: False)
        namespace = dict(STEP_MS=1000, CHUNK_MS=60000, db=DB, _cache=lambda *a: None,
                         _window=lambda *a: None, _save=save)
        with patch.dict(sys.modules, {'skip_analysis': analysis,
                                      'skip_remote_client': client,
                                      'skip_analysis_worker': worker}):
            exec(code, namespace)
            try:
                result = namespace['capture'](DB, asset, 'intro', 0, 240000,
                                              lambda: False, verified=True)
                if fail_at is not None:
                    self.fail('Expected simulated provider failure')
            except RuntimeError:
                if fail_at is None:
                    raise
                result = None
        return stats, result

    def test_two_chunks_per_connection(self):
        stats, result = self.run_capture()
        self.assertEqual(stats['calls'], [0, 60000, 120000, 180000])
        self.assertEqual(stats['opened'], 2)
        self.assertEqual(stats['closed'], 2)
        self.assertEqual(len(stats['saves']), 5)
        self.assertEqual(result, [0, 60000, 120000, 180000])

    def test_failure_closes_relay_preserves_saved_chunks(self):
        stats, _ = self.run_capture(fail_at=120000)
        self.assertEqual(stats['opened'], 2)
        self.assertEqual(stats['closed'], 2)
        self.assertEqual(stats['saves'], [(0, 60000), (60000, 60000)])


if __name__ == '__main__':
    unittest.main(verbosity=2)
