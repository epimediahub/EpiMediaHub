#!/usr/bin/env python3
"""Guarded AST patch of EXISTING EpiScene Flask device lookup.

Never adds a new route. Strictly matches the live function signature gathered
from the Hetzner redacted read-only audit, and inserts one safe cache-read
inside its authenticated successful-return path. Can stage/check without
writing production. Applies with atomic backups and automatic rollback on
an unsuccessful systemd restart. No client secrets or source code output.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path("/opt/epimediahub/provisioning/skip_markers.py")
DEST = Path("/opt/episcene-learning/unified/production_lookup_cache.py")
DATA = Path("/var/lib/episcene-learning")
UNIT = "epimediahub-provisioning.service"
LIVE_HANDLER_SHA = "b76093afb2f7b452"
ROUTE = "/v1/device/skip/lookup"
FUNCTION = "v082_skip_lookup"
MAX_FILE_BYTES = 2_000_000
INJECTION_LABEL = "_EPI_TRUSTED_EXTERNAL_LOOKUP_V1"

INSERTION = [
    "try:",
    "    from sys import path as _epi_path",
    "    if '/opt/episcene-learning/unified' not in _epi_path:",
    "        _epi_path.insert(0, '/opt/episcene-learning/unified')",
    "    from production_lookup_cache import augment_authorized_segments as _epi_augment",
    "    segments = _epi_augment(",
    "        segments, descriptor=data,",
    "        persisted_identity=(dict(identity) if identity is not None else None))",
    "    " + INJECTION_LABEL + " = True",
    "except Exception:",
    "    pass",
]


def _function(source):
    tree = ast.parse(source)
    match = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != FUNCTION:
            continue
        if any(isinstance(dec, ast.Call) and dec.args and
               isinstance(dec.args[0], ast.Constant) and
               dec.args[0].value == ROUTE for dec in node.decorator_list):
            match.append(node)
    if len(match) != 1:
        raise ValueError("STOP: expected exactly one decorated live lookup")
    return match[0]


def patch_source(source, *, expected_hash=LIVE_HANDLER_SHA):
    if INJECTION_LABEL in source:
        raise ValueError("STOP: existing trusted external patch requires manual review")
    fn = _function(source)
    sha = hashlib.sha256(ast.dump(fn, include_attributes=False).encode()).hexdigest()[:16]
    if sha != expected_hash:
        raise ValueError("STOP: active lookup differs from reviewed version")
    result_calls = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Name) or call.func.id != "jsonify":
            continue
        kws = {kw.arg: kw.value for kw in call.keywords}
        if not isinstance(kws.get("segments"), ast.Name):
            continue
        if kws["segments"].id != "segments":
            continue
        if not {"asset_key","source_key","duration_ms"} <= set(kws):
            continue
        result_calls.append(node)
    if len(result_calls) != 1:
        raise ValueError("STOP: expected exactly one successful segments response")
    insertion = result_calls[0]
    lines = source.splitlines(keepends=True)
    index = insertion.lineno - 1
    if not (0 <= index < len(lines)):
        raise ValueError("STOP: invalid return position")
    prefix = lines[index][:len(lines[index])-len(lines[index].lstrip())]
    if not prefix or "\t" in prefix:
        raise ValueError("STOP: unexpected lookup indentation")
    new_lines = [prefix + item + "\n" for item in INSERTION]
    patched = "".join(lines[:index] + new_lines + lines[index:])
    compile(patched, "<EpiScene-reviewed-patched-lookup>", "exec")
    # Existing imports, decorators and successful response payload remain the
    # same. No other function body is touched beyond this insertion.
    return patched


def _run(*args):
    return subprocess.run(list(args), capture_output=True, text=True,
                          timeout=22, check=False)


def _regular(path):
    p = Path(path)
    return p.is_file() and not p.is_symlink() and stat.S_ISREG(p.lstat().st_mode)


def preflight(source=SOURCE, data=DATA):
    if not _regular(source) or source.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("STOP: unknown active Flask source")
    if not _regular(data / "trusted-sources.sqlite3"):
        raise ValueError("STOP: no trusted external marker cache")
    if data.is_symlink() or not data.is_dir():
        raise ValueError("STOP: EpiScene private store missing")
    if stat.S_IMODE(data.stat().st_mode) & 0o077:
        raise ValueError("STOP: EpiScene private store is not private")
    if not (_run("systemctl", "is-active", "--quiet", UNIT).returncode == 0):
        raise ValueError("STOP: production API not running")
    if not (_run("systemctl", "is-active", "--quiet",
                 "episcene-trusted-sources.timer").returncode == 0):
        raise ValueError("STOP: trusted source refresh not running")
    service_user = _run("systemctl", "show", "-p", "User", "--value", UNIT)
    if service_user.returncode != 0:
        raise ValueError("STOP: cannot determine service identity")
    user = service_user.stdout.strip()
    if user not in ("", "root"):
        import re
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,63}", user):
            raise ValueError("STOP: unexpected API service account")
        # Permission-probe the actual cache as the actual systemd account.
        # Never make the entire knowledge directory world-readable.
        probe = (
            "import sqlite3;"
            "from pathlib import Path;"
            "p=Path('/var/lib/episcene-learning/trusted-sources.sqlite3');"
            "c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=3);"
            "c.execute('PRAGMA query_only=ON');"
            "c.execute('SELECT COUNT(*) FROM trusted_external_cache').fetchone();"
            "c.close()"
        )
        if _run("runuser", "-u", user, "--", "python3", "-c", probe).returncode != 0:
            raise ValueError(
                "STOP: API account still cannot read trusted cache; "
                "grant read-only account ACL before proceeding"
            )
    return {"api_service_active": True, "cache_access": "least_privilege_read_verified"}


def apply(source, patch, dependency_path, *, expected_original_sha, unit=UNIT):
    """Install exact reviewed source and dependency with rollback if needed."""
    if os.geteuid() != 0:
        raise ValueError("STOP: root required")
    original = source.read_bytes()
    if hashlib.sha256(original).hexdigest() != expected_original_sha:
        raise ValueError("STOP: live source changed after review; no modifications")
    if DEST.exists() or DEST.is_symlink():
        raise ValueError("STOP: trusted lookup module already installed")
    mode = stat.S_IMODE(source.stat().st_mode)
    stat_info = source.stat()
    stash = DATA / "live-lookup-backups"
    stash.mkdir(mode=0o700, exist_ok=True)
    if stash.is_symlink():
        raise ValueError("STOP: backup directory is a symlink")
    os.chmod(stash, 0o700)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = stash / ("skip_markers-" + suffix + ".py.bak")
    if backup.exists():
        raise ValueError("STOP: backup name already used")
    backup.write_bytes(original)
    os.chmod(backup, 0o600)
    if not _regular(dependency_path):
        raise ValueError("STOP: lookup bridge source unavailable")
    installed_new = False
    modified_original = False
    try:
        shutil.copyfile(dependency_path, DEST)
        os.chmod(DEST, 0o644)
        os.chown(DEST, 0, 0)
        installed_new = True
        tmp = source.with_name("." + source.name + ".episcene.new")
        if tmp.exists() or tmp.is_symlink():
            raise ValueError("STOP: destination staging file already exists")
        try:
            with open(tmp, "xb") as fh:
                fh.write(patch.encode("utf-8"))
            os.chmod(tmp, mode)
            os.chown(tmp, stat_info.st_uid, stat_info.st_gid)
            if hashlib.sha256(source.read_bytes()).hexdigest() != expected_original_sha:
                raise ValueError("STOP: live source changed during installation")
            os.replace(tmp, source)
            modified_original = True
        finally:
            if tmp.exists():
                tmp.unlink()
        if _run("systemctl", "restart", unit).returncode != 0:
            raise RuntimeError("STOP: API restart rejected; rollback")
        if _run("systemctl", "is-active", "--quiet", unit).returncode != 0:
            raise RuntimeError("STOP: API failed health check; rollback")
    except Exception:
        if modified_original:
            rollback = source.with_name("." + source.name + ".episcene.rollback")
            with open(rollback, "wb") as fh:
                fh.write(original)
            os.chmod(rollback, mode)
            os.chown(rollback, stat_info.st_uid, stat_info.st_gid)
            os.replace(rollback, source)
            _run("systemctl", "restart", unit)
        if installed_new and DEST.exists():
            DEST.unlink()
        raise
    return backup


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["check", "apply"])
    p.add_argument("--dependency", required=True)
    args = p.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("STOP: run as root on the analysis server")
    preflight()
    original_bytes = SOURCE.read_bytes()
    source = original_bytes.decode("utf-8")
    patched = patch_source(source)
    dependency = Path(args.dependency)
    if not _regular(dependency):
        raise SystemExit("STOP: no reviewed lookup adapter")
    compile(dependency.read_text(encoding="utf-8"),
            "<EpiScene-reviewed-cache-adapter>", "exec")
    print("ACTIVE_LOOKUP_SHAPE_OK")
    print("STATIC_GUARD_OK: original device auth and rate-limit code not rewritten")
    print("NO_CUSTOMER_PLAYLIST_OR_MARKER_DATABASE_CHANGES")
    if args.mode == "check":
        print("CHECK_OK_NO_PRODUCTION_CHANGES")
        return
    saved = apply(SOURCE, patched, dependency,
                  expected_original_sha=hashlib.sha256(original_bytes).hexdigest())
    print("LIVE_DEVICE_LOOKUP_PATCH_INSTALLED")
    print("ROLLBACK_BACKUP_CREATED_IN_PRIVATE_STORE")
    print("API_RESTART_SUCCESSFUL_DEVICE_PLAYBACK_NOT_YET_VERIFIED")
    print("EXTERNAL_CACHE_ACCEPTANCE_REQUIRES_REAL_DEVICE_TEST")


if __name__ == "__main__":
    main()
