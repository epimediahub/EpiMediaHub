#!/usr/bin/env python3
"""Read-only triage of SQLite WAL and systemd sandbox access for EpiScene.

Does not print SQLite contents or service environment, raw log lines, secret
paths, or customer identifiers. No PRAGMA that changes journal settings.
Never restarts services or modifies database permissions.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import stat
import subprocess

DB = Path("/var/lib/epimediahub/provisioning.db")
SERVICE = "episcene-unified-sync.service"
PROPERTIES = (
    "ActiveState", "SubState", "Result", "ExecMainStatus",
    "User", "Group", "ProtectSystem", "PrivateTmp", "PrivateUsers",
    "DynamicUser", "ReadWritePaths", "ReadOnlyPaths",
    "InaccessiblePaths", "TemporaryFileSystem", "RootDirectory",
)


def details(path):
    path = Path(path)
    try:
        if path.is_symlink():
            return {"state": "symlink"}
        s = path.stat()
        kind = "directory" if stat.S_ISDIR(s.st_mode) else "file" if stat.S_ISREG(s.st_mode) else "other"
        return {"state": "present", "type": kind, "mode_octal": format(stat.S_IMODE(s.st_mode), "04o"),
                "owner_uid": s.st_uid, "group_gid": s.st_gid,
                "size_bytes": s.st_size if kind == "file" else None}
    except FileNotFoundError:
        return {"state": "missing"}
    except (OSError, ValueError):
        return {"state": "unreadable"}


def sqlite_probe(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        return {"state": "path_unavailable"}
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=4) as con:
            con.execute("PRAGMA query_only=ON")
            count = len(con.execute("PRAGMA table_info(skip_assets)").fetchall())
            return {"state": "readable", "skip_assets_field_count": count,
                    "schema_present": count >= 5}
    except sqlite3.Error as exc:
        code = getattr(exc, "sqlite_errorname", None)
        if code not in (
            "SQLITE_CANTOPEN", "SQLITE_READONLY", "SQLITE_BUSY",
            "SQLITE_IOERR", "SQLITE_PERM", "SQLITE_CORRUPT", "SQLITE_NOTADB",
        ):
            code = "SQLITE_OTHER"
        return {"state": "read_failed", "sqlite_error_code": code}
    except (ValueError, OSError):
        return {"state": "read_failed", "sqlite_error_code": "OS_ACCESS"}


def service_properties(call=subprocess.run):
    try:
        response = call(
            ["systemctl", "show", SERVICE, "--no-pager", *(f"-p{x}" for x in PROPERTIES)],
            capture_output=True, text=True, timeout=7, check=False,
        )
        if response.returncode != 0:
            return {"state": "not_readable"}
        result = {}
        for line in response.stdout.splitlines():
            key, separator, value = line.partition("=")
            if not separator or key not in PROPERTIES:
                continue
            if key in ("ReadWritePaths", "ReadOnlyPaths", "InaccessiblePaths",
                       "TemporaryFileSystem", "RootDirectory"):
                # Systemd values may include arbitrary mount details or paths;
                # report only whether a property is configured.
                result[key] = {"configured": bool(value.strip())}
            elif key in ("User", "Group"):
                # Do not expose a user-supplied service identity.
                result[key] = {"configured": bool(value.strip())}
            elif key == "ExecMainStatus":
                result[key] = int(value) if value.isdecimal() else "unknown"
            elif value in (
                "yes", "no", "true", "false", "full", "strict", "active",
                "failed", "inactive", "activating", "running", "dead",
                "success", "exit-code", "start", "private",
            ):
                result[key] = value
        return result
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "not_readable"}


def report(path=DB):
    return {
        "mode": "EPISCENE_SQLITE_WAL_READ_ONLY_DIAGNOSTIC",
        "host_database_read_probe": sqlite_probe(path),
        "sqlite_file_metadata": {
            "parent_directory": details(path.parent),
            "main": details(path),
            "wal": details(Path(str(path) + "-wal")),
            "shm": details(Path(str(path) + "-shm")),
        },
        "sync_service_sandbox": service_properties(),
        "no_production_mutations": True,
        "no_service_restarts": True,
        "sensitive_database_rows_exported": 0,
    }


if __name__ == "__main__":
    print(json.dumps(report(), ensure_ascii=False, indent=2, sort_keys=True))
