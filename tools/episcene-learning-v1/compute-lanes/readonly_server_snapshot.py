#!/usr/bin/env python3
"""One-shot, READ-ONLY, credential-free EpiScene server diagnostic.

Only aggregate counts, allowlisted Python module hashes, service states,
CPU/RAM capacity, and job progress are printed. Never imports server code,
opens a provider stream, changes a job, restarts a service, or logs tokens.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, timedelta
import ast
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path("/opt/epimediahub/provisioning")
REMOTE = Path("/opt/epimediahub/analysis")
LEARN = Path("/opt/episcene-learning")
DB = Path("/var/lib/epimediahub/provisioning.db")
FDB = Path("/var/lib/episcene-learning/reference-round-40/feedback.sqlite3")

FILES = {
    "analysis_worker": ROOT / "skip_analysis_worker.py",
    "scheduler": ROOT / "skip_schedule.py",
    "scene": ROOT / "skip_scene.py",
    "scene_reliability": ROOT / "skip_scene_reliability.py",
    "analysis": ROOT / "skip_analysis.py",
    "automation": ROOT / "skip_automation.py",
    "release": ROOT / "skip_release.py",
    "manual_marker_handler": ROOT / "skip_markers.py",
    "remote_worker": REMOTE / "skip_remote_worker.py",
    "safe_release": LEARN / "safe_release_rollout.py",
    "feedback_learning": LEARN / "feedback_learning.py",
    "unified_bridge": LEARN / "unified" / "bridge.py",
}
SERVICES = (
    "epimediahub-provisioning.service",
    "epimediahub-skip-analysis.service",
    "epimediahub-analysis-worker.service",
    "episcene-safe-release-learning.service",
    "episcene-unified-sync.service",
    "episcene-safe-release-learning.timer",
    "episcene-unified-sync.timer",
)
MAX_FILE_BYTES = 2_000_000


def module_snapshot(files=FILES):
    result = {}
    for role, path in sorted(files.items()):
        try:
            if path.is_symlink() or not path.is_file():
                result[role] = {"state": "missing_or_symlink"}
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                result[role] = {"state": "unexpected_size"}
                continue
            contents = path.read_bytes()
            tree = ast.parse(contents.decode("utf-8"))
            result[role] = {
                "state": "present",
                "sha256": hashlib.sha256(contents).hexdigest(),
                "function_count": sum(
                    isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    for n in ast.walk(tree)),
            }
        except (OSError, UnicodeError, SyntaxError):
            result[role] = {"state": "unreadable_or_invalid"}
    return result


def invoke(args, *, timeout=4):
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=timeout, check=False)
        if r.returncode:
            return ""
        return (r.stdout or "")[:10000]
    except (OSError, subprocess.TimeoutExpired):
        return ""


def services_snapshot(names=SERVICES, call=invoke):
    result = {}
    for unit in names:
        value = call(["systemctl", "show", unit, "--no-pager",
                      "--property=ActiveState,SubState,UnitFileState"])
        data = {}
        for line in value.splitlines():
            k, _, v = line.partition("=")
            if k in ("ActiveState", "SubState", "UnitFileState"):
                if v in ("active", "inactive", "failed", "activating", "deactivating",
                         "dead", "running", "exited", "waiting", "enabled",
                         "disabled", "static", "not-found", "masked"):
                    data[k] = v
        result[unit] = data or {"state": "unavailable"}
    return result


def memory_available():
    result = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            if line.startswith(("MemTotal:", "MemAvailable:")):
                k, v = line.split(":", 1)
                result[k] = int(v.strip().split()[0]) * 1024
    except (OSError, UnicodeError, IndexError, ValueError):
        pass
    return result


def safe_readonly(path):
    if path.is_symlink() or not path.is_file():
        return None
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def table_columns(conn, name):
    if name not in ("skip_jobs", "skip_assets", "skip_records", "feedback_versions"):
        return set()
    return {r[1] for r in conn.execute("PRAGMA table_info(" + name + ")")}


def aggregate_jobs(conn):
    wanted = {
        "skip_jobs": {"asset_key", "status", "updated_at"},
        "skip_assets": {"asset_key", "playlist_id"},
    }
    if any(not cols <= table_columns(conn, name) for name, cols in wanted.items()):
        return {"state": "schema_unavailable"}
    result = {"8": {"counts": {}, "updated_last_24h": 0},
              "10": {"counts": {}, "updated_last_24h": 0}}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = conn.execute("""
        SELECT a.playlist_id,j.status,COUNT(*),MAX(j.updated_at)
        FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
        WHERE a.playlist_id IN (8,10)
        GROUP BY a.playlist_id,j.status
    """)
    for pid, state, count, recent in rows:
        if str(pid) not in result:
            continue
        status = str(state)
        if status not in (
                "queued", "running", "done", "partial", "review", "failed",
                "no_match", "no_reference", "retry", "cancelled", "disabled"):
            status = "other"
        result[str(pid)]["counts"][status] = int(count)
        # This is only "last status update of the whole group" not count updated.
        try:
            stamp = datetime.fromisoformat(str(recent).replace("Z", "+00:00"))
            if stamp.tzinfo is not None and stamp >= cutoff:
                result[str(pid)]["updated_within_24h"] = True
        except (ValueError, TypeError):
            pass
    return result


def manual_feedback_aggregate(conn):
    wanted = {
        "skip_records": {"asset_key", "source", "status"},
        "skip_assets": {"asset_key", "playlist_id"},
    }
    if any(not cols <= table_columns(conn, name) for name, cols in wanted.items()):
        return {"state": "schema_unavailable"}
    rows = conn.execute("""
        SELECT CASE WHEN a.playlist_id IN (8,10) THEN 'analysis'
                    ELSE 'other_playlists' END,
               r.status,COUNT(*)
        FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
        WHERE r.source='device'
        GROUP BY 1,2
    """)
    d = defaultdict(dict)
    for group, status, count in rows:
        key = status if status in ("approved", "pending", "rejected",
                                   "superseded") else "other"
        d[group][key] = int(count)
    return dict(d)


def feedback_aggregate(conn):
    required = {"decision", "active", "provenance", "playlist_id"}
    if not required <= table_columns(conn, "feedback_versions"):
        return {"state": "schema_unavailable"}
    rows = conn.execute("""
        SELECT CASE WHEN playlist_id IN (8,10) THEN 'analysis'
                    ELSE 'other_playlists' END,
               COUNT(*)
        FROM feedback_versions
        WHERE active=1 AND decision='positive'
          AND provenance IN ('device_authenticated_direct','admin_reviewed_machine')
        GROUP BY 1
    """)
    return {k: int(v) for k, v in rows}


def db_snapshot(path, aggregate):
    try:
        connection = safe_readonly(path)
        if connection is None:
            return {"state": "unavailable"}
        try:
            with connection:
                return {"state": "ok", "data": aggregate(connection)}
        finally:
            connection.close()
    except (OSError, sqlite3.Error, ValueError):
        return {"state": "unreadable"}


def collect():
    result = {
        "mode": "EPISCENE_READONLY_DIAGNOSTIC",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "cpu_cores_reported": os.cpu_count(),
        "load_average_per_cpu": (
            round(os.getloadavg()[0] / max(1, os.cpu_count() or 1), 3)
            if hasattr(os, "getloadavg") else None),
        "memory_bytes": memory_available(),
        "installed_components": module_snapshot(),
        "services": services_snapshot(),
        "analysis_jobs": db_snapshot(DB, aggregate_jobs),
        "manual_device_markers": db_snapshot(DB, manual_feedback_aggregate),
        "authenticated_feedback": db_snapshot(FDB, feedback_aggregate),
        "changes_made": False,
        "providers_contacted": 0,
        "workers_restarted": 0,
        "secrets_collected": False,
        "note": "Hashes and status are diagnostics, not proof of API compatibility",
    }
    return result


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, sort_keys=True, indent=2))
