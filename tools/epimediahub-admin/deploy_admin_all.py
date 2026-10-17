#!/usr/bin/env python3
"""One guarded, operator-approved private Admin backend + monitoring deployment.

Never touches IPTV player updater, licenses, reseller records or WireGuard.
One --check or one --apply invocation; prerequisite missing => STOP before
modifying production. All server secrets stay in private files on Hetzner.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys

import install_mobile_backend as backend

PROJECT="epimediahub-admin"
UNIT_DIR=Path("/etc/systemd/system")
SERVICE=backend.SERVICE
MONITOR="epimediahub-admin-monitor"
UPDATES="epimediahub-admin-update-sync"


def capture(*args):
    return subprocess.check_output(args,text=True,timeout=30).strip()


def owner_guard(file:Path,uid:int):
    if (file.is_symlink() or not file.is_file()
        or file.stat().st_uid!=uid or file.stat().st_mode & 0o077):
        raise RuntimeError("PRIVATE_ADMIN_CREDENTIAL_FILE_INVALID")


def validate():
    datadir,database,wsgi=backend.validate()
    service_user=capture("systemctl","show",SERVICE,"-p","User","--value")
    entry=pwd.getpwnam(service_user)
    admin=datadir/"admin-mobile"
    # Operators create these root-protected inputs ONCE, before the final
    # install, not in ChatGPT or in a public GitHub repository.
    creds=admin/"firebase-fcm-service-account.json"
    token=admin/"github-actions.token"
    if (not admin.is_dir() or admin.is_symlink()
        or admin.stat().st_uid!=entry.pw_uid or admin.stat().st_mode&0o077):
        raise RuntimeError("PRIVATE_ADMIN_DIRECTORY_NOT_PREPARED")
    owner_guard(creds,entry.pw_uid)
    owner_guard(token,entry.pw_uid)
    # Google service identity is verified locally but never printed.
    if creds.stat().st_size > 24_000:
        raise RuntimeError("FCM_SERVICE_CREDENTIAL_TOO_LARGE")
    service=json.loads(creds.read_text(encoding="utf-8"))
    if (service.get("type")!="service_account"
        or service.get("project_id")!=PROJECT
        or not isinstance(service.get("client_email"),str)
        or not isinstance(service.get("private_key"),str)
        or not service["private_key"].startswith("-----BEGIN PRIVATE KEY-----")):
        raise RuntimeError("FCM_SERVER_SERVICE_ACCOUNT_INVALID")
    raw=token.read_text(encoding="utf-8").strip()
    if not 35<=len(raw)<=250 or "\n" in raw:
        raise RuntimeError("GITHUB_ACTIONS_READ_TOKEN_INVALID")
    if not database.is_file():
        raise RuntimeError("PROVISIONING_DB_NOT_FOUND")
    return datadir,service_user,wsgi,admin,creds


def service_unit(name:str,service_user:str,datadir:Path,credential_file:Path):
    if name==MONITOR:
        py="admin_monitor_runner.py"
        env=f"Environment=GOOGLE_APPLICATION_CREDENTIALS={credential_file}\n"
        env+=f"Environment=EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID={PROJECT}\n"
    else:
        py="sync_private_updates.py"
        env=""
    return (f"[Unit]\nDescription=Private EpiMediaHub Admin {name} cycle\n"
            f"After=network-online.target {SERVICE}\nWants=network-online.target\n\n"
            f"[Service]\nType=oneshot\nUser={service_user}\n"
            f"WorkingDirectory={backend.BASE}\n"
            f"Environment=EPIMEDIAHUB_DATA_DIR={datadir}\n"
            +env+
            f"ExecStart={backend.BASE}/.venv/bin/python {backend.BASE}/{py}\n"
            f"NoNewPrivileges=true\nPrivateTmp=true\n"
            f"ProtectSystem=strict\nReadWritePaths={datadir}/admin-mobile\n"
            f"ProtectHome=true\n"
            f"TimeoutStartSec=100\n")


def timer_unit(service_name:str,period:str):
    return (f"[Unit]\nDescription=Periodic private Admin {service_name}\n\n"
            f"[Timer]\nOnBootSec=3min\nOnUnitActiveSec={period}\n"
            f"Persistent=true\nUnit={service_name}.service\n\n"
            f"[Install]\nWantedBy=timers.target\n")


def files(service_user,datadir,creds):
    return {
        UNIT_DIR/(MONITOR+".service"):service_unit(MONITOR,service_user,datadir,creds),
        UNIT_DIR/(UPDATES+".service"):service_unit(UPDATES,service_user,datadir,creds),
        UNIT_DIR/(MONITOR+".timer"):timer_unit(MONITOR,"5min"),
        UNIT_DIR/(UPDATES+".timer"):timer_unit(UPDATES,"1h"),
        UNIT_DIR/(SERVICE+".d/epimediahub-admin.conf"):(
            "[Service]\nEnvironment=EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID="+PROJECT+"\n"
            "Environment=GOOGLE_APPLICATION_CREDENTIALS="+str(creds)+"\n"),
    }


def deploy():
    datadir,user,wsgi,admin,creds=validate()
    wanted=files(user,datadir,creds)
    for path,content in wanted.items():
        if path.is_symlink() or (path.exists() and path.read_text()!=content):
            raise RuntimeError("CUSTOM_SYSTEMD_UNIT_NEEDS_REVIEW:"+path.name)
    # Never modify dashboard if a systemd unit conflicts.
    old=backend.BASE/"wsgi.py"
    if not old.is_file():
        raise RuntimeError("EXPECTED_WSGI_MISSING")
    written=[]
    applied_backend=False
    try:
        # Stage the service FCM environment BEFORE dashboard backend restart.
        # Only additive exact-content unit files are accepted.
        for path,content in wanted.items():
            path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
            if not path.exists():
                path.write_text(content,encoding="utf-8")
                path.chmod(0o644)
                written.append(path)
        capture("systemctl","daemon-reload")
        backend.install(datadir,datadir/"provisioning.db",wsgi)
        applied_backend=True
        for unit in (MONITOR+".timer",UPDATES+".timer"):
            capture("systemctl","enable","--now",unit)
        if capture("systemctl","is-active",SERVICE)!="active":
            raise RuntimeError("DASHBOARD_NOT_ACTIVE_AFTER_INSTALL")
    except Exception:
        for unit in (MONITOR+".timer",UPDATES+".timer"):
            subprocess.run(["systemctl","disable","--now",unit],
                           check=False,timeout=30)
        for path in written:
            path.unlink(missing_ok=True)
        subprocess.run(["systemctl","daemon-reload"],check=False,timeout=20)
        # Do not automatically roll back the database: live writes may exist.
        # Backend's own installer restores WSGI if its health probe failed.
        if applied_backend:
            print("WARNING: Admin API installed, timers disabled after unit failure.")
        raise
    print("PRIVATE_ADMIN_COMPLETE_SERVER_MODULES_INSTALLED")
    print("Updater polling: hourly. EpiScene monitoring: every five minutes.")
    print("Android APK distribution remains private; no player updater changes.")


def main():
    parser=argparse.ArgumentParser()
    args=parser.add_mutually_exclusive_group(required=True)
    args.add_argument("--check",action="store_true")
    args.add_argument("--apply",action="store_true")
    parsed=parser.parse_args()
    datadir,user,_,admin,creds=validate()
    if parsed.check:
        for path,content in files(user,datadir,creds).items():
            if path.is_symlink() or (path.exists() and path.read_text()!=content):
                raise RuntimeError("CUSTOM_SYSTEMD_UNIT_NEEDS_REVIEW")
        print("ADMIN_ALL_IN_ONE_SERVER_PREFLIGHT_OK")
        print("Existing customer dashboard, IPTV, resale and VPN files untouched.")
        return
    if os.environ.get("EPIMEDIAHUB_ADMIN_INSTALL_CONFIRMED")!="YES":
        raise RuntimeError("OWNER_CONFIRMATION_REQUIRED")
    deploy()


if __name__=="__main__":
    try:main()
    except (RuntimeError,PermissionError,FileNotFoundError,ValueError,
            OSError,subprocess.CalledProcessError):
        print("ADMIN_ALL_IN_ONE_INSTALL_STOP:CHECK_LOGS_LOCALLY")
        sys.exit(2)
