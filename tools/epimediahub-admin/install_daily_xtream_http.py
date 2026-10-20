#!/usr/bin/env python3
"""Guarded daily EpiMediaHub Xtream HTTP-observation systemd timer installer.

--check is strictly read-only and reveals no credentials. --apply has an
independent deployment gate and only installs private systemd unit/timer;
it does not modify the dashboard database, app code or customer data.
The service executes under the EXISTING nonroot dashboard identity.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile

BASE=Path("/opt/epimediahub/provisioning")
DASHBOARD="epimediahub-provisioning.service"
STORAGE=Path("/var/lib/epimediahub")
NAME="epimediahub-xtream-expiry"
SYSTEMD=Path("/etc/systemd/system")
REQUIRED=("expiry_http_snapshot.py","expiry_http_worker.py",
          "xtream_expiry_refresh.py","expiry_provider_adapter.py")
HERE=Path(__file__).resolve().parent

class InstallRefused(RuntimeError):pass

def command(*args):
    return subprocess.check_output(args,timeout=30,text=True).strip()

def unit_text(account):
    if not isinstance(account,str) or not account or not all(
        c.isalnum() or c in "._-" for c in account):
        raise InstallRefused("invalid_service_account")
    return f"""[Unit]
Description=EpiMediaHub daily opt-in preliminary Xtream expiry observation
After=network-online.target {DASHBOARD}
Wants=network-online.target
ConditionPathExists={STORAGE}/provisioning.db

[Service]
Type=oneshot
User={account}
Environment=EPIMEDIAHUB_XTREAM_DAILY_HTTP_APPROVED=YES
Environment=PYTHONDONTWRITEBYTECODE=1
WorkingDirectory={BASE}
ExecStart={BASE}/.venv/bin/python {BASE}/expiry_http_worker.py --once
UMask=0077
TimeoutStartSec=180
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths={STORAGE}/admin-mobile
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
StandardOutput=journal
StandardError=journal
"""

def timer_text():
    return f"""[Unit]
Description=Daily preliminary Xtream subscription expiry refresh

[Timer]
OnCalendar=*-*-* 06:15:00 Europe/Berlin
AccuracySec=5min
RandomizedDelaySec=30s
Persistent=false
Unit={NAME}.service

[Install]
WantedBy=timers.target
"""

def check():
    if os.geteuid()!=0:
        raise InstallRefused("root_required")
    if BASE.is_symlink() or not BASE.is_dir():
        raise InstallRefused("unexpected_code_directory")
    if STORAGE.is_symlink() or not STORAGE.is_dir():
        raise InstallRefused("unexpected_data_directory")
    if command("systemctl","is-active",DASHBOARD)!="active":
        raise InstallRefused("dashboard_inactive")
    if command("systemctl","show",DASHBOARD,"-p","WorkingDirectory","--value")!=str(BASE):
        raise InstallRefused("unexpected_dashboard_workdir")
    account=command("systemctl","show",DASHBOARD,"-p","User","--value")
    if not account or account=="root":
        raise InstallRefused("requires_nonroot_dashboard_user")
    pwd.getpwnam(account)
    interpreter=BASE/".venv/bin/python"
    # Python in a standard venv is commonly a symlink to /usr/bin/python3.
    if not interpreter.exists() or not interpreter.is_file() or not os.access(interpreter,os.X_OK):
        raise InstallRefused("python_runtime_not_verified")
    # Staged administrator installer deploys these exact modules first.
    for name in REQUIRED:
        p=BASE/name
        if p.is_symlink() or not p.is_file():
            raise InstallRefused("missing_deployed_backend_module")
        if p.read_bytes()!= (HERE/name).read_bytes():
            raise InstallRefused("installed_backend_has_unreviewed_changes")
    # Never force ownership changes on a pre-existing private data folder.
    folder=STORAGE/"admin-mobile"
    if folder.exists() or folder.is_symlink():
        if folder.is_symlink() or not folder.is_dir():
            raise InstallRefused("unsafe_cache_folder")
        if folder.stat().st_uid!=pwd.getpwnam(account).pw_uid:
            raise InstallRefused("cache_folder_owner_review_required")
        if folder.stat().st_mode & 0o077:
            raise InstallRefused("cache_folder_must_be_private")
    elif STORAGE.stat().st_uid!=pwd.getpwnam(account).pw_uid:
        raise InstallRefused("data_directory_owner_review_required")
    for ext in ("service","timer"):
        path=SYSTEMD/f"{NAME}.{ext}"
        expected=unit_text(account) if ext=="service" else timer_text()
        if path.exists() and (path.is_symlink() or path.read_text()!=expected):
            raise InstallRefused("existing_unit_needs_review")
    return account

def apply(account):
    if os.environ.get("EPIMEDIAHUB_XTREAM_DAILY_HTTP_DEPLOY")!="YES":
        raise InstallRefused("explicit_timer_deploy_flag_required")
    written=[]
    try:
        folder=STORAGE/"admin-mobile"
        if not folder.exists():
            folder.mkdir(mode=0o700)
            written.append(folder)
        for ext in ("service","timer"):
            target=SYSTEMD/f"{NAME}.{ext}"
            if target.exists():continue
            payload=unit_text(account) if ext=="service" else timer_text()
            # Atomic installation. Preflight rejects unexpected existing units.
            fd,tmp=tempfile.mkstemp(prefix=f".{NAME}-",dir=SYSTEMD)
            try:
                with os.fdopen(fd,"w") as stream:stream.write(payload)
                os.chmod(tmp,0o644)
                os.replace(tmp,target)
                written.append(target)
            finally:
                if os.path.exists(tmp):os.unlink(tmp)
        command("systemctl","daemon-reload")
        command("systemctl","enable","--now",f"{NAME}.timer")
        if command("systemctl","is-active",f"{NAME}.timer")!="active":
            raise InstallRefused("timer_not_active")
        print("DAILY_XTREAM_PRELIMINARY_REFRESH_TIMER_ACTIVE")
        print("CALENDAR=06:15 Europe/Berlin")
        print("NEXT_RUN_VIA_SYSTEMCTL_LIST_TIMERS")
        print("TIMER_ENABLED_WITHOUT_MISSED_RUN_CATCHUP")
    except Exception:
        subprocess.run(["systemctl","disable","--now",f"{NAME}.timer"],
                       timeout=30,check=False,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for target in reversed(written):
            if target.is_dir():
                try:target.rmdir()
                except OSError:pass
            else:target.unlink(missing_ok=True)
        subprocess.run(["systemctl","daemon-reload"],timeout=30,check=False,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        raise

def main():
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check",action="store_true")
    mode.add_argument("--apply",action="store_true")
    options=parser.parse_args()
    account=check()
    if options.check:
        print("DAILY_XTREAM_TIMER_PREFLIGHT_OK; NO_WRITES")
    else:apply(account)

if __name__=="__main__":
    try:main()
    except (InstallRefused,OSError,subprocess.SubprocessError,ValueError):
        print("DAILY_XTREAM_TIMER_INSTALL_REFUSED",file=sys.stderr)
        sys.exit(2)
