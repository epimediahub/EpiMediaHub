#!/usr/bin/env python3
"""Read-only EpiScene Raspberry/Hetzner preflight.

Does not stop/start services, change the database, disclose playlist credentials
or use the provider streams. Run on each node before coordinated recovery.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import urllib.error
import urllib.request

CONTROLLER = Path("/opt/epimediahub/provisioning")
WORKER = Path("/opt/epimediahub/analysis")
SERVICES = (
    "epimediahub-provisioning.service",
    "epimediahub-analysis-worker.service",
    "epimediahub-skip-analysis.timer",
    "epimediahub-skip-analysis.service",
    "epimediahub-skip-progress.timer",
    "epimediahub-episcene-report.timer",
    "epimediahub-episcene-report.service",
)
DEFAULT_COMPONENTS = (
    "skip_analysis.py", "skip_automation.py", "skip_detector_v2.py",
    "skip_detector_v3.py", "skip_remote_client.py", "skip_remote_protocol.py",
    "skip_visual.py", "skip_scene.py", "skip_release.py",
)

def systemd_status(unit: str) -> str:
    try:
        p = subprocess.run(
            ["systemctl", "is-active", unit], capture_output=True,
            text=True, timeout=5, check=False
        )
        return (p.stdout.strip() or p.stderr.strip() or "unknown").splitlines()[0][:100]
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"

def components(base: Path) -> tuple[str, ...]:
    protocol = base / "skip_remote_protocol.py"
    if protocol.exists():
        try:
            tree = ast.parse(protocol.read_text())
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    if any(isinstance(x, ast.Name) and x.id == "COMPONENTS"
                           for x in node.targets):
                        names = ast.literal_eval(node.value)
                        if isinstance(names, (tuple, list)) and all(
                            isinstance(x, str) and re.fullmatch(r"[a-z0-9_]+\.py", x)
                            for x in names
                        ):
                            return tuple(names)
        except (OSError, ValueError, SyntaxError):
            pass
    return DEFAULT_COMPONENTS

def local_versions(base: Path, names: tuple[str, ...]) -> dict:
    return {
        name: hashlib.sha256((base / name).read_bytes()).hexdigest()
        if (base / name).is_file() else "MISSING"
        for name in names
    }

def remote_health(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=4) as response:
            result = json.loads(response.read(300_000))
        if not isinstance(result, dict):
            raise ValueError("invalid JSON")
        return result
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return {"error": type(exc).__name__ + ": " + str(exc)[:100]}

def table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None

def db_status() -> dict:
    candidates = (
        Path("/var/lib/epimediahub/provisioning.db"),
        Path("/opt/epimediahub/provisioning/data/provisioning.db"),
    )
    try:
        path = next(p for p in candidates if p.is_file())
    except StopIteration:
        return {"status": "database not found at standard paths; not modified"}
    con = None
    try:
        con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
        con.execute("PRAGMA query_only=ON")
        result = {"status": "read-only OK", "path": str(path)}
        if table_exists(con, "skip_jobs"):
            result["jobs"] = dict(con.execute(
                "SELECT status,COUNT(*) FROM skip_jobs GROUP BY status"
            ).fetchall())
            result["last_jobs"] = [
                {"id": id, "status": status, "updated_at": updated}
                for id, status, updated in con.execute(
                    "SELECT id,status,updated_at FROM skip_jobs "
                    "ORDER BY updated_at DESC LIMIT 5"
                ).fetchall()
            ]
        tables = [
            str(r[0]) for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND (lower(name) LIKE '%analysis%' OR lower(name) LIKE '%line%' "
                "OR lower(name) LIKE '%source%')"
            )
        ]
        candidate_fields = {}
        for table in tables[:45]:
            quoted = table.replace('"','""')
            cols = [
                str(x[1]) for x in con.execute(f'PRAGMA table_info("{quoted}")')
                if re.search(r"expire|expiry|valid|renew|forecast|auto|duration|date", str(x[1]), re.I)
            ]
            if cols:
                candidate_fields[table] = cols
        result["analysis_expiry_related_columns"] = candidate_fields
        return result
    except (sqlite3.Error, OSError) as exc:
        return {"error": type(exc).__name__ + ": " + str(exc)[:150]}
    finally:
        if con:
            con.close()

def relevant_files(base: Path) -> list[str]:
    found = []
    for folder in (base / "templates", base):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.html" if folder.name == "templates" else "*.py")):
            if path.stat().st_size > 1_000_000:
                continue
            try:
                data = path.read_text(errors="replace")
            except OSError:
                continue
            if re.search(r"analys(e|is)|EpiScene", data, re.I) and re.search(
                r"ablauf|expiry|expires|expired|prognos|forecast|renew|valid_until",
                data, re.I
            ):
                found.append(path.name)
    return sorted(set(found))[:30]

def main() -> None:
    print("=== EPISCENE READ-ONLY DIAGNOSIS ===")
    print("hostname:", socket.gethostname())
    print("services:", json.dumps({unit: systemd_status(unit) for unit in SERVICES}, ensure_ascii=False))
    for base, label in ((CONTROLLER, "controller"), (WORKER, "worker")):
        if not (base / "skip_remote_protocol.py").is_file():
            continue
        names = components(base)
        hashes = local_versions(base, names)
        print(label + ":", str(base))
        print(label + "_component_hashes:", json.dumps(hashes, sort_keys=True))
        if label == "controller":
            remote = remote_health("http://10.87.26.1:8790/health")
            versions = remote.get("versions", {})
            print("remote_health:", json.dumps({
                "status": remote.get("status"),
                "error": remote.get("error"),
                "protocol": remote.get("protocol"),
                "active": remote.get("active"),
                "episcene_policy": (remote.get("episcene") or {}).get("policy")
                    if isinstance(remote.get("episcene"), dict) else None,
            }, ensure_ascii=False))
            if isinstance(versions, dict) and versions:
                mismatches = sorted(name for name in set(hashes) | set(versions)
                                    if hashes.get(name) != versions.get(name))
                print("mismatching_modules:", json.dumps(mismatches))
            elif "error" not in remote:
                print("mismatching_modules: unavailable (no versions in health)")
            print("analysis_expiry_related_files:", json.dumps(relevant_files(base)))
    print("database:", json.dumps(db_status(), ensure_ascii=False))
    print("=== END; NO CHANGES MADE ===")

if __name__ == "__main__":
    main()
