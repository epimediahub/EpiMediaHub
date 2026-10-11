#!/usr/bin/env python3
"""Report-driven EpiScene optimization for the LIVE Hetzner controller/compute split.

- Controller owns skip_analysis_worker.py: NEVER require it in compute directory.
- Controller AND compute worker own versioned skip_scene.py.
- Preflight before claiming jobs avoids 2600+ deferred attempts during worker failures.
- Increase persisted visual frame cache from 512 to 2048, without changing TTL/budgets.
- No DB modifications, mass queue resets, credentials, or marker rewrites.
- --check never stops services or writes files.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

CONTROLLER = Path("/opt/epimediahub/provisioning")
COMPUTE = Path("/opt/epimediahub/analysis")
TIMER = "epimediahub-skip-analysis.timer"
ANALYSIS = "epimediahub-skip-analysis.service"
COMPUTE_SERVICE = "epimediahub-analysis-worker.service"

# The two scene modules are versioned by the private protocol; the controller
# analysis orchestrator is NOT deployed to the compute worker.
SCENE = [CONTROLLER / "skip_scene.py", COMPUTE / "skip_scene.py"]
ORCHESTRATOR = CONTROLLER / "skip_analysis_worker.py"
TARGETS = SCENE + [ORCHESTRATOR]


def run(*command: str, timeout: int = 180) -> None:
    subprocess.run(command, check=True, timeout=timeout)


def active(unit: str) -> bool:
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", unit], check=False
    ).returncode == 0


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_atomic(path: Path, data: bytes) -> None:
    st = path.stat()
    fd, temp = tempfile.mkstemp(prefix=".episcene-20261011-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, st.st_mode & 0o777)
        os.chown(temp, st.st_uid, st.st_gid)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def patch_scene(text: str) -> str:
    expected = (
        "CACHE_ROWS = 512",
        "CACHE_SECONDS = 21600",
        "JOB_SECONDS = 300",
    )
    for fragment in expected:
        if text.count(fragment) != 1:
            raise ValueError("Unexpected scene code; expected: " + fragment)
    updated = text.replace("CACHE_ROWS = 512", "CACHE_ROWS = 2048", 1)
    ast.parse(updated, filename="skip_scene.py")
    return updated


def patch_orchestrator(text: str) -> str:
    anchor = (
        "    from skip_catalogue import advance as catalogue_advance, daily_limit\n"
    )
    # Exact live source structure verified against GitHub source; this is
    # specifically AFTER the independent app-capture branch, before job claim.
    before = (
        "def process_one(db, *, exclude_job_ids=(), on_claim=None, deadline=None):\n"
        "    from skip_app_capture import process_one as process_capture\n"
        "    if process_capture(db, lambda: deadline is not None and time.monotonic() >= deadline):\n"
        "        return 'app_compared'\n"
    )
    if text.count(before) != 1 or text.count(anchor) != 1:
        raise ValueError("Unexpected controller orchestrator: safe insertion point missing")
    if "episcene_preflight=" in text or "from skip_remote_client import configured as _epi_configured" in text:
        raise ValueError("Preflight already installed: no duplicate patches")
    if text.count("def process_batch(") != 1:
        raise ValueError("Controller batch runner not recognized")
    batch = text.split("def process_batch(", 1)[1]
    if '"queued"):' not in batch:
        raise ValueError("Batch must stop when worker preflight returns queued")

    guard = (
        "    # Check compute-worker status before taking a new analysis job.\n"
        "    # /health validates all versioned component SHA-256 values.\n"
        "    from skip_remote_client import configured as _epi_configured\n"
        "    from skip_remote_client import health as _epi_health\n"
        "    from skip_remote_client import RemoteDeferred as _epi_deferred\n"
        "    if _epi_configured():\n"
        "        try:\n"
        "            _epi_health()\n"
        "        except _epi_deferred as error:\n"
        "            print('episcene_preflight=worker_unreachable_or_version_mismatch', flush=True)\n"
        "            return 'queued'\n"
    )
    updated = text.replace(before + anchor, before + guard + anchor, 1)
    if updated == text:
        raise ValueError("Exact injection point not found")
    ast.parse(updated, filename="skip_analysis_worker.py")
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe report-driven EpiScene upgrade")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true", help="Read-only structural preflight")
    modes.add_argument("--apply", action="store_true", help="Install with backup and rollback")
    args = parser.parse_args()

    if os.geteuid() != 0:
        raise RuntimeError("Run as root on epimediahub-analysis")
    if not all(path.is_file() for path in TARGETS):
        missing = [str(path) for path in TARGETS if not path.is_file()]
        raise RuntimeError("Unknown live topology: missing " + ", ".join(missing))

    original = {path: path.read_bytes() for path in TARGETS}
    if original[SCENE[0]] != original[SCENE[1]]:
        raise RuntimeError("Controller/compute scene files differ; do not overwrite")

    desired_scene = patch_scene(original[SCENE[0]].decode("utf-8")).encode()
    desired_worker = patch_orchestrator(original[ORCHESTRATOR].decode("utf-8")).encode()
    desired = {
        SCENE[0]: desired_scene,
        SCENE[1]: desired_scene,
        ORCHESTRATOR: desired_worker,
    }
    if shutil.disk_usage(COMPUTE).free < 1024**3:
        raise RuntimeError("Less than 1 GiB free on Hetzner; stop safely")

    sys.path.insert(0, str(CONTROLLER))
    from skip_remote_protocol import versions
    from skip_remote_client import configured, health

    if not configured():
        raise RuntimeError("Private compute worker not configured; no changes")
    initial_versions = versions()
    if initial_versions.get("skip_scene.py") != sha256(original[SCENE[0]]):
        raise RuntimeError("Controller protocol reports unexpected scene hash")
    h = health()
    if h.get("status") != "ok" or h.get("versions") != initial_versions:
        raise RuntimeError("Controller/compute worker protocol versions differ")

    print("=== EPISCENE 11.10.2026 ===", flush=True)
    print("Controller: orchestrator + scene module", flush=True)
    print("Compute: scene module only (corrected topology)", flush=True)
    print("Private RPC version check: PASS", flush=True)
    print("6h TTL and 300s image budget stay unchanged", flush=True)
    print("Visual cache cap: 512 -> 2048 entries", flush=True)
    print("Job-claim preflight: added (no DB status resets)", flush=True)
    if args.check:
        print("CHECK OK: no files or services changed", flush=True)
        return 0

    state = {
        TIMER: active(TIMER),
        ANALYSIS: active(ANALYSIS),
        COMPUTE_SERVICE: active(COMPUTE_SERVICE),
    }
    if not state[COMPUTE_SERVICE]:
        raise RuntimeError("Compute service not active; no changes")

    backup_dir = COMPUTE / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="episcene-20261011-", dir=backup_dir))
    for file in TARGETS:
        prefix = "controller-" if file.parent == CONTROLLER else "compute-"
        shutil.copy2(file, backup / (prefix + file.name))
    print("Backup:", backup, flush=True)

    stopped = False
    try:
        run("systemctl", "stop", TIMER)
        # A current analysis may be interrupted; its saved windows/markers persist.
        run("systemctl", "stop", ANALYSIS)
        run("systemctl", "stop", COMPUTE_SERVICE)
        stopped = True

        for path, data in desired.items():
            write_atomic(path, data)
        for path in TARGETS:
            interpreter = path.parent / ".venv/bin/python"
            if not interpreter.is_file():
                raise RuntimeError("Missing venv interpreter: " + str(interpreter))
            run(str(interpreter), "-m", "py_compile", str(path))

        run("systemctl", "start", COMPUTE_SERVICE)
        failure = None
        for attempt in range(15):
            try:
                h = health()
                if h.get("status") == "ok" and h.get("versions") == versions():
                    break
            except Exception as error:
                failure = error
            time.sleep(1)
        else:
            raise RuntimeError("Worker health/version check failed: " + str(failure))

        # Release services only after validation.
        if state[TIMER]:
            run("systemctl", "start", TIMER)
        if state[ANALYSIS]:
            run("systemctl", "start", "--no-block", ANALYSIS)
    except BaseException as exc:
        print("ERROR: rolling back all three modules: " + str(exc), file=sys.stderr, flush=True)
        if stopped:
            for path, data in original.items():
                try:
                    write_atomic(path, data)
                except Exception as error:
                    print("ROLLBACK FAILURE " + str(path) + ": " + str(error), file=sys.stderr)
            subprocess.run(["systemctl", "restart", COMPUTE_SERVICE], check=False)
        if state[TIMER]:
            subprocess.run(["systemctl", "start", TIMER], check=False)
        if state[ANALYSIS]:
            subprocess.run(["systemctl", "start", "--no-block", ANALYSIS], check=False)
        raise

    print("SUCCESS: synchronized modules; worker health OK", flush=True)
    print("Backup:", backup, flush=True)
    print("No database, marker, playlist or account changes", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError, AssertionError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print("STOP: " + str(error), file=sys.stderr)
        sys.exit(1)
