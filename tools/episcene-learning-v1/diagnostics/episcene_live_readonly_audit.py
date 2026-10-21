#!/usr/bin/env python3
"""EpiScene production preflight (read-only). No writes, provider requests, restarts or secrets."""
import ast
import collections
import datetime as dt
import hashlib
import json
import pathlib
import sqlite3
import subprocess
import sys

DB = pathlib.Path("/var/lib/epimediahub/provisioning.db")
ROOT = pathlib.Path("/opt/epimediahub/provisioning")
LEARN = pathlib.Path("/opt/episcene-learning")
MODULES = ["skip_analysis_worker.py", "skip_automation.py", "skip_scene.py",
           "skip_release.py", "skip_schedule.py", "skip_visual.py",
           "skip_detector_v2.py", "skip_detector_v3.py",
           "skip_source_preferences.py", "skip_scene_reliability.py",
           "skip_tail_check.py", "skip_variant_reuse.py"]
LEARN_MODULES = ["safe_release_rollout.py", "safe_release_rollout_v2.py",
                 "reload_when_idle.py", "feedback_learning.py"]
UNITS = ["epimediahub-provisioning.service", "epimediahub-analysis-worker.service",
         "epimediahub-skip-analysis.service", "epimediahub-skip-analysis.timer",
         "episcene-safe-release-learning.service", "episcene-safe-release-learning.timer",
         "episcene-visual-peer-reload.service", "episcene-visual-peer-reload.timer",
         "episcene-owner-learning-shadow.service", "episcene-owner-learning-shadow.timer",
         "episcene-learning-reference-40.service", "episcene-learning-reference-40.timer"]
PROPS = ["LoadState", "ActiveState", "SubState", "UnitFileState",
         "ExecMainStatus", "ExecMainStartTimestamp", "DropInPaths"]
FLAGS = {
    "reload_pending": "/var/lib/epimediahub/episcene-visual-peer-reload-pending",
    "timer_paused_by_reload": "/var/lib/epimediahub/episcene-visual-peer-analysis-timer-paused",
}

def run(*args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=8, check=False)
        return p.stdout if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None

def services():
    info = {}
    for name in UNITS:
        raw = run("systemctl", "show", name, "--no-pager",
                  "--property=" + ",".join(PROPS))
        data = dict(line.split("=", 1) for line in (raw or "").splitlines() if "=" in line)
        if data.get("LoadState") != "not-found":
            info[name] = {key: data[key][:240] for key in PROPS if data.get(key)}
    timers = run("systemctl", "list-timers", "--all", "--no-pager", "--no-legend")
    return info, [line.strip()[:210] for line in (timers or "").splitlines()
                  if "episcene" in line.lower() or "skip-analysis" in line.lower()]

def version(path):
    if path.is_symlink():
        return {"status": "symlink_not_read"}
    if not path.is_file():
        return {"status": "missing"}
    try:
        content = path.read_bytes()
        result = {"sha256": hashlib.sha256(content).hexdigest()[:20],
                  "mtime_utc": dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()}
        # AST parsing does not execute modules; only non-sensitive numeric budget constants.
        try:
            tree = ast.parse(content, filename=path.name)
            const = {}
            for node in tree.body:
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    val = node.value
                    for target in targets:
                        if (isinstance(target, ast.Name) and
                            any(x in target.id.upper() for x in ("TIMEOUT", "BUDGET", "MAX_REQUEUE", "MAX_DAILY", "MAX_NEW_PER_RUN", "MAX_PER_PLAYLIST")) and
                            isinstance(val, ast.Constant) and type(val.value) in (int, float)):
                            const[target.id] = val.value
            if const:
                result["numeric_limits"] = const
        except (SyntaxError, ValueError, UnicodeDecodeError):
            result["ast"] = "unavailable"
        return result
    except OSError:
        return {"status": "permission_or_io_error"}

