#!/usr/bin/env python3
"""Guarded EpiMediaHub Admin mobile API installation.

Only the real provisioning dashboard host. --check is read-only on
production. --apply is an explicitly operator-controlled update with
backups and rollback of modified Python modules; never deploys Android APKs.
"""
from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path
import pwd
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

BASE=Path("/opt/epimediahub/provisioning")
SERVICE="epimediahub-provisioning.service"
HERE=Path(__file__).resolve().parent
MODULES=("monitor_rules.py","incident_store.py","mobile_registry.py",
         "mobile_flask.py","mobile_updates.py","fcm_sender.py","monitor_cycle.py",
         "live_analysis_snapshot.py","publish_private_release.py",
         "sync_private_updates.py","admin_monitor_runner.py")
HOOK="""

# Private EpiMediaHub Admin Android session API (no customer updater).
from mobile_flask import install as install_epimediahub_admin_mobile
install_epimediahub_admin_mobile(app)
"""
FLAG="install_epimediahub_admin_mobile"


def command(*args):
    return subprocess.check_output(args,text=True,timeout=22).strip()

def code(data:bytes):
    return hashlib.sha256(data).hexdigest()

def validate():
    if os.geteuid()!=0:
        raise RuntimeError("ROOT_REQUIRED")
    if BASE.is_symlink() or not BASE.is_dir():
        raise RuntimeError("PROVISIONING_DIRECTORY_NOT_FOUND")
    paths=[BASE/"wsgi.py",BASE/"dashboard_security.py",BASE/".venv/bin/python"]
    if not all(p.is_file() for p in paths):
        raise RuntimeError("EXPECTED_DASHBOARD_MODULES_MISSING")
    if command("systemctl","is-active",SERVICE)!="active":
        raise RuntimeError("DASHBOARD_SERVICE_NOT_ACTIVE")
    if command("systemctl","show",SERVICE,"-p","WorkingDirectory","--value")!=str(BASE):
        raise RuntimeError("WRONG_SERVICE_WORKING_DIRECTORY")
    user=command("systemctl","show",SERVICE,"-p","User","--value")
    if not user or user=="root":
        raise RuntimeError("DASHBOARD_MUST_HAVE_NON_ROOT_USER")
    pwd.getpwnam(user)
    environment=Path("/proc")/command("systemctl","show",SERVICE,"-p","MainPID","--value")/"environ"
    if not environment.is_file():
        raise RuntimeError("SERVICE_ENVIRONMENT_NOT_READABLE")
    env={}
    for chunk in environment.read_bytes().split(b"\0"):
        if b"=" in chunk:
            key,value=chunk.split(b"=",1)
            if key in (b"EPIMEDIAHUB_SECRET_KEY",b"EPIMEDIAHUB_DATA_DIR",
                       b"EPIMEDIAHUB_SECURE_COOKIES"):
                env[key.decode()]=value.decode("utf-8","replace")
    if len(env.get("EPIMEDIAHUB_SECRET_KEY",""))<32:
        raise RuntimeError("PERSISTENT_ADMIN_SESSION_SECRET_REQUIRED")
    if env.get("EPIMEDIAHUB_SECURE_COOKIES","1")=="0":
        raise RuntimeError("SECURE_ADMIN_COOKIES_REQUIRED")
    datadir=Path(env.get("EPIMEDIAHUB_DATA_DIR","/var/lib/epimediahub"))
    database=datadir/"provisioning.db"
    if database.is_symlink() or not database.is_file():
        raise RuntimeError("PRODUCTION_DATABASE_NOT_FOUND")
    wsgi=paths[0]
    current=wsgi.read_text(encoding="utf-8")
    if "install_dashboard_v080" not in current or "dashboard_security" not in current:
        raise RuntimeError("UNSUPPORTED_PROVISIONING_WSGI")
    if FLAG in current and HOOK.strip() not in current:
        raise RuntimeError("CUSTOM_ADMIN_MOBILE_HOOK_NEEDS_REVIEW")
    for name in MODULES:
        new=HERE/name
        if not new.is_file() or new.is_symlink():
            raise RuntimeError("SOURCE_FILE_MISSING:"+name)
        old=BASE/name
        if old.exists() and (old.is_symlink() or
                              code(old.read_bytes())!=code(new.read_bytes())):
            raise RuntimeError("EXISTING_MODULE_HAS_LOCAL_CHANGES:"+name)
    return datadir,database,current


