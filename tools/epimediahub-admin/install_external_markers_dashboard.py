#!/usr/bin/env python3
"""Guarded one-time EpiScene external marker dashboard deployment.

Updates only the existing private Admin Flask module and installs two
read-only helper modules. Existing SQLite databases, EpiScene workers,
Android customer players, skip approvals and streaming services are untouched.
"""
from __future__ import annotations
import argparse
import ast
import os
from pathlib import Path
import pwd
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

API_DIR = Path("/opt/epimediahub/provisioning")
EPI_DIR = Path("/opt/episcene-learning/unified")
PRIVATE = Path("/var/lib/episcene-learning")
TRUSTED_CACHE = PRIVATE / "trusted-sources.sqlite3"
PROD_DB = Path("/var/lib/epimediahub/provisioning.db")
SERVICE = "epimediahub-provisioning.service"
TIMER = "episcene-trusted-sources.timer"
HERE = Path(__file__).resolve().parent
FILES = (
    ("mobile_flask.py", API_DIR),
    ("native_external_markers.py", API_DIR),
    ("report_trusted_marker_series.py", EPI_DIR),
)
OLD = HERE / "previous_mobile_flask.py"


class Stop(RuntimeError):
    pass


def command(*parts):
    return subprocess.run(parts, capture_output=True, text=True, timeout=40)


def require(condition, reason):
    if not condition:
        raise Stop(reason)


def regular(path):
    return path.is_file() and not path.is_symlink()


def status(unit):
    return command("systemctl", "is-active", unit).stdout.strip() == "active"


def validate():
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    require(API_DIR.is_dir() and not API_DIR.is_symlink(), "ORIGINAL_ADMIN_MISSING")
    require(EPI_DIR.is_dir() and not EPI_DIR.is_symlink(), "TRUSTED_BRIDGE_MISSING")
    require(regular(TRUSTED_CACHE) and regular(PROD_DB), "TRUSTED_CACHE_OR_DB_MISSING")
    require(status(SERVICE) and status(TIMER), "API_OR_PREFETCH_TIMER_INACTIVE")
    service_user = command("systemctl", "show", SERVICE, "-p", "User", "--value").stdout.strip()
    require(service_user == "epimediahub", "UNEXPECTED_SERVICE_ACCOUNT")
    pwd.getpwnam(service_user)
    for name, _ in FILES:
        path = HERE / name
        require(regular(path), "MISSING_REVIEWED_RELEASE_FILE_" + name)
        ast.parse(path.read_text("utf-8"), filename=name)
    require(regular(OLD), "OLD_ADMIN_RELEASE_BASELINE_MISSING")
    require(regular(API_DIR / "mobile_flask.py"), "ORIGINAL_ADMIN_API_MISSING")
    before = (API_DIR / "mobile_flask.py").read_bytes()
    expected = OLD.read_bytes()
    require(before == expected, "EXISTING_ADMIN_API_HAS_LOCAL_CHANGES")
    for name, directory in FILES[1:]:
        dest = directory / name
        require(not dest.exists() and not dest.is_symlink(),
                "EXISTING_EXTERNAL_MARKER_MODULE_NEEDS_REVIEW_" + name)
    # The API must be able to open both read-only DBs before changes.
    probe = (
        "import sqlite3;"
        "a=sqlite3.connect('file:/var/lib/episcene-learning/trusted-sources.sqlite3?mode=ro',"
        "uri=True,timeout=4);"
        "a.execute('PRAGMA query_only=ON');"
        "a.execute('SELECT COUNT(*) FROM trusted_external_cache').fetchone();"
        "a.close();"
        "b=sqlite3.connect('file:/var/lib/epimediahub/provisioning.db?mode=ro',"
        "uri=True,timeout=4);"
        "b.execute('PRAGMA query_only=ON');"
        "b.execute('SELECT COUNT(*) FROM skip_assets WHERE playlist_id IN (8,10)').fetchone();"
        "b.close()"
    )
    check=command("runuser","-u",service_user,"--","python3","-c",probe)
    require(check.returncode == 0, "API_READONLY_DATABASE_ACCESS_MISSING")
    require(regular(EPI_DIR/"analysis_identity.py"),"ANALYSIS_IDENTITY_MODULE_MISSING")
    return before


