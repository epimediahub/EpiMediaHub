#!/usr/bin/env python3
"""EpiScene follow-up: read-only diagnosis of failed unified sync and manual marks.

Reports only allowlisted error categories, aggregate counts and service state.
Raw journal lines, episode names, provider URLs, device/customer IDs, credentials
and SQL text are never printed. No service restarts or database writes.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sqlite3
import subprocess

PROD = Path("/var/lib/epimediahub/provisioning.db")
LEARN = Path("/var/lib/episcene-learning/reference-round-40/feedback.sqlite3")
KNOWLEDGE = Path("/var/lib/episcene-learning/unified-markers.sqlite3")
UNITS = ("episcene-unified-sync.service", "episcene-unified-sync.timer",
         "episcene-safe-release-learning.service",
         "episcene-safe-release-learning.timer",
         "epimediahub-analysis-worker.service",
         "epimediahub-skip-analysis.service")

ERRORS = {
    "permission_denied": r"permission.denied|access.denied|operation.not.permitted",
    "database_locked": r"database.is.locked|database.is.busy",
    "database_open_failed": r"unable.to.open.database|cannot.open.database",
    "database_schema_mismatch": r"no.such.table|no.such.column|schema.mismatch|incompatible.schema",
    "missing_dependency": r"module.not.found|modulenotfounderror|importerror",
    "missing_file": r"no.such.file.or.directory|filenotfounderror",
    "invalid_file_permissions": r"untrusted.file|unexpected.symlink|mode.must.be|chmod",
    "python_exception": r"traceback|valueerror|runtimeerror|operationalerror|typeerror",
    "service_timeout": r"timed.out|timeout|deadline.exceeded",
    "worker_version_or_contract": r"worker.version|signature.mismatch|contract.mismatch|schema.contract",
}
ALLOWED_STATUS = frozenset(("queued", "running", "done", "failed", "review",
                            "partial", "no_match", "no_reference",
                            "pending", "approved", "superseded", "rejected",
                            "disabled", "stale", "cancelled", "expired", "retry"))


def safe_command(command, *, timeout=8, max_chars=100_000):
    try:
        proc = subprocess.run(command, capture_output=True, text=True,
                              timeout=timeout, check=False)
        return proc.returncode, proc.stdout[:max_chars]
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def unit_states(call=safe_command):
    output = {}
    for unit in UNITS:
        rc, data = call(["systemctl", "show", "--no-pager", unit,
                         "-p", "ActiveState", "-p", "SubState",
                         "-p", "Result", "-p", "ExecMainStatus",
                         "-p", "UnitFileState"])
        properties = {}
        if rc == 0:
            for line in data.splitlines():
                name, sep, value = line.partition("=")
                if sep and name in ("ActiveState", "SubState", "Result", "UnitFileState"):
                    if re.fullmatch(r"[a-z][a-z0-9_-]{0,35}", value):
                        properties[name] = value
                elif name == "ExecMainStatus" and value.isdecimal():
                    properties[name] = int(value)
        output[unit] = properties or {"state": "unavailable"}
    return output


def journal_error_categories(call=safe_command):
    rc, data = call(["journalctl", "-u", "episcene-unified-sync.service",
                     "-n", "80", "--no-pager", "-o", "cat"],
                    timeout=10, max_chars=120_000)
    if rc:
        return {"state": "unavailable"}
    lines = data.splitlines()
    categories = Counter()
    for line in lines:
        lowered = line.casefold()
        for key, pattern in ERRORS.items():
            if re.search(pattern, lowered):
                categories[key] += 1
    return {"state": "ok", "journal_lines_read": len(lines),
            "error_categories": dict(categories),
            "raw_logs_exported": False}


def read_only(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        return None
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro",
                         uri=True, timeout=6)
    db.execute("PRAGMA query_only=ON")
    return db


def columns(db, table):
    if table not in ("skip_records", "skip_assets", "feedback_versions",
                     "verified_markers", "skip_jobs"):
        return set()
    return {item[1] for item in db.execute("PRAGMA table_info(" + table + ")")}


def scan_marker_counts(db):
    if not {"asset_key", "source", "status"} <= columns(db, "skip_records"):
        return {"state": "schema_unavailable"}
    if not {"asset_key", "playlist_id"} <= columns(db, "skip_assets"):
        return {"state": "schema_unavailable"}
    rows = db.execute("""
      SELECT CASE WHEN a.playlist_id IN (8,10) THEN 'analysis'
                  ELSE 'other_playlists' END,
             r.status,COUNT(*)
      FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
      WHERE r.source='device'
      GROUP BY 1,2
    """)
    result = {}
    for group, status, count in rows:
        key = str(status)
        if key not in ALLOWED_STATUS:
            key = "unrecognized"
        result.setdefault(str(group), {})[key] = int(count)
    return result


def scan_job_states(db):
    if not {"asset_key", "status"} <= columns(db, "skip_jobs"):
        return {"state": "schema_unavailable"}
    if not {"asset_key", "playlist_id"} <= columns(db, "skip_assets"):
        return {"state": "schema_unavailable"}
    counts = {}
    for pid, status, count in db.execute("""
        SELECT a.playlist_id, j.status, COUNT(*)
        FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
        WHERE a.playlist_id IN (8,10)
        GROUP BY a.playlist_id,j.status
    """):
        key = str(status)
        if key not in ALLOWED_STATUS:
            key = "unrecognized"
        counts.setdefault(str(pid), {})[key] = (
            counts.setdefault(str(pid), {}).get(key, 0) + int(count))
    return counts


def scan_feedback(db):
    if not {"active", "decision", "provenance", "playlist_id"} <= columns(db, "feedback_versions"):
        return {"state": "schema_unavailable"}
    entries = db.execute("""
        SELECT CASE WHEN playlist_id IN (8,10) THEN 'analysis'
                    ELSE 'other_playlists' END,
               active, decision, provenance, COUNT(*)
        FROM feedback_versions
        GROUP BY 1,2,3,4
    """).fetchall()
    result = {}
    for group, active, decision, provenance, count in entries:
        label = ("verified_positive" if active == 1 and decision == "positive"
                 and provenance in ("device_authenticated_direct", "admin_reviewed_machine")
                 else "other_feedback_records")
        result.setdefault(str(group), {})[label] = (
            result.setdefault(str(group), {}).get(label, 0) + int(count))
    return result


def scan_knowledge(db):
    required = {"playlist_id"}
    if not required <= columns(db, "verified_markers"):
        return {"state": "schema_unavailable"}
    out = {"analysis": 0, "other_playlists": 0}
    for pid, count in db.execute("SELECT playlist_id,COUNT(*) FROM verified_markers GROUP BY playlist_id"):
        if pid in (8, 10):
            out["analysis"] += int(count)
        else:
            out["other_playlists"] += int(count)
    return out


def db_report(path, scanner):
    try:
        db = read_only(path)
        if db is None:
            return {"state": "unavailable"}
        try:
            db.execute("BEGIN")
            return {"state": "ok", "data": scanner(db)}
        finally:
            db.close()
    except (OSError, sqlite3.Error, ValueError):
        return {"state": "unreadable"}


def report():
    return {
        "mode": "EPISCENE_UNIFIED_SYNC_FOLLOWUP_READ_ONLY",
        "units": unit_states(),
        "unified_sync_journal": journal_error_categories(),
        "manual_markers": db_report(PROD, scan_marker_counts),
        "analysis_job_statuses": db_report(PROD, scan_job_states),
        "authenticated_feedback": db_report(LEARN, scan_feedback),
        "verified_knowledge": db_report(KNOWLEDGE, scan_knowledge),
        "services_restarted": 0, "markers_approved": 0,
        "production_writes": 0, "provider_connections": 0,
        "raw_journal_text_returned": False,
    }


if __name__ == "__main__":
    print(json.dumps(report(), ensure_ascii=False, indent=2, sort_keys=True))