def table(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

def cols(db, name):
    return {row[1] for row in db.execute("PRAGMA table_info(" + name + ")")}

def query(db, sql):
    try:
        return [dict(row) for row in db.execute(sql)]
    except sqlite3.Error as error:
        return [{"error": type(error).__name__}]

def database():
    result = {}
    if not DB.is_file() or DB.is_symlink():
        return {"status": "missing_or_symlink"}
    try:
        with sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=8) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            relevant = ["skip_analysis_playlists", "skip_analysis_sources", "skip_auto_settings",
                        "skip_release_settings", "skip_language_priority", "skip_assets",
                        "skip_jobs", "skip_records", "skip_auto_evidence",
                        "skip_scene_windows", "skip_scene_window_versions",
                        "skip_auto_blocks", "episcene_safe_release_retries"]
            result["tables"] = {t: table(db, t) for t in relevant}
            for name in ("skip_analysis_playlists", "skip_analysis_sources",
                         "skip_auto_settings", "skip_release_settings"):
                if not table(db, name):
                    continue
                columns = cols(db, name)
                allowed = [c for c in ("id", "playlist_id", "enabled", "archived", "paused")
                           if c in columns]
                selector = "playlist_id" if "playlist_id" in columns else "id"
                if allowed and selector in columns:
                    result[name] = query(db, "SELECT " + ",".join(allowed) + " FROM " + name +
                                         " WHERE " + selector + " IN (8,10) ORDER BY " + selector)
                else:
                    result[name + "_schema"] = sorted(columns)
            if result["tables"]["skip_jobs"] and result["tables"]["skip_assets"]:
                result["jobs"] = query(db, """
                   SELECT a.playlist_id, j.status, COUNT(*) jobs,
                          COUNT(DISTINCT a.asset_key) distinct_assets
                   FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
                   WHERE a.playlist_id IN (8,10)
                   GROUP BY a.playlist_id, j.status
                   ORDER BY a.playlist_id, j.status""")
            if result["tables"]["skip_records"] and result["tables"]["skip_assets"]:
                result["markers"] = query(db, """
                   SELECT a.playlist_id, r.segment_type, r.source, r.status,
                          COUNT(*) n FROM skip_records r
                   JOIN skip_assets a ON a.asset_key=r.asset_key
                   WHERE a.playlist_id IN (8,10)
                   GROUP BY a.playlist_id,r.segment_type,r.source,r.status
                   ORDER BY a.playlist_id,r.segment_type,r.source,r.status""")
            if result["tables"]["skip_language_priority"] and result["tables"]["skip_assets"]:
                c = cols(db, "skip_language_priority")
                if {"asset_key", "priority"} <= c:
                    result["language_priority"] = query(db, """
                       SELECT a.playlist_id, p.priority, COUNT(*) assets
                       FROM skip_language_priority p JOIN skip_assets a ON a.asset_key=p.asset_key
                       WHERE a.playlist_id IN (8,10)
                       GROUP BY a.playlist_id,p.priority
                       ORDER BY a.playlist_id,p.priority""")
            if result["tables"]["episcene_safe_release_retries"]:
                result["retry_ledger"] = query(db, """
                  SELECT COUNT(*) unique_assets,
                         COUNT(DISTINCT substr(last_requeued_utc,1,10)) days
                  FROM episcene_safe_release_retries""")
    except (sqlite3.Error, OSError) as error:
        result["error"] = type(error).__name__
    return result

def diagnose(data):
    findings = []
    db = data["database"]
    if db.get("status") or db.get("error"):
        findings.append({"severity":"BLOCKER", "code":"DB_UNAVAILABLE",
                         "detail":"Production SQLite could not be inspected"})
        return findings
    available = {x.get("id") for x in db.get("skip_analysis_playlists", [])}
    for playlist in (8, 10):
        if playlist not in available:
            findings.append({"severity":"CHECK", "code":"ANALYSIS_PLAYLIST_MISSING",
                             "playlist_id":playlist})
        for t in ("skip_analysis_sources", "skip_auto_settings", "skip_release_settings"):
            entries = [x for x in db.get(t, []) if x.get("playlist_id") == playlist]
            if entries and any(x.get("enabled") == 0 for x in entries):
                findings.append({"severity":"CONFLICT", "code":"DISABLED_GATE",
                                 "playlist_id":playlist, "table":t})
    if data["flags"]["timer_paused_by_reload"]:
        findings.append({"severity":"CHECK", "code":"ANALYSIS_TIMER_PAUSED_FOR_RELOAD"})
    if data["flags"]["reload_pending"]:
        findings.append({"severity":"CHECK", "code":"SCENE_RELOAD_STILL_PENDING"})
    for name, entry in data["services"].items():
        if name.endswith(".timer") and entry.get("UnitFileState") == "enabled" and entry.get("ActiveState") != "active":
            findings.append({"severity":"CONFLICT", "code":"ENABLED_TIMER_NOT_RUNNING", "unit":name})
    return findings

def main():
    data = {
        "audit_version": 1,
        "mode": "READ_ONLY_NO_PROVIDER_IO_NO_RESTARTS",
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "services": {},
        "timers": [],
        "modules": {},
        "flags": {k: pathlib.Path(p).exists() for k,p in FLAGS.items()},
        "database": {}
    }
    data["services"], data["timers"] = services()
    data["modules"] = {p:version(base / p) for base, names in
                       ((ROOT, MODULES), (LEARN, LEARN_MODULES)) for p in names}
    data["database"] = database()
    data["findings"] = diagnose(data)
    data["limitations"] = ["Files on disk do not prove which Python modules a live process imported.",
                           "Static/SQLite checks cannot establish visual accuracy or a correct approval policy.",
                           "No credentials, provider URLs, customer names or episode titles included."]
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))

if __name__ == "__main__":
    main()
