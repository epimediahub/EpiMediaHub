#!/usr/bin/env python3
"""Guarded upgrade for *native* Admin management API (never an APK release).

Install only when native Android authentication AND write actions are fully
tested. Requires operator opt-in; checks the exact known stable mobile backend,
backs up files, atomically replaces only two modules, restarts dashboard and
rolls back on failure. Does not write to customer/license/VPN DB tables.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

BASE=Path("/opt/epimediahub/provisioning")
SERVICE="epimediahub-provisioning.service"
HERE=Path(__file__).resolve().parent
MODULES=("mobile_flask.py","native_management_data.py","native_management_actions.py",
         "native_management_edits.py","native_legacy_bridge.py")
# Git blob SHA of released, already-deployed Android Admin v1 module on main.
KNOWN_MAIN_SHA={"mobile_flask.py":"074979ed6e523ba899106f54549fcab1ec432f2c"}

def blob_sha(blob:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(blob)).encode()+bytes([0])+blob).hexdigest()

def cmd(*parts):
    return subprocess.check_output(parts,timeout=40,text=True).strip()

def require_safe_paths():
    if os.geteuid()!=0 or BASE.is_symlink() or not BASE.is_dir():
        raise RuntimeError("REQUIRES_ROOT_AND_EXPECTED_HOST")
    if cmd("systemctl","is-active",SERVICE)!="active":
        raise RuntimeError("DASHBOARD_NOT_ACTIVE")
    if cmd("systemctl","show",SERVICE,"-p","WorkingDirectory","--value")!=str(BASE):
        raise RuntimeError("WRONG_DASHBOARD_WORKING_DIRECTORY")
    if "install_epimediahub_admin_mobile" not in (BASE/"wsgi.py").read_text():
        raise RuntimeError("ADMIN_MOBILE_BLUEPRINT_NOT_INSTALLED")
    # Refuse deployment if the existing authentication form cannot be driven
    # natively with the exact known field. Do not execute or print app.py.
    login_ast=ast.parse((BASE/"app.py").read_text(encoding="utf-8"))
    logins=[n for n in ast.walk(login_ast)
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
            and n.name=="login"]
    if len(logins)!=1:
        raise RuntimeError("NATIVE_LOGIN_HANDLER_UNVERIFIED")
    fields=[]
    for n in ast.walk(logins[0]):
        if (isinstance(n,ast.Call) and
            isinstance(n.func,ast.Attribute) and n.func.attr=="get" and
            isinstance(n.func.value,ast.Attribute) and
            n.func.value.attr=="form" and n.args and
            isinstance(n.args[0],ast.Constant)):
            fields.append(n.args[0].value)
    if "password" not in fields:
        raise RuntimeError("NATIVE_LOGIN_FORM_FIELD_UNVERIFIED")
    # The native JSON wrappers delegate ONLY to these production business
    # handlers, never to a guessed new implementation.
    for module,handler in (("annual_license.py","admin_grant_year"),
                           ("vpn_auto_enroll.py","grant_trial_auto")):
        source_tree=ast.parse((BASE/module).read_text(encoding="utf-8"))
        found=[n for n in ast.walk(source_tree)
               if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
               and n.name==handler]
        if len(found)!=1:
            raise RuntimeError("ORIGINAL_GRANT_HANDLER_UNVERIFIED:"+module)
    source={}
    to_copy=[]
    for name in MODULES:
        candidate=HERE/name
        target=BASE/name
        if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size>150_000:
            raise RuntimeError("UNSAFE_STAGED_MODULE:"+name)
        data=candidate.read_bytes()
        ast.parse(data.decode("utf-8"),filename=name)
        source[name]=data
        if target.exists() and (target.is_symlink() or not target.is_file()):
            raise RuntimeError("UNSAFE_INSTALLED_MODULE:"+name)
        if target.exists():
            installed=target.read_bytes()
            if installed==data:
                continue
            if name not in KNOWN_MAIN_SHA or blob_sha(installed)!=KNOWN_MAIN_SHA[name]:
                raise RuntimeError("LOCAL_MODULE_MODIFICATIONS_REQUIRE_REVIEW:"+name)
        to_copy.append(name)
    return source,to_copy

def probe():
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8787/health",timeout=3) as r:
                if r.status==200:
                    break
        except (urllib.error.URLError,TimeoutError,OSError):
            pass
        time.sleep(1)
    else:
        raise RuntimeError("DASHBOARD_HEALTH_FAILED")

    for path in ("/admin/mobile/management/overview",
                 "/admin/mobile/management/customers",
                 "/admin/mobile/management/resellers"):
        try:
            urllib.request.urlopen("http://127.0.0.1:8787"+path,timeout=5)
        except urllib.error.HTTPError as err:
            if err.code==401:
                continue
            raise RuntimeError("ANONYMOUS_API_BAD_STATUS_"+str(err.code))
        raise RuntimeError("UNAUTHORIZED_API_ACCESS")

def upgrade(source,to_copy):
    if not to_copy:
        print("NATIVE_MANAGEMENT_API_ALREADY_SYNCED")
        return
    backups=Path("/var/backups/epimediahub")
    if backups.is_symlink():
        raise RuntimeError("BACKUP_DIRECTORY_LINKED")
    backups.mkdir(parents=True,exist_ok=True,mode=0o700)
    if backups.stat().st_mode & 0o077:
        raise RuntimeError("BACKUP_DIRECTORY_NOT_PRIVATE")
    backup=Path(tempfile.mkdtemp(dir=backups,prefix="native-admin-v2-"))
    backup.chmod(0o700)
    original={}
    for name in MODULES:
        target=BASE/name
        if target.exists():
            original[name]=target.read_bytes()
            previous=backup/name
            previous.write_bytes(original[name])
            previous.chmod(0o600)
    touched=[]
    restart_attempted=False
    try:
        for name in to_copy:
            target=BASE/name
            fd,temporary=tempfile.mkstemp(dir=BASE,prefix="."+name+".native-")
            try:
                with os.fdopen(fd,"wb") as stream:
                    stream.write(source[name])
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary,0o644)
                if target.exists():
                    shutil.copystat(target,temporary)
                    shutil.chown(temporary,user=target.owner(),group=target.group())
                os.replace(temporary,target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            touched.append(name)
        restart_attempted=True
        cmd("systemctl","restart",SERVICE)
        probe()
        print("NATIVE_MANAGEMENT_API_UPGRADE_OK")
        print("BACKUP="+str(backup))
    except Exception:
        for name in touched:
            destination=BASE/name
            if name in original:
                temporary=BASE/("."+name+".restore-"+str(os.getpid()))
                temporary.write_bytes(original[name])
                os.chmod(temporary,0o644)
                os.replace(temporary,destination)
            else:
                destination.unlink(missing_ok=True)
        if restart_attempted:
            subprocess.run(["systemctl","restart",SERVICE],timeout=40,check=False)
        print("ROLLBACK_ATTEMPTED; BACKUP="+str(backup))
        raise

def main():
    cli=argparse.ArgumentParser()
    actions=cli.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check",action="store_true")
    actions.add_argument("--apply",action="store_true")
    options=cli.parse_args()
    source,to_copy=require_safe_paths()
    if options.check:
        print("NATIVE_MANAGEMENT_API_PREFLIGHT_OK")
        print("MODULES_TO_UPDATE="+str(len(to_copy)))
        print("DB_UNCHANGED")
        return
    if os.environ.get("EPIMEDIAHUB_NATIVE_ADMIN_DEPLOY")!="YES":
        raise RuntimeError("EXPLICIT_DEPLOY_APPROVAL_REQUIRED")
    upgrade(source,to_copy)

if __name__=="__main__":
    try:
        main()
    except (RuntimeError,OSError,UnicodeError,ValueError,SyntaxError,subprocess.SubprocessError) as error:
        print("NATIVE_MANAGEMENT_API_DEPLOY_FAILED:"+type(error).__name__)
        sys.exit(2)
