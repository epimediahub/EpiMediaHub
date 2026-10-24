#!/usr/bin/env python3
"""Read-only EpiScene same-host worker launch and endpoint contract inventory.

Never prints raw systemd ExecStart, environment values, source code, hashes,
hostnames, URLs, auth tokens, network peers, or customer metadata. It only
reports whether a safe bounded local repair could be designed.
"""
from __future__ import annotations
import ast
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path("/opt/epimediahub/provisioning")
ANALYSIS = Path("/opt/epimediahub/analysis")
UNIT = "epimediahub-analysis-worker.service"
SAFE_ENV = re.compile(r"(EPI|REMOTE|COMPUTE|WORKER|HOST|SERVER|BIND)",re.I)

def show(field, run=subprocess.run):
    if field not in ("ExecStart","WorkingDirectory","User","Group","EnvironmentFiles","Environment"):
        raise ValueError("INVALID_PROPERTY")
    try:
        p=run(["systemctl","show","--value","-p",field,"--",UNIT],
              capture_output=True,text=True,timeout=5,check=False)
        return p.stdout[:16000].strip() if p.returncode==0 else ""
    except (OSError,subprocess.TimeoutExpired):
        return ""

def flags(command,server_ip,client_ip):
    found={}
    for opt in ("bind","peer","port"):
        # Only allowlisted flags, not full ExecStart or tokens.
        m=re.search(r"(?:^|\s)--"+opt+r"(?:=|\s+)([^\s;}{]+)",command)
        found[opt]=m.group(1) if m else None
    def endpoint(value):
        if value is None:return "argument_not_found"
        if value=="127.0.0.1":return "loopback"
        if value==server_ip:return "configured_worker_ip"
        if value==client_ip:return "configured_client_ip"
        return "other_or_unexpected"
    port=found["port"]
    return {"bind_option":endpoint(found["bind"]),
            "peer_option":endpoint(found["peer"]),
            "port_is_8790":port=="8790" if port is not None else None,
            "has_bind_flag":found["bind"] is not None,
            "has_peer_flag":found["peer"] is not None,
            "script_mentions_skip_remote_worker":"skip_remote_worker" in command,
            "entrypoint_mentions_python":"python" in command.lower()}

def source_summary(path):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>1_000_000:
            return {"state":"unavailable"}
        tree=ast.parse(path.read_text(encoding="utf-8"))
    except (OSError,SyntaxError,UnicodeError):
        return {"state":"unavailable"}
    names=set()
    env_names=set()
    remote_binds=0
    for n in ast.walk(tree):
        if isinstance(n,ast.Name):
            if n.id in ("SERVER_IP","CLIENT_IP","PORT","PROTOCOL"):
                names.add(n.id)
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute):
            if n.func.attr in ("getenv","get") and n.args and isinstance(n.args[0],ast.Constant):
                v=n.args[0].value
                if isinstance(v,str) and len(v)<=80 and re.fullmatch(r"[A-Za-z0-9_]+",v) and SAFE_ENV.search(v):
                    env_names.add(v)
            if n.func.attr in ("bind","listen"):
                remote_binds+=1
    return {"state":"parsed","protocol_constant_references":sorted(names),
            "environment_override_variable_names":sorted(env_names)[:20],
            "bind_or_listen_calls_count":remote_binds}

def run():
    if ROOT.is_symlink() or not ROOT.is_dir():
        return {"mode":"EPISCENE_REMOTE_LAUNCH_PREFLIGHT","status":"ROOT_UNAVAILABLE",
                "writes":0,"restarts":0}
    sys.path.insert(0,str(ROOT))
    try:
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            import skip_remote_protocol as proto
            ip=proto.SERVER_IP
            client=proto.CLIENT_IP
    except Exception:
        return {"mode":"EPISCENE_REMOTE_LAUNCH_PREFLIGHT","status":"PROTOCOL_UNAVAILABLE",
                "writes":0,"restarts":0}
    command=show("ExecStart")
    wd=show("WorkingDirectory")
    return {
        "mode":"EPISCENE_REMOTE_LAUNCH_PREFLIGHT_READ_ONLY",
        "installed_systemd_unit_found":bool(command),
        "unit_launch_flags":flags(command,ip,client),
        "working_directory_is_provisioning":wd==str(ROOT),
        "working_directory_is_worker_tree":wd==str(ANALYSIS),
        "service_has_environmentfile":bool(show("EnvironmentFiles")),
        "client_ast":source_summary(ROOT/"skip_remote_client.py"),
        "worker_ast":source_summary(ANALYSIS/"skip_remote_worker.py"),
        "note":"No decisions about service restarts or updates from this inventory alone",
        "raw_source_or_secrets_exported":False,
        "database_writes":0,"provider_requests":0,"worker_restarts":0,
    }

if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True,indent=2))
