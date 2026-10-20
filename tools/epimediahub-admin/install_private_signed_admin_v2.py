#!/usr/bin/env python3
"""One-shot private Admin V2 signed-release handoff on the existing Hetzner.

This does NOT sign, rebuild, or publicly release an APK. The GitHub Actions
run already pinned the signer certificate and APK hash. This installer
updates only the read-only Actions artifact synchronizer and, if absent,
its private hourly systemd service/timer. Then it imports the signed bundle
as the non-root dashboard user. No changes to IPTV playlists, customer
accounts, VPN, EpiScene or the separate player updater.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request

BASE=Path("/opt/epimediahub/provisioning")
DATA=Path("/var/lib/epimediahub/admin-mobile")
UNIT_DIR=Path("/etc/systemd/system")
NAME="epimediahub-admin-update-sync"
DASHBOARD="epimediahub-provisioning.service"
COMMIT="76f1aba9f4f6e692415bdbfecc75b463218160cb"
SOURCES={
  "sync_private_updates.py":(
    "3d47d0ab2a055f9276051a908bc6e80313fa54b9",
    {"bc2372363ca93e6e539ad364dac6eb69cf852072"}),
  "publish_private_release.py":(
    "f445157710825482ea3d85cce5519754c341a727",
    set()),
}
BASE_URL="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/"+COMMIT+"/tools/epimediahub-admin/"
MAX_CODE_BYTES=24000


class Stop(RuntimeError):
    pass


def cmd(*args,timeout=20):
    result=subprocess.run(args,check=False,capture_output=True,text=True,timeout=timeout)
    if result.returncode:
        raise Stop("host prerequisite/service command did not succeed")
    return result.stdout.strip()


def git_sha(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\x00"+data).hexdigest()


def private_owner(path,uid,directory=False):
    if path.is_symlink():
        return False
    try: st=path.stat()
    except OSError:return False
    return (st.st_uid==uid and not st.st_mode&0o077 and
            (stat.S_ISDIR(st.st_mode) if directory else
             stat.S_ISREG(st.st_mode)))


def service_unit(user):
    return f"""[Unit]
Description=Private EpiMediaHub Admin signed release artifact sync
After=network-online.target {DASHBOARD}
Wants=network-online.target

[Service]
Type=oneshot
User={user}
WorkingDirectory={BASE}
Environment=EPIMEDIAHUB_DATA_DIR=/var/lib/epimediahub
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart={BASE}/.venv/bin/python {BASE}/sync_private_updates.py
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths={DATA}
TimeoutStartSec=150
"""


def timer_unit():
    return f"""[Unit]
Description=Private EpiMediaHub Admin signed update refresh

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Persistent=true
Unit={NAME}.service

