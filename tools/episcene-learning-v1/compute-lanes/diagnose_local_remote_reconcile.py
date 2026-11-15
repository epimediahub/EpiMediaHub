#!/usr/bin/env python3
"""Read-only exact local EpiScene remote-component & bind diagnosis.

Reports ONLY booleans, safe unit names and counts. It never prints any
source contents, full paths, hashes, credentials, provider URLs or env values.
Connects solely to local 127.0.0.1:8790 GET /health. No worker restarts.
"""
from __future__ import annotations
import hashlib
import importlib
import io
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

PROV=Path("/opt/epimediahub/provisioning")
ANAL=Path("/opt/epimediahub/analysis")
VENV=Path("/opt/epimediahub/provisioning/.venv")
PORT=8790

def call(args,timeout=5):
    try:
        r=subprocess.run(args,check=False,timeout=timeout,text=True,capture_output=True)
        return r.stdout if r.returncode==0 else ""
    except (OSError,subprocess.TimeoutExpired):
        return ""

def digest_match(path,value):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>2_000_000:
            return {"exists":False}
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        return {"exists":True,
                "matches_reported_version":bool(isinstance(value,str) and
                       len(value)>=12 and (actual==value or
                       actual.startswith(value.lower())))}
    except (OSError,ValueError):
        return {"exists":False}

def local_health():
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8790/health",timeout=4
        ) as response:
            if response.status!=200:
                return {"state":"HTTP_UNEXPECTED_STATUS"}
            raw=response.read(65537)
            if len(raw)>65536:return {"state":"REPLY_TOO_LARGE"}
        data=json.loads(raw.decode("utf-8"))
        if not isinstance(data,dict):return {"state":"UNEXPECTED_HEALTH_STRUCTURE"}
        active=data.get("active_count")
        return {
            "state":"OK" if data.get("status")=="ok" else "NOT_HEALTHY",
            "protocol":data.get("protocol"),
            "reported_versions":data.get("versions") if isinstance(data.get("versions"),dict) else {},
            "tasks_active":bool(data.get("active")),
            "active_count":active if type(active)==int and 0<=active<=2 else None,
        }
    except Exception:
        return {"state":"UNAVAILABLE"}

def listener():
    output=call(["ss","-H","-lntp","sport = :8790"])
    entries=output.splitlines()
    all_pids={int(x) for x in re.findall(r"pid=(\d+)",output) if x.isdecimal()}
    units=set()
    for pid in list(all_pids)[:6]:
        try:
            cgroup=(Path("/proc")/str(pid)/"cgroup").read_text("utf-8")
        except (OSError,UnicodeError):
            continue
        found=re.findall(r"([a-zA-Z0-9_@.-]+\.service)",cgroup)
        units.update(x for x in found if len(x)<100)
    return {
        "listener_present":bool(entries),
        "listener_on_loopback":any("127.0.0.1:8790" in x for x in entries),
        "listener_on_all_ipv4":any("0.0.0.0:8790" in x or "*:8790" in x for x in entries),
        "worker_process_count":len(all_pids),
        "systemd_service_names":sorted(units),
    }

def configured_address_assigned(host):
    # Only report whether the *expected* private IP is assigned locally.
    # No interface/IP inventory is exported.
    if not isinstance(host,str):
        return False
    try: expected=ipaddress.ip_address(host)
    except ValueError:return False
    data=call(["ip","-o","-4","addr","show"])
    return bool(re.search(r"(?<![\d.])"+re.escape(str(expected))+r"/\d+",data))

def diagnostic():
    if PROV.is_symlink() or not PROV.is_dir():
        return {"status":"STOP_PROVISIONING_PATH_UNAVAILABLE"}
    sys.path.insert(0,str(PROV))
    try:
        with io.StringIO() as sink:
            from contextlib import redirect_stdout,redirect_stderr
            with redirect_stdout(sink),redirect_stderr(sink):
                p=importlib.import_module("skip_remote_protocol")
                local=p.versions()
                worker_ip=p.SERVER_IP
                expected_port=p.PORT
    except Exception:
        return {"status":"STOP_PROTOCOL_READ_FAILURE"}
    health=local_health()
    remote=health.get("reported_versions") or {}
    component="skip_analysis.py"
    local_version=local.get(component)
    remote_version=remote.get(component)
    matches={name:digest_match(folder/component,expected) for name,folder,expected in (
       ("api_file_compared_to_current",PROV,local_version),
       ("worker_tree_file_compared_to_current",ANAL,local_version),
       ("api_file_compared_to_running_remote",PROV,remote_version),
       ("worker_tree_file_compared_to_running_remote",ANAL,remote_version),
    )}
    differing=[str(k) for k in set(local)|set(remote)
               if local.get(k)!=remote.get(k)
               and isinstance(k,str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,60}",k)]
    return {
        "mode":"EPISCENE_LOCAL_WORKER_RECONCILIATION_READ_ONLY",
        "health_state":health.get("state"),
        "reported_worker_active_count":health.get("active_count"),
        "worker_has_active_task":health.get("tasks_active"),
        "client_worker_protocol_match":health.get("protocol")==getattr(p,"PROTOCOL",None),
        "configured_port_matches_local_listener":expected_port==PORT,
        "configured_remote_target_assigned_to_this_host":configured_address_assigned(worker_ip),
        "configured_target_is_loopback":worker_ip=="127.0.0.1",
        "local_and_live_version_component_counts":[len(local),len(remote)],
        "all_version_component_names_equal":set(local)==set(remote),
        "different_component_names":sorted(differing),
        "file_provenance":matches,
        "socket":listener(),
        "safe_to_restart_worker_based_on_this_report_alone":False,
        "note":"Module hash and bind alone do not certify a safe restart. Do not patch provisioning/customer marker API.",
        "database_writes":0,"provider_connections":0,"restarts":0,
        "raw_logs_or_identifiers_exported":False
    }

if __name__=="__main__":
    print(json.dumps(diagnostic(),indent=2,sort_keys=True))