def health():
    for i in range(15):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8787/health",timeout=3) as response:
                if response.status == 200:
                    break
        except (OSError,urllib.error.URLError):
            pass
        time.sleep(1)
    else:
        raise Stop("ADMIN_SERVICE_HEALTH_FAILED")
    # A non-authenticated client must never see cached series names.
    try:
        urllib.request.urlopen(
            "http://127.0.0.1:8787/admin/mobile/episcene/markers",timeout=4)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            return
    raise Stop("ADMIN_EXTERNAL_MARKER_AUTH_GATE_FAILED")


def install(before):
    folder=Path("/var/backups/epimediahub")
    require(folder.is_dir() and not folder.is_symlink()
            and folder.stat().st_mode & 0o077 == 0,
            "PROTECTED_BACKUP_FOLDER_REQUIRED")
    backup=Path(tempfile.mkdtemp(prefix="marker-overview-",dir=folder))
    backup.chmod(0o700)
    shutil.copy2(API_DIR/"mobile_flask.py",backup/"mobile_flask.py")
    written=[]
    modified=False
    try:
        for name, directory in FILES[1:]:
            dest=directory/name
            require(not dest.exists() and not dest.is_symlink(),
                    "RACE_EXTERNAL_MARKER_MODULE_EXISTS")
            staged=directory/("." + name + ".staged")
            require(not staged.exists() and not staged.is_symlink(),
                    "STAGING_FILE_EXISTS")
            try:
                staged.write_bytes((HERE/name).read_bytes())
                staged.chmod(0o644)
                os.chown(staged,0,0)
                os.replace(staged,dest)
            finally:
                staged.unlink(missing_ok=True)
            written.append(dest)
        require((API_DIR/"mobile_flask.py").read_bytes()==before,
                "ACTIVE_ADMIN_API_CHANGED_DURING_INSTALL")
        next_file=API_DIR/".mobile_flask.py.external-marker-next"
        require(not next_file.exists() and not next_file.is_symlink(),
                "ADMIN_API_STAGING_EXISTS")
        try:
            next_file.write_bytes((HERE/"mobile_flask.py").read_bytes())
            next_file.chmod((API_DIR/"mobile_flask.py").stat().st_mode & 0o777)
            current=(API_DIR/"mobile_flask.py").stat()
            os.chown(next_file,current.st_uid,current.st_gid)
            os.replace(next_file,API_DIR/"mobile_flask.py")
            modified=True
        finally:
            next_file.unlink(missing_ok=True)
        require(command("systemctl","restart",SERVICE).returncode == 0,
                "API_RESTART_FAILED")
        health()
        require(status(SERVICE) and status(TIMER),"API_OR_TIMER_NOT_RUNNING")
    except BaseException:
        if modified:
            shutil.copy2(backup/"mobile_flask.py",API_DIR/"mobile_flask.py")
        for dest in written:
            dest.unlink(missing_ok=True)
        command("systemctl","restart",SERVICE)
        print("EXTERNAL_MARKER_DASHBOARD_ROLLBACK_ATTEMPTED",flush=True)
        raise
    print("EPISCENE EXTERNAL MARKER DASHBOARD API INSTALLED")
    print("ADMIN_SESSION_GATE_VERIFIED; ORIGINAL_DATABASES_UNCHANGED")
    print("BACKUP_LOCATION=" + str(backup))


def main():
    parser=argparse.ArgumentParser()
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--check",action="store_true")
    choice.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    before=validate()
    if args.check:
        print("EXTERNAL_MARKER_DASHBOARD_INSTALL_CHECK_OK")
        return
    install(before)


if __name__ == "__main__":
    try:
        main()
    except (Stop, ValueError, OSError, SyntaxError, sqlite3.Error,
            subprocess.TimeoutExpired) as exc:
        # Never print private paths, credentials, customer records or source code.
        print("EXTERNAL_MARKER_DASHBOARD_STOP:" + type(exc).__name__)
        if isinstance(exc, Stop):
            print(str(exc))
        sys.exit(2)
