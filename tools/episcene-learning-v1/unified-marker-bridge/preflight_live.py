#!/usr/bin/env python3
"""EpiScene production preflight, strictly read-only and privacy-preserving.

No private URLs, playlist credentials, customer/device IDs, stream IDs,
database rows, exception traces or SSH configuration are emitted.
Use this on the EpiScene Hetzner host BEFORE any deployment.
"""
from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
from pathlib import Path

DEFAULTS = {
    "production_db": "/var/lib/epimediahub/provisioning.db",
    "feedback_db": "/var/lib/episcene-learning/reference-round-40/feedback.sqlite3",
    "unified_db": "/var/lib/episcene-learning/unified-markers.sqlite3",
    "backend_root": "/opt/epimediahub/provisioning",
    "bridge_root": "/opt/episcene-learning/unified",
    "service_unit": "/etc/systemd/system/episcene-unified-sync.service",
    "timer_unit": "/etc/systemd/system/episcene-unified-sync.timer",
}

REQUIRED_PRODUCTION = {
    "skip_assets": {"asset_key", "playlist_id", "title", "season", "episode", "duration_ms"},
    "skip_records": {"id", "asset_key", "start_ms", "end_ms", "segment_type", "status"},
}
REQUIRED_FEEDBACK = {"marker_id", "asset_key", "playlist_id", "season",
                     "episode", "kind", "decision", "active", "start_ms",
                     "end_ms", "provenance", "reviewed_at"}


def regular_file(path):
    """Reject symlinks at the final component; never read their destination."""
    p = Path(path)
    try:
        return p.is_file() and not p.is_symlink() and stat.S_ISREG(p.lstat().st_mode)
    except OSError:
        return False


def inspect_db(path, required_tables):
    if not regular_file(path):
        return {"exists": False, "readable": False, "schema_ok": False}
    p = Path(path)
    try:
        # SQLite immutable mode suppresses journal creation; safe for a
        # stable snapshot, but not for a concurrently active WAL database.
        # mode=ro remains transactionally consistent for an active WAL source.
        with sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True, timeout=3) as db:
            db.execute("PRAGMA query_only=ON")
            valid = True
            for table, columns in required_tables.items():
                observed = {r[1] for r in db.execute("PRAGMA table_info(" + table + ")")}
                if not columns <= observed:
                    valid = False
            return {"exists": True, "readable": True, "schema_ok": valid}
    except (sqlite3.Error, OSError, ValueError):
        return {"exists": True, "readable": False, "schema_ok": False}


def systemd_active(unit):
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", unit],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False, timeout=4)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def diagnostic(paths=None, active=None):
    p = dict(DEFAULTS)
    if paths is not None:
        p.update(paths)
    source = inspect_db(p["production_db"], REQUIRED_PRODUCTION)
    feedback = inspect_db(p["feedback_db"], {"feedback_versions": REQUIRED_FEEDBACK})
    backend = Path(p["backend_root"])
    code = {name: regular_file(backend / name)
            for name in ("skip_markers.py", "skip_release.py", "skip_analysis.py")}
    bridge = Path(p["bridge_root"])
    bridge_present = all(regular_file(bridge / file) for file in
                         ("bridge.py", "runtime_integration.py"))
    active = systemd_active("epimediahub-provisioning.service") if active is None else active
    current_install = {
        "verified_store_exists": regular_file(p["unified_db"]),
        "bridge_files_exist": bridge_present,
        "sync_unit_exists": regular_file(p["service_unit"]),
        "sync_timer_exists": regular_file(p["timer_unit"]),
    }
    ready = bool(source["schema_ok"] and feedback["schema_ok"] and
                 all(code.values()) and active)
    # Do not infer running API integration from the presence of these files.
    return {
        "inspection_mode": "READ_ONLY",
        "production_db": source,
        "authenticated_feedback_db": feedback,
        "existing_backend_file_checks": code,
        "existing_backend_active": bool(active),
        "unified_snapshot_install": current_install,
        "preflight_for_private_snapshot": "PASS" if ready else "BLOCKED",
        "public_marker_api_connected": "NOT_VERIFIED",
        "current_android_player_connected": "NOT_VERIFIED",
        "actual_cut_fingerprint_generator": "NOT_VERIFIED",
        "analysis_stream_limits": "NOT_VERIFIED",
        "no_database_or_service_modified": True,
        "privacy": "No provider/customer/device identifiers, access tokens or URLs included",
    }


def main():
    print(json.dumps(diagnostic(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
