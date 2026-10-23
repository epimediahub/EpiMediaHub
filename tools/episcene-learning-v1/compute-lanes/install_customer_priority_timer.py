#!/usr/bin/env python3
"""Guarded installation of a NEW, independent EpiScene customer-priority timer.

Never modifies/restarts production analysis, remote, scheduler or API services.
--check is fully read-only. --apply copies ONE hash-validated helper into a
new directory, installs two new systemd units, performs one dry-run-like sync
(the helper may create bounded priority requests only when matches exist),
and enables the 15-minute timer. An installation error removes the new units.

Priority requests are additive, expire within 7 days, and cannot replace an
active manual/reference request. No provider connections or marker release.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path("/opt/episcene-learning/customer-smart-priority")
SCRIPT=ROOT/"priority.py"
UNIT=Path("/etc/systemd/system/episcene-customer-smart-priority.service")
TIMER=Path("/etc/systemd/system/episcene-customer-smart-priority.timer")
SOURCE=Path(__file__).with_name("apply_customer_priority_requests.py")
API="epimediahub-provisioning.service"
ANALYSIS="epimediahub-analysis-worker.service"
PRIORITY_SERVICE=UNIT.name
PRIORITY_TIMER=TIMER.name
SERVICE_CONTENT="""[Unit]
Description=EpiScene authenticated customer marker analysis-priority requests
After=epimediahub-provisioning.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/episcene-learning/customer-smart-priority/priority.py --apply
NoNewPrivileges=true
PrivateNetwork=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/epimediahub
CapabilityBoundingSet=
CPUQuota=30%
MemoryMax=512M
TimeoutStartSec=60
"""
TIMER_CONTENT="""[Unit]
Description=EpiScene customer-triggered analysis priority every 15 minutes

[Timer]
OnBootSec=10min
OnUnitInactiveSec=15min
AccuracySec=1min
Unit=episcene-customer-smart-priority.service

