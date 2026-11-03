#!/usr/bin/env python3
"""EpiScene READ-ONLY source provenance and service compatibility preflight.

This does NOT calculate a trusted manifest from whatever happens to be live.
It compares live installed sources to two known source snapshots and provides
only sanitized compatibility evidence to support a reviewed, future rollout.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

LIVE = Path("/opt/episcene-learning/safe_release_rollout_v2.py")
SERVICE = "episcene-safe-release-learning.service"
TIMER = "episcene-safe-release-learning.timer"
RUNNER = "epimediahub-skip-analysis.service"
REMOTE = "epimediahub-analysis-worker.service"
MODULES = {
    "skip_analysis_worker.py":Path("/opt/epimediahub/provisioning/skip_analysis_worker.py"),
    "skip_schedule.py":Path("/opt/epimediahub/provisioning/skip_schedule.py"),
    "skip_scene.py":Path("/opt/epimediahub/provisioning/skip_scene.py"),
    "skip_release.py":Path("/opt/epimediahub/provisioning/skip_release.py"),
    "skip_remote_worker.py":Path("/opt/epimediahub/analysis/skip_remote_worker.py"),
}

def source(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size>2_000_000:
        return None
    data=p.read_bytes()
    try:
        tree=ast.parse(data.decode("utf-8"))
    except (SyntaxError,UnicodeError):
        return None
    return {
        "sha256":hashlib.sha256(data).hexdigest(),
        "functions":sorted({n.name for n in ast.walk(tree)
                            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}),
    }


def systemd(unit, field):
    try:
        p=subprocess.run(["systemctl","show",unit,"-p",field,"--value"],
                         capture_output=True,text=True,timeout=5,check=False)
        return p.stdout.strip() if p.returncode==0 else ""
    except (OSError,subprocess.TimeoutExpired):
        return ""


def run(baseline, candidate):
    old=source(baseline);new=source(candidate);installed=source(LIVE)
    if not old or not new:
        raise ValueError("reviewed_source_files_unavailable")
    if not installed:
        return {"mode":"EPISCENE_SAFE_RELEASE_COMPAT_READ_ONLY",
                "live_controller":"UNAVAILABLE",
                "deployment_allowed":False,"writes":0,
                "no_service_restarted":True}
    current=installed["sha256"]
    expected=old["sha256"];nextver=new["sha256"]
    matches_old=current==expected
    matches_new=current==nextver
    current_functions=set(installed["functions"])
    expected_functions=set(old["functions"])
    changed_functions=sorted(current_functions.symmetric_difference(expected_functions))
    service_exec=systemd(SERVICE,"ExecStart")
    checks={
        "service_load_state":systemd(SERVICE,"LoadState"),
        "service_enabled":systemd(SERVICE,"UnitFileState"),
        "service_type":systemd(SERVICE,"Type"),
        "timer_active":systemd(TIMER,"ActiveState")=="active",
        "worker_service_active":systemd(REMOTE,"ActiveState")=="active",
        "analysis_runner_state":systemd(RUNNER,"ActiveState"),
        "release_unit_uses_v2_controller":"safe_release_rollout_v2.py" in service_exec,
    }
    modules={}
    for role,path in MODULES.items():
        item=source(path)
        modules[role]={"status":"present" if item else "unavailable",
                       "sha256_prefix":item["sha256"][:16] if item else None}
    return {
        "mode":"EPISCENE_SAFE_RELEASE_COMPAT_READ_ONLY",
        "installed_controller_sha256":current,
        "reviewed_main_baseline_sha256":expected,
        "candidate_change_sha256":nextver,
        "live_equals_reviewed_main":matches_old,
        "live_equals_candidate":matches_new,
        "live_diverges_from_both":not matches_old and not matches_new,
        "live_function_names_differ_from_main":bool(changed_functions),
        "live_function_name_differences":changed_functions,
        "service_checks":checks,
        "worker_components":modules,
        "deployment_allowed":False,
        "requires_reviewed_manifest_and_full_rollback":True,
        "notes":"Matching hashes verify exact code bytes, not integration compatibility or release eligibility",
        "writes":0,"provider_requests":0,"marker_approvals":0,
        "no_service_restarted":True,"no_secret_values_exported":True,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--baseline",type=Path,required=True)
    ap.add_argument("--candidate",type=Path,required=True)
    a=ap.parse_args()
    try:
        print(json.dumps(run(a.baseline,a.candidate),sort_keys=True,indent=2))
    except (ValueError,OSError) as exc:
        print(json.dumps({"mode":"EPISCENE_SAFE_RELEASE_COMPAT_READ_ONLY",
                          "status":"STOP","reason":str(exc),"writes":0,
                          "deployment_allowed":False},sort_keys=True))
        raise SystemExit(2)
if __name__=="__main__":
    main()
