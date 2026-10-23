#!/usr/bin/env python3
"""EpiScene: staged import of verified markers from all owned playlists.

Only a single pinned bridge source is changed; no analyzer, scheduler, player
or feedback DB code is modified. Preflight evaluates the exact proposed patch
against a PRIVATE temporary SQLite store before any live update. On failure,
restore the source and re-run the original sync, never force-approve markers.
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile

SOURCE = Path("/opt/episcene-learning/unified/bridge.py")
PIN = "db7ac24db2b2333d46ae504526a2db29578c91258f4cc4a226da235b6b36ed2e"
FEEDBACK = Path("/var/lib/episcene-learning/reference-round-40/feedback.sqlite3")
PRODUCTION = Path("/var/lib/epimediahub/provisioning.db")
STORE = Path("/var/lib/episcene-learning/unified-markers.sqlite3")
VENV = Path("/opt/epimediahub/provisioning/.venv/bin/python")
SYNC_SERVICE = "episcene-unified-sync.service"
ANALYSIS_SERVICE = "epimediahub-analysis-worker.service"
BACKUP_PARENT = Path("/var/lib/episcene-learning")
OLD = 'if r["playlist_id"] not in ANALYSIS_PLAYLISTS or r["kind"] not in KINDS:'
NEW = ('if (type(r["playlist_id"]) is not int or r["playlist_id"] < 1\n'
       '                    or r["kind"] not in KINDS):')
OLD_REPORT = '"from_playlists": list(ANALYSIS_PLAYLISTS),'
NEW_REPORT = '"from_playlists": sorted({x[2] for x in chosen}),'


class Stop(Exception):
    pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def command(args, timeout=70):
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("COMMAND_UNAVAILABLE_OR_TIMEOUT") from exc


def component(path, *, required=True):
    path = Path(path)
    if path.is_symlink() or (required and not path.is_file()):
        raise Stop("UNTRUSTED_COMPONENT_OR_MISSING")
    return path


def service_is_active(name):
    return command(["systemctl", "is-active", "--quiet", name], timeout=8).returncode == 0


def patch_source(raw):
    if sha(raw) != PIN:
        raise Stop("UNEXPECTED_BRIDGE_VERSION")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise Stop("INVALID_SOURCE_ENCODING") from exc
    if text.count(OLD) != 1 or text.count(OLD_REPORT) != 1:
        raise Stop("UNEXPECTED_BRIDGE_CONTRACT")
    patched = text.replace(OLD, NEW).replace(OLD_REPORT, NEW_REPORT)
    import ast
    ast.parse(patched)
    return patched.encode("utf-8")


def database_counts(path):
    component(path)
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro",
                             uri=True, timeout=8) as db:
            db.execute("PRAGMA query_only=ON")
            rows = db.execute(
                "SELECT CASE WHEN playlist_id IN (8,10) THEN 'analysis' "
                "ELSE 'other' END,COUNT(*) FROM verified_markers GROUP BY 1")
            d = {str(k): int(v) for k, v in rows}
            return {"analysis": d.get("analysis", 0), "other": d.get("other", 0)}
    except sqlite3.Error as exc:
        raise Stop("VERIFIED_STORE_UNREADABLE") from exc


def sync_to(source_path, destination):
    result = command([
        str(VENV), str(source_path), "sync-verified",
        "--feedback", str(FEEDBACK),
        "--production", str(PRODUCTION),
        "--store", str(destination),
    ], timeout=70)
    if result.returncode:
        raise Stop("STAGED_SYNC_FAILED")


def install_bytes(raw, previous_stat):
    fd, tmp = tempfile.mkstemp(prefix=".bridge-evidence-", dir=str(SOURCE.parent))
    try:
        os.fchmod(fd, stat.S_IMODE(previous_stat.st_mode))
        os.fchown(fd, previous_stat.st_uid, previous_stat.st_gid)
        with os.fdopen(fd, "wb") as writer:
            writer.write(raw)
            writer.flush()
            os.fsync(writer.fileno())
        fd = None
        os.replace(tmp, SOURCE)
    finally:
        if fd is not None:
            os.close(fd)
        if os.path.exists(tmp):
            os.unlink(tmp)


def preflight():
    if os.geteuid() != 0:
        raise Stop("ROOT_REQUIRED")
    for path in (SOURCE, FEEDBACK, PRODUCTION, STORE, VENV):
        component(path)
    if SOURCE.parent.is_symlink():
        raise Stop("SOURCE_DIRECTORY_SYMLINK")
    if not service_is_active(ANALYSIS_SERVICE):
        raise Stop("ANALYSIS_WORKER_INACTIVE")
    if not service_is_active("episcene-unified-sync.timer"):
        raise Stop("SYNC_TIMER_INACTIVE")
    base_stat = SOURCE.stat()
    if base_stat.st_uid != 0 or not stat.S_ISREG(base_stat.st_mode):
        raise Stop("SOURCE_OWNERSHIP_UNEXPECTED")
    original = SOURCE.read_bytes()
    candidate = patch_source(original)
    baseline = database_counts(STORE)
    return original, candidate, base_stat, baseline


def run(apply=False):
    original, candidate, stats, before = preflight()
    with tempfile.TemporaryDirectory(prefix=".episcene-bridge-stage-", dir=str(BACKUP_PARENT)) as temp:
        stage = Path(temp)
        candidate_script = SOURCE.parent / (".bridge-stage-" + sha(candidate)[:16] + ".py")
        if candidate_script.exists() or candidate_script.is_symlink():
            raise Stop("UNEXPECTED_STAGING_SCRIPT")
        # Same module directory as deployed bridge to preserve import resolution.
        fd = os.open(candidate_script, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(candidate)
            sync_to(candidate_script, stage / "candidate.sqlite3")
        finally:
            candidate_script.unlink(missing_ok=True)
        staged = database_counts(stage / "candidate.sqlite3")
        if staged["analysis"] < before["analysis"]:
            raise Stop("ANALYSIS_VERIFIED_MARKERS_WOULD_BE_LOST")
        if staged["other"] < 1:
            raise Stop("NO_AUTHENTICATED_OTHER_PLAYLIST_SOURCE_IMPORTED")
    result = dict(mode="VERIFIED_ALL_PLAYLIST_BRIDGE_STAGED",
                  preflight="PASS", before=before, candidate=staged,
                  production_source_modified=False, analysis_worker_restarted=False)
    if not apply:
        return result
    # Back up the exact binary and keep the backup private for rollback.
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_PARENT / ("bridge-backup-" + stamp + "-" + sha(original)[:12])
    if backup.exists() or backup.is_symlink():
        raise Stop("BACKUP_DIRECTORY_CONFLICT")
    backup.mkdir(mode=0o700)
    saved = backup / "bridge.py"
    fd = os.open(saved, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as w:
        w.write(original)
        w.flush()
        os.fsync(w.fileno())
    updated = False
    try:
        if sha(SOURCE.read_bytes()) != PIN:
            raise Stop("SOURCE_CHANGED_DURING_PREFLIGHT")
        install_bytes(candidate, stats)
        updated = True
        if command(["systemctl", "start", SYNC_SERVICE], timeout=90).returncode:
            raise Stop("LIVE_SYNC_FAILED")
        after = database_counts(STORE)
        if after["analysis"] < before["analysis"] or after["other"] < 1:
            raise Stop("LIVE_VERIFIED_IMPORT_INCOMPLETE")
        if not service_is_active(ANALYSIS_SERVICE):
            raise Stop("ANALYSIS_WORKER_NO_LONGER_ACTIVE")
        if not service_is_active("episcene-unified-sync.timer"):
            raise Stop("SYNC_TIMER_NO_LONGER_ACTIVE")
        return dict(result, applied=True, before=before, after=after,
                    source_backed_up=True, production_source_modified=True,
                    analysis_worker_still_active=True, sync_result="success")
    except (Stop, OSError, sqlite3.Error) as exc:
        reason = str(exc) if isinstance(exc, Stop) else "IO_ERROR"
        rollback_ok = True
        if updated:
            try:
                install_bytes(original, stats)
                rollback_ok = command(["systemctl", "start", SYNC_SERVICE], timeout=90).returncode == 0
            except (Stop, OSError):
                rollback_ok = False
        return dict(result, applied=False, stop_reason=reason,
                    source_restored=rollback_ok, backup_preserved=True)


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        summary = run(apply=args.apply)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if (not args.apply or summary.get("applied")) else 2
    except Stop as exc:
        print(json.dumps({"status": "STOP_NO_CHANGES", "reason": str(exc)},
                         sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
