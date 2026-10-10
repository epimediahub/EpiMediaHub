#!/usr/bin/env python3
"""Guard EpiScene from burning thousands of queue transitions on a dead RPC.

This is an opt-in source patch for the Raspberry controller, NOT a deployment.
Run only after reading the EpiScene read-only recovery report. It preserves
the database, workers, schedules, playlist credentials, and existing markers.
"""
from __future__ import annotations
import ast
import os
from pathlib import Path
import shutil
import sys
import tempfile

base = Path(os.environ.get("EPIMEDIAHUB_APP_DIR", "/opt/epimediahub/provisioning"))
path = base / "skip_analysis_worker.py"
original = path.read_text()
before = """    from skip_app_capture import process_one as process_capture
    if process_capture(db, lambda: deadline is not None and time.monotonic() >= deadline):
        return 'app_compared'
"""
after = """    # Remote code/worker health is checked before claiming a queued job.
    # Failures cannot repeatedly move the same asset queued -> running -> queued.
    from skip_remote_client import configured as episcene_remote_configured
    from skip_remote_client import health as episcene_remote_health
    from skip_remote_client import RemoteDeferred as EpiSceneRemoteDeferred
    if episcene_remote_configured():
        try:
            episcene_remote_health()
        except EpiSceneRemoteDeferred as error:
            if 'stimmt nicht überein' in error.reason:
                return 'remote_version_mismatch'
            return 'remote_unavailable'
    from skip_app_capture import process_one as process_capture
    if process_capture(db, lambda: deadline is not None and time.monotonic() >= deadline):
        return 'app_compared'
"""
before_status = '''        if status in ("idle", "daily_limit", "preferred_pending", "catalogue_pending",
                      "playlist_pending", "series_pending", "queued"):
            break'''
after_status = '''        if status in ("idle", "daily_limit", "preferred_pending", "catalogue_pending",
                      "playlist_pending", "series_pending", "queued",
                      "remote_unavailable", "remote_version_mismatch"):
            break'''
if "remote_version_mismatch" in original:
    print("Guard already installed; nothing changed.")
    raise SystemExit(0)
assert original.count(before) == 1, "Unknown controller worker version; no changes made"
assert original.count(before_status) == 1, "Unknown batch loop version; no changes made"
changed = original.replace(before, after, 1).replace(before_status, after_status, 1)
ast.parse(changed, filename=str(path))
backup = path.with_name(path.name + ".before-remote-preflight")
if backup.exists():
    raise SystemExit("Backup already exists; refusing to overwrite or stack patches")
shutil.copy2(path, backup)
with tempfile.NamedTemporaryFile("w", dir=base, prefix=".epi-guard-",
                                 delete=False) as file:
    file.write(changed)
    tmp = Path(file.name)
try:
    os.chmod(tmp, path.stat().st_mode)
    os.replace(tmp, path)
except BaseException:
    if tmp.exists():
        tmp.unlink()
    raise
print("Guard installed. Prior file:", backup)
print("No services restarted, and the database remains unchanged.")
