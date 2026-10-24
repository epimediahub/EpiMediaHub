#!/usr/bin/env python3
"""Read-only EpiScene remote-worker preflight: distinguish network vs ABI drift.

Probes only the dedicated compute worker /health endpoint defined by the
already-installed skip_remote_protocol. Does NOT access IPTV providers, decode
video, issue task POSTs, change credentials, modify databases or restart units.

No endpoint IP, URL, secrets, environment strings or raw exceptions exported.
"""
from __future__ import annotations
import contextlib
import http.client
import importlib
import io
import ipaddress
import json
from pathlib import Path
import re
import socket
import subprocess
import sys

PROVISION=Path("/opt/epimediahub/provisioning")
WORKER_MODULE=("skip_remote_client","skip_remote_protocol")
UNITS=("epimediahub-skip-analysis.timer","epimediahub-skip-analysis.service",
       "epimediahub-analysis-worker.service","epimediahub-remote-worker.service",
       "episcene-remote-worker.service")


def service(unit):
    if unit not in UNITS:
        raise ValueError("UNKNOWN_SERVICE")
    try:
        r=subprocess.run(["systemctl","show","--no-pager",unit,
                          "-p","LoadState","-p","ActiveState","-p","SubState"],
                         capture_output=True,text=True,check=False,timeout=5)
    except (subprocess.TimeoutExpired,OSError):
        return {"state":"unavailable"}
    allowed={"loaded","not-found","masked","active","inactive","failed",
             "activating","deactivating","dead","running","waiting","start","exited"}
    result={}
    for line in r.stdout.splitlines():
        if "=" in line:
            key,value=line.split("=",1)
            if key in ("LoadState","ActiveState","SubState"):
                result[key]=value if value in allowed else "other"
    return result or {"state":"unavailable"}


def only_compute_peer(ip):
    try:
        address=ipaddress.ip_address(ip)
        cgnat=ipaddress.ip_network("100.64.0.0/10")
        return bool(address.is_private or address.is_loopback or address in cgnat)
    except ValueError:
        return False


def safe_health_payload(value,*,local_protocol,local_versions):
    if not isinstance(value,dict):
        return {"remote_reply":"NOT_JSON_OBJECT","protocol_match":False,
                "versions_match":False}
    remote_protocol=value.get("protocol")
    remote_versions=value.get("versions")
    local_version_ok=isinstance(local_versions,dict)
    remote_version_ok=isinstance(remote_versions,dict)
    # Version names are allowlisted by shape; hashes/version values are never printed.
    if local_version_ok and remote_version_ok:
        differences=sorted(k for k in set(local_versions)|set(remote_versions)
             if local_versions.get(k)!=remote_versions.get(k)
             and isinstance(k,str) and re.fullmatch("[a-zA-Z0-9_]{1,60}",k))
    else:
        differences=[]
    return {"remote_reply":"HEALTH_RESPONSE",
            "remote_status_ok":value.get("status")=="ok",
            "protocol_match":remote_protocol==local_protocol,
            "versions_match":local_version_ok and remote_version_ok and
                             local_versions==remote_versions,
            "version_component_name_differences":differences,
            "task_capacity":value.get("capacity") if type(value.get("capacity")) is int
                            and 0<=value["capacity"]<=64 else None}


def classify_io_error(exc):
    if isinstance(exc,ConnectionRefusedError):return "CONNECTION_REFUSED"
    if isinstance(exc,(TimeoutError,socket.timeout)):return "TIMEOUT"
    if isinstance(exc,ConnectionResetError):return "CONNECTION_RESET"
    if isinstance(exc,PermissionError):return "PERMISSION_DENIED"
    if isinstance(exc,EOFError):return "INCOMPLETE_HTTP_RESPONSE"
    if isinstance(exc,OSError):return "NETWORK_IO_FAILURE"
    if isinstance(exc,http.client.HTTPException):return "INVALID_HTTP_REPLY"
    return "HEALTH_REPLY_UNAVAILABLE"


