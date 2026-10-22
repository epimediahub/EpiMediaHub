#!/usr/bin/env python3
"""Read-only EpiScene runtime/time-budget and release-blocker triage.

Never reads IPTV streams, modifies jobs, marks records as approved, or prints
customer/provider identities, secrets, episode names, source URLs, or raw logs.
Only aggregate counts and bounded, sanitized configuration facts are returned.
"""
from __future__ import annotations

import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess

DB = Path("/var/lib/epimediahub/provisioning.db")
PROVISIONING = Path("/opt/epimediahub/provisioning")
REMOTE = Path("/opt/epimediahub/analysis")
ANALYSIS_IDS = (8, 10)
SERVICE_NAMES = (
    "epimediahub-skip-analysis.service",
    "epimediahub-analysis-worker.service",
    "episcene-safe-release-learning.service",
)
KEYWORDS = re.compile(r"(timeout|deadline|budget|time_limit|max_time|limit_seconds|seconds_limit)", re.I)
LOG_RULES = {
    "timeouts": re.compile(r"\b(timeout|timed.out|deadline.exceeded|zeit.limit|zeitüberschreitung|time.limit)\b", re.I),
    "partial": re.compile(r"\bpartial\b", re.I),
    "review": re.compile(r"\breview\b", re.I),
    "no_match": re.compile(r"\bno.match\b", re.I),
    "auto_confirmed": re.compile(r"\bAUTO_CONFIRMED\b", re.I),
    "approved": re.compile(r"\bapproved\b", re.I),
}


def run(*args, timeout=8):
    try:
        proc = subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout, check=False)
        return proc.returncode, proc.stdout[:250000]
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def present(db, table):
    return bool(db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone())


