#!/usr/bin/env python3
"""Safe EpiScene scene-code sync between controller and local remote-worker service.

The private worker listens on loopback. Refuses to change anything unless
the health endpoint reports exactly a skip_scene.py version mismatch.
No changes to DBs, analysis markers, accounts or playlists.
"""
from __future__ import annotations

import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

CONTROLLER = Path("/opt/epimediahub/provisioning")
COMPUTE = Path("/opt/epimediahub/analysis")
SOURCE_SCENE = CONTROLLER / "skip_scene.py"
SOURCE_HINTS = CONTROLLER / "skip_external_learning_hints.py"
DEST_SCENE = COMPUTE / "skip_scene.py"
DEST_HINTS = COMPUTE / "skip_external_learning_hints.py"
WORKER_SERVICE = "epimediahub-analysis-worker.service"
ANALYSIS_SERVICE = "epimediahub-skip-analysis.service"
TIMER = "epimediahub-skip-analysis.timer"
LOCK = Path("/var/lib/epimediahub/skip-analysis.lock")
BACKUP_ROOT = Path("/var/backups/epimediahub/episcene-compute-sync")

def run(*args, check=True):
    return subprocess.run(args, check=check, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True)

def active(unit):
    return run("systemctl", "is-active", "--quiet", unit, check=False).returncode == 0

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def check_path(path, *, existing=True):
    if path.is_symlink() or (existing and not path.is_file()):
        raise RuntimeError("STOP_UNSAFE_PATH: " + str(path))
    if existing and path.stat().st_size > 750_000:
        raise RuntimeError("STOP_UNEXPECTED_FILE_SIZE: " + str(path))