def compute_health(ip,port,proto,versions,connection_factory=http.client.HTTPConnection):
    if not only_compute_peer(ip) or type(port) is not int or not 1<=port<=65535:
        return {"result":"STOP_INVALID_OR_NONPRIVATE_COMPUTE_ENDPOINT"}
    connection=None
    try:
        connection=connection_factory(ip,port,timeout=4)
        connection.request("GET","/health",headers={"Accept":"application/json"})
        response=connection.getresponse()
        code=response.status
        if code!=200:
            return {"result":"HEALTH_HTTP_DENIED" if code in (401,403) else
                    "HEALTH_HTTP_UNEXPECTED_STATUS","http_status":int(code)}
        raw=response.read(65_537)
        if len(raw)>65_536:return {"result":"HEALTH_REPLY_OVERSIZED"}
        return {"result":"HTTP_HEALTH_RECEIVED",
                **safe_health_payload(json.loads(raw.decode("utf-8")),
                   local_protocol=proto,local_versions=versions)}
    except (OSError,UnicodeError,ValueError,json.JSONDecodeError,http.client.HTTPException) as exc:
        return {"result":classify_io_error(exc)}
    finally:
        if connection is not None:
            try:connection.close()
            except (OSError,http.client.HTTPException):pass


def run():
    statuses={name:service(name) for name in UNITS}
    if PROVISION.is_symlink() or not (PROVISION/"skip_remote_client.py").is_file() \
       or not (PROVISION/"skip_remote_protocol.py").is_file():
        return {"mode":"EPISCENE_REMOTE_PREFLIGHT_DIAG","status":"STOP_MODULE_UNAVAILABLE",
                "services":statuses,"writes":0,"provider_requests":0}
    sys.path.insert(0,str(PROVISION))
    try:
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            client=importlib.import_module("skip_remote_client")
            protocol=importlib.import_module("skip_remote_protocol")
            configured=bool(client.configured())
            expected=protocol.versions()
            worker_ip=protocol.SERVER_IP
            worker_port=protocol.PORT
            worker_proto=protocol.PROTOCOL
    except Exception:
        return {"mode":"EPISCENE_REMOTE_PREFLIGHT_DIAG",
                "status":"STOP_CLIENT_IMPORT_OR_VERSION_PROBE",
                "services":statuses,"writes":0,"provider_requests":0}
    if not isinstance(worker_ip,str):
        return {"mode":"EPISCENE_REMOTE_PREFLIGHT_DIAG","status":"STOP_NO_INTERNAL_PEER",
                "services":statuses,"writes":0,"provider_requests":0}
    target=compute_health(worker_ip,worker_port,worker_proto,expected)
    # The main worker's health() may apply additional strict checks.
    client_health="NOT_CONFIGURED"
    if configured:
        try:
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                client.health()
            client_health="PASS"
        except Exception as exc:
            name=type(exc).__name__
            client_health="REMOTE_DEFERRED" if name=="RemoteDeferred" else "CLIENT_HEALTH_EXCEPTION"
    if target.get("result")=="HTTP_HEALTH_RECEIVED":
        if not target.get("protocol_match") or not target.get("versions_match"):
            diagnosis="REMOTE_PROTOCOL_OR_COMPONENT_VERSION_MISMATCH"
        elif target.get("remote_status_ok") and client_health=="PASS":
            diagnosis="COMPUTE_REMOTE_HEALTHY_NOW"
        elif target.get("remote_status_ok"):
            diagnosis="REMOTE_HEALTHY_BUT_CLIENT_PREFLIGHT_REJECTED"
        else:
            diagnosis="REMOTE_REPORTS_UNHEALTHY_STATUS"
    elif target.get("result") in {"CONNECTION_REFUSED","TIMEOUT","CONNECTION_RESET",
                                   "NETWORK_IO_FAILURE","HEALTH_HTTP_DENIED"}:
        diagnosis="REMOTE_UNREACHABLE_OR_PEER_ACCESS"
    else:
        diagnosis="REMOTE_DIAGNOSIS_INCOMPLETE"
    return {"mode":"EPISCENE_REMOTE_PREFLIGHT_DIAG","status":"READ_ONLY",
            "diagnosis":diagnosis,"client_configured":configured,
            "installed_client_health_result":client_health,
            "dedicated_compute_health":target,
            "services":statuses,"raw_endpoints_or_logs_exported":False,
            "provider_requests":0,"production_writes":0,
            "service_restarts":0,"analysis_jobs_claimed":0}


if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True,indent=2))