def date_seconds(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return None


def inventory(db, now=None):
    """Recent job outcomes by *analysis* playlist; no customer inventory join."""
    if now is None:
        now = datetime.now(timezone.utc).timestamp()
    if not all(present(db, x) for x in ("skip_jobs", "skip_assets")):
        return {"status": "MISSING_JOB_OR_ASSET_TABLE"}
    columns = {r[1] for r in db.execute("PRAGMA table_info(skip_jobs)")}
    if not {"asset_key", "status", "updated_at"} <= columns:
        return {"status": "UNKNOWN_JOB_SCHEMA"}
    rows = db.execute("""
        SELECT a.playlist_id, j.status, j.updated_at, COUNT(*) AS amount
        FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
        WHERE a.playlist_id IN (8,10)
        GROUP BY a.playlist_id, j.status, j.updated_at
    """)
    result = {str(pid): {"status_counts": {}, "updated_last_24h": 0,
                         "running_over_15m": 0, "recent_partial": 0}
              for pid in ANALYSIS_IDS}
    for pid, status, stamp, amount in rows:
        bucket = result[str(pid)]
        name = str(status)[:32]
        bucket["status_counts"][name] = bucket["status_counts"].get(name, 0) + amount
        age = None if date_seconds(stamp) is None else now - date_seconds(stamp)
        if age is not None and 0 <= age <= 86400:
            bucket["updated_last_24h"] += amount
            if name == "partial":
                bucket["recent_partial"] += amount
        if name == "running" and age is not None and age > 900:
            bucket["running_over_15m"] += amount
    return result


def release_evidence(db):
    if not all(present(db, x) for x in ("skip_records", "skip_assets", "skip_auto_evidence")):
        return {"status": "EVIDENCE_TABLE_MISSING"}
    counts = Counter()
    rows = db.execute("""
        SELECT r.source, e.evidence_json
        FROM skip_records r
        JOIN skip_assets a ON a.asset_key=r.asset_key
        LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
        WHERE a.playlist_id IN (8,10)
          AND r.status='pending'
          AND r.segment_type IN ('intro','recap','outro')
          AND r.source IN ('audio','chapter','theintrodb','audio_repetition',
                           'auto_audio','episcene')
    """)
    for source, raw in rows:
        try:
            evidence = json.loads(raw or "{}")
            if not isinstance(evidence, dict):
                evidence = {}
        except (ValueError, TypeError):
            evidence = {}
        decision = evidence.get("decision")
        decision = decision if isinstance(decision, dict) else {}
        if evidence.get("audio_visual_disagreement") is True:
            label = "AUDIO_VISUAL_CONFLICT"
        elif evidence.get("method") == "episcene_consensus":
            label = ("VISUAL_AUTO_CONFIRMED_STILL_PENDING"
                     if decision.get("status") == "AUTO_CONFIRMED"
                     else "VISUAL_NOT_AUTO_CONFIRMED")
        elif evidence.get("episcene_required") is True:
            label = "MISSING_VISUAL_CONSENSUS"
        elif source == "audio_repetition":
            label = "AUDIO_REPETITION_NOT_ENOUGH"
        else:
            label = "OTHER_PRODUCTION_GATE"
        counts[label] += 1
    return dict(counts)


def configured_budgets():
    """AST-only numeric assignments; NEVER output code, secrets or raw files."""
    findings = {}
    for folder, filename in ((PROVISIONING, "skip_analysis_worker.py"),
                             (PROVISIONING, "skip_scene.py"),
                             (REMOTE, "skip_remote_worker.py")):
        path = folder / filename
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1000000:
            findings[filename] = {"status": "ABSENT_OR_UNEXPECTED"}
            continue
        try:
            content = path.read_bytes()
            tree = ast.parse(content.decode("utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            findings[filename] = {"status": "UNREADABLE_OR_INVALID"}
            continue
        variables = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                target_nodes = (node.targets if isinstance(node, ast.Assign) else [node.target])
                value = node.value
                if not isinstance(value, ast.Constant) or type(value.value) not in (int, float):
                    continue
                for target in target_nodes:
                    if not isinstance(target, ast.Name) or not KEYWORDS.search(target.id):
                        continue
                    if 0 < value.value <= 100000:
                        variables[target.id[:80]] = value.value
        findings[filename] = {
            "status": "PRESENT",
            "sha256_prefix": hashlib.sha256(content).hexdigest()[:16],
            "named_numeric_budget_assignments": dict(sorted(variables.items())),
        }
    return findings


def service_states():
    output = {}
    for unit in SERVICE_NAMES:
        rc, body = run("systemctl", "show", unit,
                       "-p", "ActiveState", "-p", "TimeoutStartUSec", timeout=5)
        if rc:
            output[unit] = {"status": "NOT_READABLE"}
            continue
        values = {}
        for line in body.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key == "ActiveState" and value in ("active", "inactive", "failed", "activating"):
                values["state"] = value
            elif key == "TimeoutStartUSec" and re.fullmatch(r"[0-9]+(ms|s|min|h)?|infinity", value):
                values["timeout"] = value
        output[unit] = values
    return output


def journal_counts():
    output = {}
    for unit in SERVICE_NAMES:
        rc, body = run("journalctl", "-u", unit, "-n", "500",
                       "--no-pager", "-o", "cat", timeout=12)
        if rc:
            output[unit] = {"status": "NOT_READABLE"}
            continue
        output[unit] = {
            key: sum(bool(regex.search(line)) for line in body.splitlines())
            for key, regex in LOG_RULES.items()
        }
    return output


def report(database=DB):
    if database.is_symlink() or not database.is_file():
        raise RuntimeError("Database missing or unexpected symlink")
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro",
                         uri=True, timeout=12) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        jobs = inventory(db)
        blockers = release_evidence(db)
    budgets = configured_budgets()
    services = service_states()
    journals = journal_counts()
    partial = sum(jobs.get(str(pid), {}).get("recent_partial", 0) for pid in ANALYSIS_IDS)
    timeout_signals = sum(x.get("timeouts", 0) for x in journals.values())
    return {
        "mode": "EPISCENE_READ_ONLY_RUNTIME_TRIAGE",
        "analysis_playlists": {"8": "4K ANALYSE", "10": "THE BEST"},
        "jobs": jobs,
        "pending_release_blockers": blockers,
        "worker_static_numeric_budgets": budgets,
        "systemd": services,
        "recent_journal_event_counts": journals,
        "time_budget_suspected": bool(partial or timeout_signals),
        "time_budget_not_proven_causal": True,
        "production_db_modified": False,
        "worker_files_modified": False,
        "marker_approvals_triggered": 0,
        "privacy": "Aggregates only; no raw logs, identifiers or credentials",
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DB)
    args = parser.parse_args()
    print(json.dumps(report(args.database), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
