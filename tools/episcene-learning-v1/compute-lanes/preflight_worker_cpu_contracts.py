#!/usr/bin/env python3
"""EpiScene FINAL read-only worker/scheduler contract + CPU headroom preflight.

Never executes/imports installed worker code. Reads only allowlisted Python
module AST, selected service states, host capacity and aggregate job statuses.
Outputs no file content, source URLs, credentials, job IDs or customer rows.

This is NOT a compatibility certificate, deploy or performance benchmark.
"""
from __future__ import annotations
import ast
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
from typing import Any

ROOT=Path("/opt/epimediahub/provisioning")
REMOTE=Path("/opt/epimediahub/analysis")
DB=Path("/var/lib/epimediahub/provisioning.db")
WORKERS={
    "analysis_worker":ROOT/"skip_analysis_worker.py",
    "scheduler":ROOT/"skip_schedule.py",
    "scene":ROOT/"skip_scene.py",
    "scene_reliability":ROOT/"skip_scene_reliability.py",
    "release":ROOT/"skip_release.py",
    "automation":ROOT/"skip_automation.py",
    "remote_worker":REMOTE/"skip_remote_worker.py",
}
# Hash prefixes observed in the user's 2026-10-23 21:19Z inventory.
# Only flag drift; DO NOT treat a match as proof of compatibility.
OBSERVED_SHA16={
    "analysis_worker":"e062daaedce41501",
    "scheduler":"5dfbcad78c666a7a",
    "scene":"6b83cf39dc825b6b",
    "scene_reliability":"65350baf4bf160aa",
    "release":"6ffde912fad22255",
    "automation":"7dc0681ae329c1ae",
    "remote_worker":"0fbc8d2457593eee",
}
# Previously reviewed AST function digests. A differing digest must be
# reviewed against the installed code before enabling scheduler hooks.
FUNCTION_SHAPES={
    "scheduler":{"select_job":{"66ccd47b3f270d61"}},
    "scene":{"capture":{"1d717bc5fd36ccdb"},"analyze":{"999539f90f059311"}},
    "scene_reliability":{"analyze":{"9256681315517a3e","ac797952bcf1234f"}},
}
SERVICES=(
    "epimediahub-analysis-worker.service",
    "epimediahub-provisioning.service",
    "episcene-unified-sync.timer",
    "episcene-safe-release-learning.timer",
)
ALLOWED_STATES=frozenset(("active","inactive","failed","activating","deactivating"))


def file_contract(path, baseline=None, targets=None):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>2_000_000:
            return {"state":"unavailable"}
        src=path.read_bytes()
        tree=ast.parse(src.decode("utf-8"))
        hash16=hashlib.sha256(src).hexdigest()[:16]
        result={
            "state":"present",
            "baseline_sha16_match":hash16==baseline if baseline else None,
            "digest_sha16":hash16,
        }
        if targets:
            found={}
            for n in ast.walk(tree):
                if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in targets:
                    found.setdefault(n.name,[]).append(hashlib.sha256(
                        ast.dump(n,include_attributes=False).encode("utf-8")
                    ).hexdigest()[:16])
            shapes={name:(set(found.get(name,[]))==expected) for name,expected in targets.items()}
            result["contract_function_shapes_match"]=shapes
            result["known_function_contracts_match"]=all(shapes.values())
        else:
            result["known_function_contracts_match"]=None
        return result
    except (OSError,SyntaxError,UnicodeError):
        return {"state":"unavailable"}


def service_status(name,run=subprocess.run):
    try:
        r=run(["systemctl","is-active",name],capture_output=True,text=True,
              timeout=5,check=False)
        val=r.stdout.strip()
        return val if val in ALLOWED_STATES else "unknown"
    except (OSError,subprocess.TimeoutExpired):
        return "unknown"


def job_counts(database=DB):
    if database.is_symlink() or not database.is_file():
        return {"state":"unavailable"}
    try:
        with sqlite3.connect(database.resolve().as_uri()+"?mode=ro",
                             uri=True,timeout=7) as db:
            db.execute("PRAGMA query_only=ON")
            q={row[1] for row in db.execute("PRAGMA table_info(skip_jobs)")}
            a={row[1] for row in db.execute("PRAGMA table_info(skip_assets)")}
            if not {"asset_key","status"}<=q or not {"asset_key","playlist_id"}<=a:
                return {"state":"schema_unavailable"}
            out={"8":{},"10":{}}
            allowed={"queued","running","done","failed","partial","review",
                     "no_match","no_reference","disabled","archived"}
            for pid,status,count in db.execute("""
                SELECT a.playlist_id,j.status,COUNT(*)
                FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
                WHERE a.playlist_id IN (8,10)
                GROUP BY 1,2
            """):
                key=status if status in allowed else "other"
                d=out[str(pid)]
                d[key]=d.get(key,0)+int(count)
            return {"state":"ok","playlist_job_status_totals":out}
    except (sqlite3.Error,OSError,ValueError):
        return {"state":"unavailable"}


def host_resources():
    cpus=os.cpu_count() or 1
    avail_kb=0
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                avail_kb=int(line.split()[1])
                break
    except (OSError,UnicodeError,ValueError,IndexError):
        pass
    try:
        load=os.getloadavg()[0]
    except OSError:
        load=None
    return {
        "cpu_cores":cpus,
        "one_minute_load_per_core":round(load/cpus,2) if load is not None else None,
        "memory_available_gib":round(avail_kb/1048576,2),
        # A one-minute host load average is NOT measured EpiScene CPU
        # utilization. Do not infer safe additional workers from it alone.
        "measured_analysis_cpu_utilization":None,
        "additional_offline_workers_safe_to_activate_without_benchmark":0,
        "analysis_provider_stream_caps":{"8":1,"10":1},
    }


def collect(files=WORKERS,services=SERVICES,database=DB):
    contracts={
        role:file_contract(path,OBSERVED_SHA16.get(role),FUNCTION_SHAPES.get(role))
        for role,path in files.items()
    }
    service_states={unit:service_status(unit) for unit in services}
    verified=[k for k,v in contracts.items() if v.get("known_function_contracts_match") is True]
    changed=[k for k,v in contracts.items()
             if v.get("known_function_contracts_match") is False or
             v.get("baseline_sha16_match") is False]
    return {
        "mode":"EPISCENE_WORKER_CONTRACT_AND_CAPACITY_READ_ONLY",
        "installed_module_contracts":contracts,
        "known_exact_contract_roles_passed":verified,
        "contract_or_baseline_changes_needing_review":changed,
        "service_states":service_states,
        "analysis_job_counts":job_counts(database),
        "host_capacity":host_resources(),
        "safe_to_enable_new_scheduler_hooks":False,
        "reason":"Deployed API wiring and rollback must be integration-tested first",
        "new_provider_connections":0,
        "worker_restarts":0,
        "database_writes":0,
        "source_or_customer_data_exported":False,
    }


if __name__=="__main__":
    print(json.dumps(collect(),sort_keys=True,indent=2))
