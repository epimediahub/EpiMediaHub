#!/usr/bin/env python3
"""Guarded WAL read-access fix for the EpiScene unified sync ONLY.

The existing service reads provisioning.db via SQLite mode=ro, but a systemd
ProtectSystem=strict mount can prevent WAL shared-memory access. This adds a
narrow ReadWritePaths=/var/lib/epimediahub exception to ONE existing service
so SQLite can use its WAL files; never chmods/chowns databases, edits workers,
starts additional provider streams, or restarts analysis services.

If the existing service's identity/config does not match the reviewed install,
or if the service still fails, fail closed and remove the exception.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

SERVICE = "episcene-unified-sync.service"
WORKER = "epimediahub-analysis-worker.service"
DB = Path("/var/lib/epimediahub/provisioning.db")
WRITE_ROOT = DB.parent
DROPIN_DIR = Path("/etc/systemd/system/episcene-unified-sync.service.d")
DROPIN = DROPIN_DIR / "90-episcene-sqlite-wal.conf"
UNIT_SOURCE = Path("/opt/episcene-learning/unified/bridge.py")
# Exact installed bridge digest from 2026-10-23 read-only inventory; fail if drifted.
PINNED_BRIDGE_SHA256 = "db7ac24db2b2333d46ae504526a2db29578c91258f4cc4a226da235b6b36ed2e"
CONTENT = ("# Permit read-only SQLite WAL consumers to access the active -shm file.\n"
           "# The bridge itself must retain mode=ro and PRAGMA query_only=ON.\n"
           "[Service]\n"
           "ReadWritePaths=/var/lib/epimediahub\n")
PROPERTIES = ("ActiveState", "Result", "ExecMainStatus", "User", "ProtectSystem",
              "ReadWritePaths", "ExecStart", "FragmentPath", "PrivateNetwork")


class Stop(Exception):
    pass


def command(*args, timeout=20):
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stop("SYSTEMCTL_UNAVAILABLE") from exc


def properties(service):
    r = command("systemctl", "show", service, "--no-pager",
                *(f"-p{x}" for x in PROPERTIES), timeout=8)
    if r.returncode:
        raise Stop("SERVICE_PROPERTIES_UNAVAILABLE")
    fields = {}
    for line in r.stdout.splitlines():
        name, sep, value = line.partition("=")
        if sep and name in PROPERTIES:
            fields[name] = value
    return fields


def local_db_preflight(database=DB):
    if database.is_symlink() or not database.is_file() or database.parent.is_symlink():
        raise Stop("PRODUCTION_DB_MISSING_OR_SYMLINK")
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(database) + suffix)
        if sidecar.is_symlink() or not sidecar.is_file():
            raise Stop("EXPECTED_WAL_SIDECAR_MISSING")
    try:
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro",
                             uri=True, timeout=6) as con:
            con.execute("PRAGMA query_only=ON")
            columns = con.execute("PRAGMA table_info(skip_assets)").fetchall()
        if not columns:
            raise Stop("PRODUCTION_SCHEMA_UNAVAILABLE")
    except sqlite3.Error as exc:
        raise Stop("HOST_DB_READ_FAILED") from exc


def validate(props):
    if os.geteuid() != 0:
        raise Stop("ROOT_REQUIRED")
    if props.get("User") != "root":
        raise Stop("UNEXPECTED_SERVICE_IDENTITY")
    if props.get("ProtectSystem") != "strict":
        raise Stop("UNEXPECTED_SANDBOX_POLICY")
    if props.get("ActiveState") not in ("failed", "inactive"):
        raise Stop("SERVICE_NOT_IDLE")
    if str(DB.parent) in props.get("ReadWritePaths", ""):
        raise Stop("WRITE_PATH_ALREADY_ALLOWED")
    start = props.get("ExecStart", "")
    if (str(UNIT_SOURCE) not in start or " sync-verified " not in start
            or str(DB) not in start):
        raise Stop("UNKNOWN_SERVICE_COMMAND")
    fragment = props.get("FragmentPath", "")
    if fragment != "/etc/systemd/system/episcene-unified-sync.service":
        raise Stop("UNKNOWN_SYSTEMD_UNIT_LOCATION")
    if Path(fragment).is_symlink():
        raise Stop("UNIT_SYMLINK")
    if UNIT_SOURCE.is_symlink() or not UNIT_SOURCE.is_file():
        raise Stop("UNIFIED_BRIDGE_UNAVAILABLE")
    if hashlib.sha256(UNIT_SOURCE.read_bytes()).hexdigest() != PINNED_BRIDGE_SHA256:
        raise Stop("UNIFIED_BRIDGE_VERSION_DRIFT")
    if DROPIN_DIR.is_symlink() or DROPIN.exists() or DROPIN.is_symlink():
        raise Stop("EXISTING_DROPIN_REQUIRES_REVIEW")
    if WRITE_ROOT.is_symlink() or not WRITE_ROOT.is_dir():
        raise Stop("DB_DIRECTORY_UNEXPECTED")
    return True


def unit_success(props):
    return props.get("Result") == "success" and props.get("ExecMainStatus") == "0"


def marker_count(path=Path("/var/lib/episcene-learning/unified-markers.sqlite3")):
    try:
        if path.is_symlink() or not path.is_file():
            return None
        with sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=5) as db:
            return int(db.execute("SELECT COUNT(*) FROM verified_markers").fetchone()[0])
    except (OSError, sqlite3.Error):
        return None


def install_dropin():
    created_dir = False
    if not DROPIN_DIR.exists():
        DROPIN_DIR.mkdir(mode=0o755)
        created_dir = True
    if DROPIN_DIR.is_symlink():
        raise Stop("DROPIN_DIR_SYMLINK")
    try:
        fd = os.open(DROPIN, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o644)
    except OSError as exc:
        raise Stop("DROPIN_CREATION_FAILED") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(CONTENT)
            f.flush()
            os.fsync(f.fileno())
    except (OSError, UnicodeError):
        DROPIN.unlink(missing_ok=True)
        raise
    return created_dir


def undo(created_dir):
    try:
        DROPIN.unlink(missing_ok=True)
        if created_dir:
            DROPIN_DIR.rmdir()
        command("systemctl", "daemon-reload", timeout=15)
        return True
    except (OSError, Stop):
        return False


def run(*, apply=False):
    state = {"mode": "EPISCENE_SQLITE_WAL_GUARDED_FIX",
             "applied": False, "analysis_worker_restarted": False,
             "provisioning_database_written_by_tool": False,
             "marker_count_before": None, "marker_count_after": None}
    props = properties(SERVICE)
    validate(props)
    local_db_preflight()
    if properties(WORKER).get("ActiveState") != "active":
        raise Stop("ANALYSIS_WORKER_NOT_ACTIVE")
    state["marker_count_before"] = marker_count()
    if not apply:
        return dict(state, preflight="PASS", changes_made=0)
    created_dir = False
    dropin_created = False
    try:
        created_dir = install_dropin()
        dropin_created = True
        if command("systemctl", "daemon-reload", timeout=15).returncode:
            raise Stop("DAEMON_RELOAD_FAILED")
        started = command("systemctl", "start", SERVICE, timeout=90)
        if started.returncode:
            raise Stop("SYNC_START_FAILED")
        synced = properties(SERVICE)
        if not unit_success(synced):
            raise Stop("SYNC_RESULT_NOT_SUCCESS")
        if properties(WORKER).get("ActiveState") != "active":
            raise Stop("ANALYSIS_WORKER_UNEXPECTEDLY_INACTIVE")
        state["marker_count_after"] = marker_count()
        if state["marker_count_after"] is None:
            raise Stop("VERIFIED_STORE_UNAVAILABLE")
        state.update(applied=True, sync_result="success",
                     analysis_worker_still_active=True)
        return state
    except (Stop, OSError, sqlite3.Error) as exc:
        reason = str(exc) if isinstance(exc, Stop) else "IO_ERROR"
        rolled_back = undo(created_dir) if dropin_created else True
        return dict(state, applied=False, rolled_back=rolled_back,
                    stop_reason=reason)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = run(apply=args.apply)
        print(json.dumps(result, sort_keys=True, indent=2))
        if args.apply and not result["applied"]:
            return 2
        return 0
    except Stop as exc:
        print(json.dumps({"mode": "EPISCENE_SQLITE_WAL_GUARDED_FIX",
                          "status": "STOP_NO_CHANGES", "reason": str(exc),
                          "workers_restarted": 0}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