def copy_atomic(source, target):
    """Replace bytes without exposing a half-written importable Python file."""
    old = target.stat() if target.exists() else None
    fd, tmp = tempfile.mkstemp(prefix=".episcene-sync-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(source.read_bytes())
            output.flush()
            os.fsync(output.fileno())
        if old:
            os.chown(tmp, old.st_uid, old.st_gid)
            os.chmod(tmp, old.st_mode & 0o7777)
        else:
            os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def worker_health(remote, expected, *, max_attempts=12):
    for _ in range(max_attempts):
        try:
            reply = remote.request("/health", timeout=2)
            if reply.get("status") == "ok" and reply.get("versions") == expected:
                return True
        except remote.RemoteDeferred:
            pass
        time.sleep(.7)
    return False

def main():
    if os.geteuid() != 0:
        raise RuntimeError("STOP_ROOT_REQUIRED")
    for directory in (CONTROLLER, COMPUTE):
        if not directory.is_dir() or directory.is_symlink():
            raise RuntimeError("STOP_MISSING_DEPLOY_DIRECTORY: " + str(directory))
    for path in (SOURCE_SCENE, SOURCE_HINTS, DEST_SCENE):
        check_path(path)
    for path in (DEST_HINTS, LOCK):
        if path.is_symlink():
            raise RuntimeError("STOP_UNSAFE_PATH: " + str(path))
    if not LOCK.is_file():
        raise RuntimeError("STOP_MISSING_LOCK")
    if "from skip_external_learning_hints import external_hint" not in SOURCE_SCENE.read_text():
        raise RuntimeError("STOP_CONTROLLER_ACTIVE_HINTS_NOT_INSTALLED")

    service_exec = run("systemctl", "show", WORKER_SERVICE,
                       "-p", "ExecStart", "--value").stdout
    if str(COMPUTE / "skip_remote_worker.py") not in service_exec:
        raise RuntimeError("STOP_COMPUTE_SERVICE_PATH_NOT_VERIFIED")

    sys.path.insert(0, str(CONTROLLER))
    import skip_remote_client as remote
    from skip_remote_protocol import versions

    before = remote.request("/health", timeout=4)
    local_versions = versions()
    remote_versions = before.get("versions")
    if before.get("status") != "ok" or not isinstance(remote_versions, dict):
        raise RuntimeError("STOP_WORKER_UNHEALTHY_BEFORE_DEPLOY")
    if not isinstance(local_versions, dict):
        raise RuntimeError("STOP_LOCAL_VERSION_SCHEMA")
    differences = sorted(k for k in local_versions.keys() | remote_versions.keys()
                         if local_versions.get(k) != remote_versions.get(k))
    if not differences:
        print("SYNC_ALREADY_OK: worker health and all versions agree")
        return
    if differences != ["skip_scene.py"]:
        raise RuntimeError("STOP_UNEXPECTED_VERSION_DIFFERENCE: "+str(differences))
    old_sha = digest(SOURCE_SCENE)
    print("PREFLIGHT_OK: only skip_scene.py differs; private worker healthy")

    timer_was_active = active(TIMER)
    if timer_was_active:
        run("systemctl", "stop", TIMER)
    try:
        with LOCK.open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("STOP_ANALYSIS_LOCK_BUSY: no changes")
            if active(ANALYSIS_SERVICE):
                raise RuntimeError("STOP_ANALYSIS_SERVICE_ACTIVE: no changes")
            if digest(SOURCE_SCENE) != old_sha:
                raise RuntimeError("STOP_SOURCE_CHANGED: no changes")
            if active(WORKER_SERVICE) is False:
                raise RuntimeError("STOP_REMOTE_WORKER_NOT_RUNNING")
            # Prevent unrelated file edits between preflight and sync.
            current = remote.request("/health", timeout=3)
            if current.get("versions") != remote_versions:
                raise RuntimeError("STOP_WORKER_CHANGED_SINCE_PREFLIGHT")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = BACKUP_ROOT / (stamp + "-" + str(os.getpid()))
            backup.mkdir(mode=0o700, parents=True)
            backup.chmod(0o700)
            present = {}
            for target in (DEST_SCENE, DEST_HINTS):
                present[target] = target.exists()
                if target.exists():
                    check_path(target)
                    shutil.copy2(target, backup / target.name)
                    (backup / target.name).chmod(0o600)
            print("BACKUP_OK:", backup)
            try:
                # Import dependency must exist before the new scene is activated.
                copy_atomic(SOURCE_HINTS, DEST_HINTS)
                copy_atomic(SOURCE_SCENE, DEST_SCENE)
                if digest(DEST_SCENE) != old_sha or digest(DEST_HINTS) != digest(SOURCE_HINTS):
                    raise RuntimeError("STOP_COPY_DIGEST_MISMATCH")
                for path in (DEST_SCENE, DEST_HINTS):
                    compile(path.read_bytes(), str(path), "exec")
                run("systemctl", "restart", WORKER_SERVICE)
                if not worker_health(remote, local_versions):
                    raise RuntimeError("STOP_WORKER_HEALTH_OR_VERSION_CHECK_FAILED")
            except Exception:
                # Restore both files and restart original compute worker on failure.
                for target in (DEST_SCENE, DEST_HINTS):
                    if present.get(target):
                        copy_atomic(backup / target.name, target)
                    elif target.exists() and not target.is_symlink():
                        target.unlink()
                try:
                    run("systemctl", "restart", WORKER_SERVICE)
                    print("ROLLBACK_OK: prior compute worker restored")
                except subprocess.CalledProcessError:
                    print("ROLLBACK_SERVICE_RESTART_FAILED: inspect worker service manually")
                raise
            print("SYNC_OK: skip_scene.py and hint module identical in controller and compute")
            print("HEALTH_OK: all worker protocol versions match")
            print("NO_MARKERS_OR_DATABASES_MODIFIED")
    finally:
        if timer_was_active:
            run("systemctl", "start", TIMER)
            print("TIMER_RESTORED: active")

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError,
            ValueError, SyntaxError) as exc:
        print("SYNC_ABORTED:", exc)
        raise SystemExit(1)