def snapshot(source:Path,dest:Path):
    with sqlite3.connect(source.resolve().as_uri()+"?mode=ro",uri=True,timeout=30) as src:
        with sqlite3.connect(dest,timeout=30) as target:
            src.backup(target)
            if target.execute("PRAGMA quick_check").fetchone()[0]!="ok":
                raise RuntimeError("DATABASE_BACKUP_FAILED")
    dest.chmod(0o600)


def install(datadir:Path,database:Path,original:str):
    backup_root=Path("/var/backups/epimediahub")
    if backup_root.is_symlink():
        raise RuntimeError("UNSAFE_BACKUP_DIRECTORY")
    backup_root.mkdir(mode=0o700,parents=True,exist_ok=True)
    if backup_root.stat().st_mode & 0o077:
        raise RuntimeError("BACKUP_DIRECTORY_MUST_BE_PRIVATE")
    backup=Path(tempfile.mkdtemp(prefix="admin-mobile-",dir=backup_root))
    backup.chmod(0o700)
    written=[]
    stopped=False
    try:
        snapshot(database,backup/"provisioning.sqlite3")
        shutil.copy2(BASE/"wsgi.py",backup/"wsgi.py")
        for name in MODULES:
            current=BASE/name
            if current.exists():shutil.copy2(current,backup/name)
        staged=original if FLAG in original else original.rstrip()+"\n"+HOOK
        # Compile test the hook and the new modules without importing the live
        # wsgi. Importing it would trigger production schema migrations.
        import ast
        ast.parse(staged,filename="wsgi.py")
        for name in MODULES:
            ast.parse((HERE/name).read_text(),filename=name)
        command("systemctl","stop",SERVICE)
        stopped=True
        for name in MODULES:
            dest=BASE/name
            if not dest.exists():
                temp=BASE/("."+name+".admin-mobile-new")
                temp.write_bytes((HERE/name).read_bytes())
                temp.chmod(0o644)
                os.replace(temp,dest)
                written.append(name)
        temp=BASE/".wsgi.admin-mobile-new"
        temp.write_text(staged,encoding="utf-8")
        temp.chmod(0o644)
        os.replace(temp,BASE/"wsgi.py")
        command("systemctl","start",SERVICE)
        stopped=False
        if command("systemctl","is-active",SERVICE)!="active":
            raise RuntimeError("DASHBOARD_START_FAILED")
        try:
            with urllib.request.urlopen("http://127.0.0.1:8787/health",timeout=7) as response:
                if response.status!=200:
                    raise RuntimeError("LOCAL_DASHBOARD_HEALTH_FAILED")
        except (OSError,urllib.error.URLError):
            raise RuntimeError("LOCAL_DASHBOARD_HEALTH_FAILED") from None
        print("ADMIN_MOBILE_API_INSTALLED")
        print("BACKUP="+str(backup))
        print("PUSH_NOT_ACTIVATED_BY_INSTALLER")
    except Exception:
        # Restore source modules only. Database is intentionally not rolled
        # backward because other clients might have written meanwhile.
        shutil.copy2(backup/"wsgi.py",BASE/"wsgi.py")
        for name in written:
            try:(BASE/name).unlink()
            except FileNotFoundError:pass
        for name in MODULES:
            prev=backup/name
            if prev.exists():shutil.copy2(prev,BASE/name)
        if stopped or command("systemctl","is-active",SERVICE)!="active":
            subprocess.run(["systemctl","start",SERVICE],check=False,timeout=20)
        print("ROLLBACK_ATTEMPTED_BACKUP="+str(backup))
        raise


def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check",action="store_true")
    group.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    datadir,database,current=validate()
    if args.check:
        print("ADMIN_MOBILE_API_CHECK_OK")
        print("Existing license, customer, reseller and VPN records untouched.")
        return
    if os.environ.get("EPIMEDIAHUB_ADMIN_MOBILE_DEPLOY")!="YES":
        raise RuntimeError("Explicit EPIMEDIAHUB_ADMIN_MOBILE_DEPLOY=YES required")
    install(datadir,database,current)


if __name__=="__main__":
    try:main()
    except (RuntimeError,OSError,subprocess.CalledProcessError) as error:
        # Never print environment, customer identifiers or source contents.
        print("ADMIN_MOBILE_DEPLOY_STOP:"+type(error).__name__)
        sys.exit(2)
