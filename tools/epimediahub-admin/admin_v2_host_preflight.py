#!/usr/bin/env python3
"""Read-only EpiMediaHub Admin V2 host preflight.

Never imports WSGI, touches the live database, contacts IPTV providers,
displays credentials, installs packages or restarts services. The printed
check names and statuses are safe to share with support.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys

BASE=Path("/opt/epimediahub/provisioning")
DATA=Path("/var/lib/epimediahub")
SERVICE="epimediahub-provisioning.service"
NAMES=(
 "mobile_flask.py","native_management_data.py",
 "native_management_actions.py","native_management_edits.py",
 "native_legacy_bridge.py","native_delete_confirmation.py",
 "native_marker_review.py","expiry_report_core.py","expiry_cache.py",
 "expiry_provider_adapter.py","expiry_report_rows.py",
 "expiry_report_coverage.py","expiry_report_calendar.py",
 "expiry_report_pdf.py","expiry_report_publish.py",
 "xtream_expiry_refresh.py","expiry_http_snapshot.py",
 "expiry_http_worker.py",
)


def service_value(*parts):
    try:
        result=subprocess.run(("systemctl",)+parts,capture_output=True,
                text=True,check=False,timeout=8)
        return result.stdout.strip() if result.returncode==0 else ""
    except (OSError,subprocess.TimeoutExpired):
        return ""


def private_file_ok(path,uid):
    try:
        if path.is_symlink():return False
        info=path.stat()
        return stat.S_ISREG(info.st_mode) and info.st_uid==uid and (
            info.st_mode & 0o077)==0 and info.st_size>0
    except OSError:return False


def private_dir_ok(path,uid):
    try:
        if path.is_symlink():return False
        info=path.stat()
        return stat.S_ISDIR(info.st_mode) and info.st_uid==uid and (
            info.st_mode & 0o077)==0
    except OSError:return False


def inspect():
    values={}
    values["running_as_root"]=(os.geteuid()==0)
    values["dashboard_service_active"]=(service_value(
        "is-active",SERVICE)=="active")
    values["expected_dashboard_directory"]=(
        not BASE.is_symlink() and BASE.is_dir() and
        service_value("show",SERVICE,"-p","WorkingDirectory","--value")==str(BASE))
    account=service_value("show",SERVICE,"-p","User","--value")
    uid=None
    try:
        if account and account!="root":
            uid=pwd.getpwnam(account).pw_uid
    except KeyError:pass
    values["dashboard_runs_as_nonroot_user"]=uid is not None
    values["database_file_present"]=(
        not (DATA/"provisioning.db").is_symlink() and
        (DATA/"provisioning.db").is_file())
    values["python_environment_present"]=(BASE/".venv/bin/python").exists()
    values["admin_route_hook_present"]=False
    if (BASE/"wsgi.py").is_file() and not (BASE/"wsgi.py").is_symlink():
        try:
            source=(BASE/"wsgi.py").read_text(encoding="utf-8")
            values["admin_route_hook_present"]=(
                "install_epimediahub_admin_mobile" in source)
        except (OSError,UnicodeError):pass
    values["private_admin_folder_ready"]=(uid is not None and
        private_dir_ok(DATA/"admin-mobile",uid))
    values["fcm_server_credential_ready"]=(uid is not None and
        private_file_ok(DATA/"admin-mobile"/
                        "firebase-fcm-service-account.json",uid))
    values["github_actions_read_token_ready"]=(uid is not None and
        private_file_ok(DATA/"admin-mobile"/"github-actions.token",uid))
    values["existing_admin_module_present"]=(
        (BASE/"mobile_flask.py").is_file() and
        not (BASE/"mobile_flask.py").is_symlink())
    values["existing_admin_v2_module_count"]=sum(
        int((BASE/name).is_file() and not (BASE/name).is_symlink())
        for name in NAMES)
    values["expected_admin_v2_module_count"]=len(NAMES)
    values["daily_xtream_timer_present"]=(
        Path("/etc/systemd/system/epimediahub-xtream-expiry.timer").is_file())
    values["daily_xtream_timer_active"]=(service_value(
        "is-active","epimediahub-xtream-expiry.timer")=="active")
    # A signed release is gated by GitHub Actions, not host preflight.
    values["signing_key_status"]="requires_separate_GitHub_and_device_verification"
    values["tests_and_customer_data_modified"]=False
    required=(
      "running_as_root","dashboard_service_active",
      "expected_dashboard_directory","dashboard_runs_as_nonroot_user",
      "database_file_present","python_environment_present",
      "admin_route_hook_present")
    values["basic_native_upgrade_preflight_ready"]=all(values[k] for k in required)
    return values


def main():
    parser=argparse.ArgumentParser(description="No-change server preflight")
    parser.add_argument("--check",action="store_true",required=True)
    args=parser.parse_args()
    print("EPIMEDIAHUB_ADMIN_V2_HOST_PREFLIGHT_READ_ONLY")
    print(json.dumps(inspect(),sort_keys=True,indent=2))


if __name__=="__main__":
    try:main()
    except Exception:
        # Never leak systemd properties, environment or raw file bytes.
        print("ADMIN_V2_PREFLIGHT_UNAVAILABLE",file=sys.stderr)
        sys.exit(2)
