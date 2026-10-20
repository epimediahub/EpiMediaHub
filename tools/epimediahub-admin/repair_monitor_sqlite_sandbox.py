#!/usr/bin/env python3
"""Repair only the Admin monitor's SQLite WAL sandbox, never customer APIs.

A strict systemd sandbox may prevent a read-only SQLite WAL connection from
creating/mapping the accompanying -shm file. Do not change database ownership,
chmod the database, disable systemd protection, or restart the dashboard.
This repairs a recognized installed service unit only; all other units must
match the approved release. If the smoke test fails, restore the original unit.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import deploy_admin_all as admin

def checked_units():
    datadir,user,_,_,creds=admin.validate()
    approved=admin.files(user,datadir,creds)
    monitor=admin.UNIT_DIR/(admin.MONITOR+".service")
    if monitor not in approved or not monitor.is_file() or monitor.is_symlink():
        raise RuntimeError("ADMIN_MONITOR_UNIT_MISSING_OR_LINKED")
    for path,expected in approved.items():
        if path==monitor:
            continue
        if not path.is_file() or path.is_symlink() or path.read_text()!=expected:
            raise RuntimeError("OTHER_ADMIN_UNIT_DIFFERS:"+path.name)
    current=monitor.read_text()
    new=approved[monitor]
    old=new.replace(
        f"ReadWritePaths={datadir}\nReadOnlyPaths={datadir}/provisioning.db\n",
        f"ReadWritePaths={datadir}/admin-mobile\n"
    )
    if old==new:
        raise RuntimeError("ADMIN_MONITOR_REPAIR_TEMPLATE_INVALID")
    if current not in (old,new):
        raise RuntimeError("ADMIN_MONITOR_UNIT_UNRECOGNIZED")
    return monitor,current,new

def run(args):
    return subprocess.run(args,check=True,timeout=140,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,text=True)

def replace_atomic(path:Path,contents:str):
    fd,name=tempfile.mkstemp(prefix=".admin-monitor-repair-",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            os.fchmod(f.fileno(),0o644)
            f.write(contents)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def repair():
    path,old,new=checked_units()
    if old==new:
        print("ADMIN_MONITOR_SANDBOX_ALREADY_UPDATED")
        return
    backup_dir=Path("/var/backups/epimediahub")
    if (backup_dir.is_symlink() or not backup_dir.is_dir() or
        backup_dir.stat().st_mode&0o077):
        raise RuntimeError("PRIVATE_BACKUP_DIRECTORY_REQUIRED")
    fd,backup=tempfile.mkstemp(prefix="admin-monitor-unit-",suffix=".bak",
                                dir=backup_dir)
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        os.fchmod(f.fileno(),0o600)
        f.write(old)
        f.flush()
        os.fsync(f.fileno())
    try:
        replace_atomic(path,new)
        run(["systemctl","daemon-reload"])
        # One-shot command exit status, not is-active (oneshot becomes inactive).
        run(["systemctl","start",admin.MONITOR+".service"])
    except Exception:
        replace_atomic(path,old)
        subprocess.run(["systemctl","daemon-reload"],check=False,
                       timeout=30)
        print("ADMIN_MONITOR_SANDBOX_TEST_FAILED_RESTORED")
        print("BACKUP="+backup)
        raise
    print("ADMIN_MONITOR_SQLITE_SANDBOX_FIXED")
    print("ADMIN_MONITOR_SMOKE_TEST_SUCCESS")
    print("BACKUP="+backup)
    print("DASHBOARD_NOT_RESTARTED")
    print("UPDATE_SYNC_UNIT_UNCHANGED")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check",action="store_true")
    group.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    try:
        monitor,current,approved=checked_units()
        if args.check:
            print("ADMIN_MONITOR_SANDBOX_CHECK_OK")
            print("STATUS="+("CURRENT" if current==approved else "OLD_NEEDS_REPAIR"))
        else:
            repair()
    except Exception as error:
        print("ADMIN_MONITOR_REPAIR_STOP:"+type(error).__name__)
        if isinstance(error,RuntimeError) and str(error).isupper():
            print(str(error))
        sys.exit(2)
