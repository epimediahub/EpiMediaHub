#!/usr/bin/env python3
"""Fail-closed, read-only EpiScene deployed-worker integrity and version gate.

An approved manifest must pin each deployed component's FULL SHA-256 digest.
Components have different release versions: compatibility is established by a
reviewed manifest + integration tests, not by equating version strings.
This tool neither restarts systemd services nor touches the production DB.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

PROVISIONING = Path("/opt/epimediahub/provisioning")
REMOTE = Path("/opt/epimediahub/analysis")
ALLOWED = (PROVISIONING, REMOTE, Path("/opt/episcene-learning"))
CORE = frozenset(("analysis_worker", "scheduler", "scene", "release"))
RECOMMENDED = {
    "analysis_worker": PROVISIONING / "skip_analysis_worker.py",
    "scheduler": PROVISIONING / "skip_schedule.py",
    "scene": PROVISIONING / "skip_scene.py",
    "release": PROVISIONING / "skip_release.py",
    "automation": PROVISIONING / "skip_automation.py",
    "reliability": PROVISIONING / "skip_scene_reliability.py",
    "remote_worker": REMOTE / "skip_remote_worker.py",
}
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_BYTES = 2_000_000


def fingerprint(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing_or_symlink")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("unexpected_size")
    raw = path.read_bytes()
    try:
        tree = ast.parse(raw.decode("utf-8"))
    except (UnicodeError, SyntaxError) as exc:
        raise ValueError("invalid_python") from exc
    count = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                for n in ast.walk(tree))
    return {"sha256": hashlib.sha256(raw).hexdigest(), "functions": count}


def inventory(paths=None):
    paths = paths or RECOMMENDED
    items = {}
    for role, path in paths.items():
        try:
            data = fingerprint(path)
            items[role] = {"status": "present", "sha256_prefix": data["sha256"][:16],
                           "functions": data["functions"]}
        except (OSError, ValueError) as exc:
            items[role] = {"status": str(exc)}
    return {"mode": "READ_ONLY_VERSION_INVENTORY",
            "components": items, "compatible": False,
            "note": "Inventory alone never proves compatibility"}


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise ValueError("manifest_schema")
    components = manifest.get("components")
    if not isinstance(components, dict) or not CORE <= set(components):
        raise ValueError("missing_core_components")
    if not isinstance(manifest.get("integration_test_run"), str) or not manifest["integration_test_run"].strip():
        raise ValueError("missing_test_provenance")
    for role, value in components.items():
        if not isinstance(role, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", role):
            raise ValueError("invalid_role")
        if not isinstance(value, dict) or not HEX_SHA256.fullmatch(str(value.get("sha256", ""))):
            raise ValueError("invalid_expected_digest")
        p = Path(value.get("path", ""))
        if (not p.is_absolute() or ".." in p.parts or
                not any(p == allowed or allowed in p.parents for allowed in ALLOWED)):
            raise ValueError("unexpected_component_path")
    services = manifest.get("services")
    if not isinstance(services, list) or not services:
        raise ValueError("missing_service_contract")
    for item in services:
        if not isinstance(item, str) or not re.fullmatch(r"[a-zA-Z0-9@_.-]+\.service", item):
            raise ValueError("invalid_service")
    return True


def service_state(name, executor=subprocess.run):
    try:
        r = executor(["systemctl", "is-active", "--", name],
                     capture_output=True, text=True, timeout=5, check=False)
        state = (r.stdout or "").strip()
        return state if state in {"active", "inactive", "failed", "activating"} else "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def verify(manifest, *, executor=subprocess.run):
    validate_manifest(manifest)
    components = {}
    good = True
    for role, value in sorted(manifest["components"].items()):
        try:
            actual = fingerprint(value["path"])
            match = actual["sha256"] == value["sha256"]
            components[role] = {
                "status": "match" if match else "DRIFT",
                "sha256_prefix": actual["sha256"][:16],
                "functions": actual["functions"]}
            good &= match
        except (OSError, ValueError) as exc:
            good = False
            components[role] = {"status": str(exc)}
    services = {name: service_state(name, executor) for name in manifest["services"]}
    good &= all(state == "active" for state in services.values())
    return {
        "mode": "READ_ONLY_WORKER_COHERENCE_GATE",
        "all_components_match_manifest": all(
            x.get("status") == "match" for x in components.values()),
        "all_required_services_active": all(v == "active" for v in services.values()),
        "compatible_for_considered_rollout": bool(good),
        "integrity_only_not_end_to_end_proof": True,
        "components": components, "services": services,
        "no_restart": True, "production_writes": 0, "provider_requests": 0,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path)
    a = p.parse_args()
    if not a.manifest:
        result = inventory()
    else:
        if a.manifest.is_symlink() or not a.manifest.is_file():
            raise SystemExit("Manifest unavailable")
        result = verify(json.loads(a.manifest.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if a.manifest and not result["compatible_for_considered_rollout"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
