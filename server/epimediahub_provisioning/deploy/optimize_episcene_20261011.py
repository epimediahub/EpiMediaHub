#!/usr/bin/env python3
"""EpiScene 2026-10-11: safe, version-pinned optimization for live Hetzner.

Keep more 6-hour visual frames, and check worker connectivity/version BEFORE
claiming a queued job. Does not change database or playlist data.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

CONTROLLER = Path('/opt/epimediahub/provisioning')
WORKER = Path('/opt/epimediahub/analysis')
TIMER = 'epimediahub-skip-analysis.timer'
ANALYSIS = 'epimediahub-skip-analysis.service'
REMOTE_WORKER = 'epimediahub-analysis-worker.service'
EXPECTED = {
    'skip_scene.py': 'c666e20a90d72840d2b82f1dea15faad8368f06ec5a21610fd98f26f0e02ae7a',
    'skip_analysis_worker.py': '0db75c3116117f00f3ed2ca360b285ec46cbf3c842a1eb2401cfe31eec5d394f',
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cmd(*args: str, timeout: int = 120) -> None:
    subprocess.run(args, check=True, timeout=timeout)


def is_active(unit: str) -> bool:
    return subprocess.run(['systemctl', 'is-active', '--quiet', unit], check=False).returncode == 0


def write_atomic(path: Path, data: bytes) -> None:
    stat = path.stat()
    fd, temp = tempfile.mkstemp(prefix='.episcene-daily-opt-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, stat.st_mode & 0o7777)
        os.chown(temp, stat.st_uid, stat.st_gid)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def patch_scene(source: str) -> str:
    assert source.count('CACHE_ROWS = 512') == 1, 'Unknown cache limit or already patched'
    assert source.count('CACHE_SECONDS = 21600') == 1, '6-hour cache not installed'
    assert source.count('JOB_SECONDS = 300') == 1, '300s visual budget not installed'
    modified = source.replace('CACHE_ROWS = 512', 'CACHE_ROWS = 2048', 1)
    ast.parse(modified, filename='skip_scene.py')
    return modified


def patch_worker(source: str) -> str:
    # Deliberately retain app captures and all existing playlist selection.
    anchor = '    from skip_catalogue import advance as catalogue_advance'
    assert source.count(anchor) == 1, 'Unknown analysis entry point'
    pos = source.index(anchor)
    before, after = source[:pos], source[pos:]
    assert 'def process_one(' in before[-4500:], 'Unexpected process_one structure'
    assert 'process_capture(' in before[-1200:], 'App capture entry not verified'
    assert 'def process_batch(' in after, 'Expected batch runner missing'
    batch_code = after[after.index('def process_batch('):]
    assert re.search(r'\bif\s+status\s+in\s*\([\s\S]{0,480}?[\'\"]queued[\'\"]', batch_code), 'Batch does not appear to stop on queued'
    assert 'episcene_preflight=' not in source, 'Guard already present'
    guard = '''    # Check private compute worker before claiming queued work.
    # /health verifies connectivity and identical component SHA-256 hashes.
    from skip_remote_client import configured as _episcene_remote_configured
    from skip_remote_client import health as _episcene_remote_health
    from skip_remote_client import RemoteDeferred as _episcene_remote_deferred
    if not _episcene_remote_configured():
        print('episcene_preflight=remote_not_configured', flush=True)
        return 'queued'
    try:
        _episcene_remote_health()
    except _episcene_remote_deferred:
        print('episcene_preflight=worker_unreachable_or_version_mismatch', flush=True)
        return 'queued'
'''
    modified = before + guard + after
    ast.parse(modified, filename='skip_analysis_worker.py')
    return modified


def main() -> int:
    parser = argparse.ArgumentParser(description='Version-pinned safe EpiScene optimization')
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--check', action='store_true', help='inspect without changes')
    choice.add_argument('--apply', action='store_true', help='back up and install')
    args = parser.parse_args()

    if os.geteuid() != 0:
        raise SystemExit('Must run as root on epimediahub-analysis Hetzner host')
    assert CONTROLLER.is_dir() and WORKER.is_dir(), 'Controller/worker directory missing'

    sources = {}
    new_sources = {}
    for name in EXPECTED:
        for base in (CONTROLLER, WORKER):
            path = base / name
            content = path.read_bytes()
            actual = digest(content)
            if actual != EXPECTED[name]:
                raise SystemExit(f'STOP: {path} SHA {actual} differs from report SHA {EXPECTED[name]} (no changes).')
            sources[path] = content
        assert sources[CONTROLLER / name] == sources[WORKER / name], f'{name} controller/worker differ'

    scene = patch_scene(sources[CONTROLLER / 'skip_scene.py'].decode('utf-8')).encode('utf-8')
    worker = patch_worker(sources[CONTROLLER / 'skip_analysis_worker.py'].decode('utf-8')).encode('utf-8')
    for base in (CONTROLLER, WORKER):
        new_sources[base / 'skip_scene.py'] = scene
        new_sources[base / 'skip_analysis_worker.py'] = worker

    space = shutil.disk_usage('/var/lib/epimediahub')
    if space.free < 2 * 1024**3:
        raise SystemExit(f'STOP: Only {space.free/1024**3:.2f} GiB free; requires 2 GiB (no changes)')

    print('=== EPISCENE 2026-10-11 OPTIMIERUNG ===', flush=True)
    print('Controller and worker match exact report hashes.', flush=True)
    print('Visual cache: 512 -> 2048 rows; 6h retention and 300s budget unchanged.', flush=True)
    print('Worker preflight: /health before job claim, fail safely to queued.', flush=True)
    print(f'Available disk: {space.free/1024**3:.2f} GiB.', flush=True)
    if args.check:
        print('CHECK OK — no changes made.', flush=True)
        return 0

    sys.path.insert(0, str(CONTROLLER))
    from skip_remote_protocol import versions
    from skip_remote_client import health
    local = versions()
    assert all(name in local and local[name] == EXPECTED[name] for name in EXPECTED), 'Version manifest mismatch'
    assert health().get('status') == 'ok', 'Compute worker not healthy before upgrade'

    states = {unit: is_active(unit) for unit in (TIMER, ANALYSIS, REMOTE_WORKER)}
    assert states[REMOTE_WORKER], 'Compute worker inactive before upgrade'
    backup_dir = WORKER / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='episcene-daily-20261011-', dir=backup_dir))
    for p in sources:
        shutil.copy2(p, backup / (('controller-' if p.parent == CONTROLLER else 'worker-') + p.name))
    print('Backup:', backup, flush=True)

    stopped = False
    try:
        cmd('systemctl', 'stop', TIMER)
        cmd('systemctl', 'stop', ANALYSIS)
        cmd('systemctl', 'stop', REMOTE_WORKER)
        stopped = True
        for p, data in new_sources.items():
            write_atomic(p, data)
        for base in (CONTROLLER, WORKER):
            python = base / '.venv/bin/python'
            assert python.is_file(), f'Venv missing: {python}'
            cmd(str(python), '-m', 'py_compile',
                str(base / 'skip_scene.py'), str(base / 'skip_analysis_worker.py'))
        cmd('systemctl', 'start', REMOTE_WORKER)
        last_error = None
        for _ in range(15):
            try:
                remote = health()
                assert remote.get('status') == 'ok', 'Worker unhealthy'
                assert remote.get('versions') == versions(), 'Worker version mismatch'
                break
            except Exception as exc:
                last_error = exc
                time.sleep(1)
        else:
            raise RuntimeError(f'Worker verification failed: {last_error}')
    except BaseException as exc:
        print('INSTALL FAILED — rolling back:', repr(exc), file=sys.stderr, flush=True)
        if stopped:
            for p, original in sources.items():
                try:
                    write_atomic(p, original)
                except Exception as error:
                    print('URGENT: rollback failed for', p, repr(error), file=sys.stderr)
            subprocess.run(['systemctl', 'restart', REMOTE_WORKER], check=False)
        if states[TIMER]:
            subprocess.run(['systemctl', 'start', TIMER], check=False)
        if states[ANALYSIS]:
            subprocess.run(['systemctl', 'start', '--no-block', ANALYSIS], check=False)
        raise SystemExit(1)

    if states[TIMER]:
        cmd('systemctl', 'start', TIMER)
    if states[ANALYSIS]:
        cmd('systemctl', 'start', '--no-block', ANALYSIS)
    print('SUCCESS: Worker healthy and synchronized; prior timer state restored.', flush=True)
    print('Backups:', backup, flush=True)
    print('Database, markers, credentials and playlists untouched.', flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (AssertionError, OSError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        print('STOP:', exc, file=sys.stderr)
        sys.exit(1)