[Install]
WantedBy=timers.target
"""

class Stop(Exception):pass

def ctl(*args,timeout=15):
    try:
        r=subprocess.run(["systemctl",*args],capture_output=True,
                         text=True,timeout=timeout,check=False)
        return r.returncode
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise Stop("SYSTEMD_COMMAND_FAILED") from exc

def active(service):
    return ctl("is-active","--quiet",service,timeout=8)==0

def load():
    if SOURCE.is_symlink() or not SOURCE.is_file() or SOURCE.stat().st_size>500_000:
        raise Stop("SMART_PRIORITY_SOURCE_UNAVAILABLE")
    if SOURCE.parent.is_symlink():
        raise Stop("UNTRUSTED_DOWNLOAD_DIRECTORY")
    spec=importlib.util.spec_from_file_location("episcene_staged_customer_priority",SOURCE)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def safe_no_existing_units():
    if ROOT.is_symlink() or ROOT.exists():
        raise Stop("EXISTING_INSTALL_DIRECTORY_REQUIRES_REVIEW")
    if any(p.exists() or p.is_symlink() for p in (UNIT,TIMER)):
        raise Stop("EXISTING_PRIORITY_UNIT_REQUIRES_REVIEW")
    if ROOT.parent.is_symlink() or not ROOT.parent.is_dir():
        raise Stop("EXPECTED_EPISCENE_INSTALL_ROOT_UNAVAILABLE")

def preflight():
    if os.geteuid()!=0:
        raise Stop("ROOT_REQUIRED")
    safe_no_existing_units()
    if not active(API) or not active(ANALYSIS):
        raise Stop("EXISTING_PRODUCTION_SERVICE_NOT_ACTIVE")
    module=load()
    check=module.run(apply=False)
    if check.get("check")!="PASS" or check.get("analysis_jobs_modified")!=0:
        raise Stop("SMART_PRIORITY_PREFLIGHT_NOT_SAFE")
    return {"mode":"EPISCENE_SMART_PRIORITY_INSTALL",
            "preflight":"PASS",
            "matching_existing_jobs":check["priority_requests_proposed"],
            "analysis_worker_active":True,
            "existing_services_unchanged":True,"changes_made":0}

def atomic_new(path,raw,mode=0o644):
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0)
    fd=os.open(path,flags,mode)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise

def rollback(created):
    # Only remove unit files actually created by this installer.
    try:
        ctl("disable","--now",PRIORITY_TIMER,timeout=15)
    except Stop:
        pass
    for p in reversed(created):
        try:
            if p.is_file() and not p.is_symlink():
                p.unlink()
            elif p.is_dir() and not p.is_symlink():
                p.rmdir()
        except OSError:
            return False
    try:
        ctl("daemon-reload",timeout=15)
        return True
    except Stop:
        return False

def install():
    status=preflight()
    created=[]
    try:
        ROOT.mkdir(mode=0o755)
        created.append(ROOT)
        raw=SOURCE.read_bytes()
        atomic_new(SCRIPT,raw)
        created.append(SCRIPT)
        atomic_new(UNIT,SERVICE_CONTENT.encode())
        created.append(UNIT)
        atomic_new(TIMER,TIMER_CONTENT.encode())
        created.append(TIMER)
        if ctl("daemon-reload")!=0:
            raise Stop("DAEMON_RELOAD_FAILED")
        if ctl("start",PRIORITY_SERVICE,timeout=90)!=0:
            raise Stop("FIRST_PRIORITY_SYNC_FAILED")
        if ctl("enable","--now",PRIORITY_TIMER,timeout=30)!=0:
            raise Stop("TIMER_ENABLE_FAILED")
        if not active(PRIORITY_TIMER) or not active(ANALYSIS) or not active(API):
            raise Stop("SERVICE_HEALTH_CHECK_FAILED")
        return dict(status,applied=True,customer_priority_timer_active=True,
                    analysis_worker_restarted=False,
                    priority_helper_sha256=hashlib.sha256(raw).hexdigest(),
                    new_units=[PRIORITY_SERVICE,PRIORITY_TIMER])
    except (Stop,OSError) as exc:
        return dict(status,applied=False,reason=(str(exc) if isinstance(exc,Stop)
                   else "IO_ERROR"),rollback_restored=rollback(created),
                   analysis_worker_restarted=False)

def verify():
    if os.geteuid()!=0:raise Stop("ROOT_REQUIRED")
    mod=load()
    if (SCRIPT.is_symlink() or not SCRIPT.is_file() or
        hashlib.sha256(SCRIPT.read_bytes()).digest()!=hashlib.sha256(SOURCE.read_bytes()).digest()):
        raise Stop("DEPLOYED_SMART_PRIORITY_VERSION_DRIFT")
    if UNIT.is_symlink() or TIMER.is_symlink() or (
        not UNIT.is_file() or UNIT.read_text()!=SERVICE_CONTENT or
        not TIMER.is_file() or TIMER.read_text()!=TIMER_CONTENT):
        raise Stop("DEPLOYED_SERVICE_UNIT_DRIFT")
    if not active(PRIORITY_TIMER) or not active(API) or not active(ANALYSIS):
        raise Stop("SERVICE_INACTIVE")
    check=mod.run(apply=False)
    return {"mode":"EPISCENE_SMART_PRIORITY_INSTALL","verified":True,
            "priority_timer_active":True,
            "installed_worker_versions":check["versions"],
            "analysis_worker_restarted":False,
            "provider_connections":0,"production_scheduler_file_modified":False}

def main():
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check",action="store_true")
    mode.add_argument("--apply",action="store_true")
    mode.add_argument("--verify",action="store_true")
    args=parser.parse_args()
    try:
        result=preflight() if args.check else verify() if args.verify else install()
    except (Stop,OSError,ValueError,RuntimeError,ImportError) as exc:
        result={"mode":"EPISCENE_SMART_PRIORITY_INSTALL",
                "status":"STOP_WITHOUT_NEW_WORKER_RESTART",
                "reason":str(exc) if isinstance(exc,Stop) else "PREFLIGHT_OR_RUNTIME_FAILURE"}
        print(json.dumps(result,sort_keys=True,indent=2))
        return 2
    print(json.dumps(result,sort_keys=True,indent=2))
    return 2 if args.apply and not result.get("applied") else 0

if __name__=="__main__":
    sys.exit(main())