[Install]
WantedBy=timers.target
"""


def check():
    if os.geteuid()!=0:
        raise Stop("root required")
    if BASE.is_symlink() or not BASE.is_dir() or not (BASE/".venv/bin/python").exists():
        raise Stop("unexpected installed Admin runtime")
    if cmd("systemctl","is-active",DASHBOARD)!="active":
        raise Stop("provisioning service inactive")
    user=cmd("systemctl","show",DASHBOARD,"-p","User","--value")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}",user) or user=="root":
        raise Stop("invalid service identity")
    account=pwd.getpwnam(user)
    if not private_owner(DATA,account.pw_uid,directory=True):
        raise Stop("private Admin store permissions mismatch")
    if not private_owner(DATA/"github-actions.token",account.pw_uid):
        raise Stop("private Actions read token unavailable")
    for dep in ("mobile_flask.py","mobile_updates.py"):
        if not (BASE/dep).is_file() or (BASE/dep).is_symlink():
            raise Stop("native backend or private updater missing")
    service_state=subprocess.run(
        ["systemctl","is-active",NAME+".service"],
        check=False,capture_output=True,text=True,timeout=8).stdout.strip()
    if service_state=="active":
        raise Stop("release sync currently running")
    for module,(target_sha,previous) in SOURCES.items():
        path=BASE/module
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise Stop("unsafe synchronizer file")
        if path.exists() and git_sha(path.read_bytes()) not in ({target_sha}|previous):
            raise Stop("locally modified synchronizer requires manual review")
    svc=UNIT_DIR/(NAME+".service")
    timer=UNIT_DIR/(NAME+".timer")
    if svc.exists() != timer.exists():
        raise Stop("partially installed update timer requires review")
    for path,expected in ((svc,service_unit(user)),(timer,timer_unit())):
        if path.is_symlink():raise Stop("linked systemd unit")
        if path.exists():
            existing=path.read_text()
            # Preserve previous EpiMediaHub service definitions as deployed:
            # no overwrite, but demand nonroot user and the exact entrypoint.
            if (f"User={user}" not in existing and path==svc):
                raise Stop("existing update service identity mismatch")
            if path==svc and f"ExecStart={BASE}/.venv/bin/python {BASE}/sync_private_updates.py" not in existing:
                raise Stop("existing update entrypoint mismatch")
            if path==timer and f"Unit={NAME}.service" not in existing:
                raise Stop("existing update timer target mismatch")
    return user,not svc.exists()


def download_verified():
    data={}
    for name,(sha,_) in SOURCES.items():
        req=urllib.request.Request(BASE_URL+name,headers={
            "User-Agent":"epimediahub-admin-private-release-install/1"})
        with urllib.request.urlopen(req,timeout=25) as response:
            raw=response.read(MAX_CODE_BYTES+1)
        if len(raw)>MAX_CODE_BYTES or git_sha(raw)!=sha:
            raise Stop("pinned source integrity mismatch")
        compile(raw.decode("utf-8"),name,"exec")
        data[name]=raw
    return data


def install_module(path,body):
    # Atomic same-directory replacement. Original retained in private backup.
    fd,temp=tempfile.mkstemp(prefix=".epi-private-sync-",dir=BASE)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp,0o644)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def apply(user,add_units,source):
    backups=Path(tempfile.mkdtemp(
        prefix="admin-v2-signed-sync-",dir="/var/backups/epimediahub"))
    backups.chmod(0o700)
    for name in SOURCES:
        target=BASE/name
        if target.exists():
            shutil.copy2(target,backups/name)
            os.chmod(backups/name,0o600)
    for name,payload in source.items():
        if not (BASE/name).exists() or git_sha((BASE/name).read_bytes())!=SOURCES[name][0]:
            install_module(BASE/name,payload)
    if add_units:
        for ext,text_value in (("service",service_unit(user)),
                               ("timer",timer_unit())):
            path=UNIT_DIR/(NAME+"."+ext)
            with path.open("x",encoding="utf-8") as dest:
                dest.write(text_value)
            path.chmod(0o644)
        cmd("systemctl","daemon-reload")
    cmd("systemctl","enable","--now",NAME+".timer",timeout=30)
    # Execute once with exactly the existing private service identity.
    result=subprocess.run([
        "runuser","-u",user,"--",str(BASE/".venv/bin/python"),
        str(BASE/"sync_private_updates.py")],
        env={"PATH":"/usr/bin:/bin",
             "EPIMEDIAHUB_DATA_DIR":"/var/lib/epimediahub",
             "PYTHONDONTWRITEBYTECODE":"1"},
        capture_output=True,text=True,timeout=100,check=False)
    if result.returncode:
        print("PRIVATE_SIGNED_UPDATE_SYNC_NEEDS_REVIEW")
        print("CODE_BACKUP="+str(backups))
        raise Stop("private artifact download or publication failed")
    try:
        status=json.loads(result.stdout)
    except (ValueError,TypeError):
        raise Stop("unrecognized private updater response") from None
    if status.get("status") not in (
            "ADMIN_SIGNED_ARTIFACT_PUBLISHED",
            "ADMIN_ALREADY_AT_OR_ABOVE_ARTIFACT",
            "NO_NEW_SIGNED_ADMIN_ARTIFACT"):
        raise Stop("unexpected private updater result")
    print("PRIVATE_ADMIN_UPDATER_TIMER_ACTIVE")
    print("PRIVATE_SIGNED_RELEASE_STATUS="+status["status"])
    if "version_code" in status:
        print("VERSION_CODE="+str(status["version_code"]))
    print("CODE_BACKUP="+str(backups))
    print("NO_CUSTOMER_OR_PLAYER_APP_CHANGES")


def main():
    cli=argparse.ArgumentParser()
    mode=cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check",action="store_true",
        help="Read-only host and GitHub pinned-source validation")
    mode.add_argument("--apply",action="store_true",
        help="Install private signed release sync after preflight")
    options=cli.parse_args()
    print("PRIVATE_ADMIN_RELEASE_PREFLIGHT_START")
    user,create_units=check()
    print("RELEASE_PREFLIGHT=HOST_OK")
    source=download_verified()
    print("RELEASE_PREFLIGHT=PINNED_SOURCES_OK")
    print("RELEASE_SYNC_UNITS="+("TO_CREATE" if create_units else "PRESENT"))
    if options.check:
        print("RELEASE_PREFLIGHT_READ_ONLY_OK")
        print("NO_FILES_OR_SERVICES_CHANGED")
        return
    apply(user,create_units,source)


if __name__=="__main__":
    try:main()
    except Stop as error:
        # Stop messages are fixed, developer-authored categories only.
        print("PRIVATE_ADMIN_RELEASE_HANDOFF_STOPPED",file=sys.stderr)
        print("RELEASE_STAGE_REASON="+str(error),file=sys.stderr)
        sys.exit(2)
    except Exception as error:
        # Never print raw urllib, token, hostname or subprocess errors.
        print("PRIVATE_ADMIN_RELEASE_HANDOFF_STOPPED",file=sys.stderr)
        print("RELEASE_STAGE_REASON=unexpected_"+type(error).__name__,
              file=sys.stderr)
        sys.exit(2)
