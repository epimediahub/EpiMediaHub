#!/usr/bin/env python3
"""Conservative EpiScene same-host remote endpoint/worker version repair.

Uses only an existing localhost listener, exact verified provenance, no active
remote task, no active analysis runner. Requires explicit --apply, snapshots
old worker code, adds one isolated service override, and restarts ONLY the
remote compute worker. Performs the real client.health() check on localhost;
rolls back all its changes if any check fails.

NEVER edits provisioning/skip_analysis.py, protocol, client, DB, markers,
learning, Smart Priority or the existing systemd unit. Never opens providers.
No secrets, endpoint details or hashes appear in output.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request

PROV=Path("/opt/epimediahub/provisioning")
WORKER=Path("/opt/epimediahub/analysis")
API_SRC=PROV/"skip_analysis.py"
REMOTE_SRC=WORKER/"skip_analysis.py"
PYTHON=PROV/".venv/bin/python"
WORKER_UNIT="epimediahub-analysis-worker.service"
RUNNER_UNIT="epimediahub-skip-analysis.service"
TIMER_UNIT="epimediahub-skip-analysis.timer"
DROPIN=Path("/etc/systemd/system/epimediahub-skip-analysis.service.d/95-episcene-local-remote.conf")
ENV_CONTENT="[Service]\nEnvironment=\"SKIP_ANALYSIS_REMOTE_URL=http://127.0.0.1:8790\"\n"
LOCAL_URL="http://127.0.0.1:8790/health"
EXPECTED_PORT=8790
DEFAULT_TIMEOUT=15
REPORT_MODE="EPISCENE_GUARDED_LOCAL_WORKER_REPAIR"

class Stop(Exception):pass

def cmd(*args, timeout=DEFAULT_TIMEOUT, env=None):
    try:
        p=subprocess.run(list(args),capture_output=True,text=True,
                         timeout=timeout,env=env,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise Stop("PROCESS_OR_SYSTEMD_UNAVAILABLE") from exc
    if p.returncode!=0:
        raise Stop("SYSTEMD_OR_PROCESS_COMMAND_FAILED")
    return p.stdout.strip()

def active(unit):
    try: return cmd("systemctl","is-active","--",unit)=="active"
    except Stop:return False

def status(unit):
    try:return cmd("systemctl","show","--property=ActiveState","--value","--",unit)
    except Stop:return "unknown"

def source_sha(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>2_000_000:
        raise Stop("SOURCE_FILE_UNAVAILABLE_OR_SYMLINK")
    return hashlib.sha256(path.read_bytes()).hexdigest()

def local_health():
    try:
        with urllib.request.urlopen(LOCAL_URL,timeout=4) as reply:
            if reply.status!=200:raise Stop("LOCAL_WORKER_HEALTH_NON_200")
            raw=reply.read(65537)
        if len(raw)>65536:raise Stop("LOCAL_WORKER_HEALTH_OVERSIZED")
        val=json.loads(raw.decode("utf-8"))
    except (ValueError,UnicodeError,OSError) as exc:
        raise Stop("LOCAL_WORKER_HEALTH_UNAVAILABLE") from exc
    if not isinstance(val,dict) or val.get("status")!="ok" or not isinstance(val.get("versions"),dict):
        raise Stop("LOCAL_WORKER_HEALTH_INVALID")
    return val

def local_context():
    # Minimal import of existing protocol, no config modification.
    import contextlib,importlib
    sys.path.insert(0,str(PROV))
    try:
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            proto=importlib.import_module("skip_remote_protocol")
            return proto.versions(),proto.SERVER_IP,proto.PORT,proto.PROTOCOL
    except Exception as exc:
        raise Stop("PROTOCOL_UNAVAILABLE") from exc

def local_client_health():
    # Set override before import: client may cache its URL at import time.
    script=(
       "import sys;sys.path.insert(0,'/opt/epimediahub/provisioning');"
       "import skip_remote_client as c;"
       "assert c.configured(), 'not configured';"
       "c.health()"
    )
    e=os.environ.copy()
    e["SKIP_ANALYSIS_REMOTE_URL"]="http://127.0.0.1:8790"
    try:
        cmd(str(PYTHON),"-c",script,env=e,timeout=10)
        return True
    except Stop:
        return False

def listener_and_flags():
    # Only trust the already-running worker systemd unit when it uses loopback.
    raw=cmd("systemctl","show","--property=ExecStart","--value","--",WORKER_UNIT)
    if "skip_remote_worker" not in raw:
        raise Stop("WORKER_SERVICE_ENTRYPOINT_UNEXPECTED")
    if not re.search(r"--bind(?:=|\s+)127\.0\.0\.1(?:\s|;|$)",raw):
        raise Stop("WORKER_SERVICE_BIND_IS_NOT_LOCAL")
    if not re.search(r"--peer(?:=|\s+)127\.0\.0\.1(?:\s|;|$)",raw):
        raise Stop("WORKER_SERVICE_PEER_IS_NOT_LOCAL")
    sockets=cmd("ss","-H","-lntp","sport = :8790")
    if "127.0.0.1:8790" not in sockets:
        raise Stop("EXPECTED_LOCAL_LISTENER_MISSING")

def marker_code_contract():
    # Last verified local deployed customer-marker fix hash. If API source
    # changed, cannot safely transplant its code into compute worker.
    EXPECTED_API="10b8537eb3df3b3a4744959e51150b86046f26c8aa625a4bdf4ac9331c3cea5b"
    if source_sha(API_SRC)!=EXPECTED_API:
        raise Stop("LIVE_API_CHANGED_FROM_REVIEWED_VERSION")

def guard():
    if os.geteuid()!=0:raise Stop("ROOT_REQUIRED")
    if PROV.is_symlink() or WORKER.is_symlink():
        raise Stop("SOURCE_TREE_SYMLINK_UNEXPECTED")
    if DROPIN.exists() or DROPIN.is_symlink():
        raise Stop("EXISTING_OVERRIDE_REQUIRES_MANUAL_REVIEW")
    if not active(WORKER_UNIT) or not active(TIMER_UNIT):
        raise Stop("EXISTING_SERVICES_NOT_READY")
    if status(RUNNER_UNIT) in ("active","activating","deactivating"):
        raise Stop("RUNNING_ANALYSIS_JOB_BLOCKS_REPAIR")
    if not PYTHON.is_file():raise Stop("PYTHON_INTERPRETER_MISSING")
    listener_and_flags()
    marker_code_contract()
    local=local_health()
    vers,peer,port,protocol=local_context()
    if port!=EXPECTED_PORT or local.get("protocol")!=protocol:
        raise Stop("PROTOCOL_OR_PORT_MISMATCH")
    remotevers=local["versions"]
    if len(vers)!=13 or set(remotevers)!=set(vers):
        raise Stop("WORKER_SCHEMA_VERSION_COUNT_MISMATCH")
    drift=[k for k in vers if vers.get(k)!=remotevers.get(k)]
    if drift!=["skip_analysis.py"]:
        raise Stop("MORE_THAN_ONE_COMPONENT_MISMATCH")
    if len(source_sha(API_SRC))!=64:
        raise Stop("API_FILE_HASH_UNAVAILABLE")
    if source_sha(REMOTE_SRC)!=remotevers["skip_analysis.py"]:
        raise Stop("REMOTE_INSTALLED_FILE_NOT_SAME_AS_RUNNING_WORKER")
    if source_sha(API_SRC)!=vers["skip_analysis.py"]:
        raise Stop("API_FILE_NOT_SAME_AS_PROTOCOL_VERSION")
    if bool(local.get("active")) or local.get("active_count",0) not in (None,0):
        raise Stop("WORKER_BUSY")
    # The configured IP is local to this host, but client must use loopback
    # because worker has --bind 127.0.0.1. Do NOT expose 8790 externally.
    if not isinstance(peer,str) or peer=="127.0.0.1":
        raise Stop("NO_HOST_BIND_MISMATCH")
    if "SKIP_ANALYSIS_REMOTE_URL" not in (PROV/"skip_remote_client.py").read_text("utf-8"):
        raise Stop("CLIENT_OVERRIDE_NOT_SUPPORTED")
    return {"worker_active":True,"analysis_runner_idle":True,
            "analysis_timer_active":True,
            "version_component_count":len(vers),"version_drift":["skip_analysis.py"],
            "worker_has_active_task":False,
            "bind_and_peer_loopback":True,
            "api_fix_preserved":True,
            "changes_made":0}

def restart_worker_and_wait(match_local=False):
    cmd("systemctl","restart","--",WORKER_UNIT,timeout=25)
    for _ in range(10):
        time.sleep(1)
        if not active(WORKER_UNIT):continue
        try: h=local_health()
        except Stop:continue
        if match_local:
            versions,*_=local_context()
            if h["versions"]!=versions:continue
        return True
    return False

def atomic_copy(origin,destination):
    if destination.is_symlink() or not destination.is_file():
        raise Stop("WORKER_CODE_DESTINATION_UNTRUSTED")
    old=destination.stat()
    if not stat.S_ISREG(old.st_mode):raise Stop("WORKER_CODE_NOT_REGULAR")
    fd,tmp=tempfile.mkstemp(dir=destination.parent,prefix=".episcene-swap-")
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(origin.read_bytes())
            out.flush()
            os.fsync(out.fileno())
        os.chown(tmp,old.st_uid,old.st_gid)
        os.chmod(tmp,stat.S_IMODE(old.st_mode))
        os.replace(tmp,destination)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def apply():
    state=guard()
    if not DROPIN.parent.is_dir() or DROPIN.parent.is_symlink():
        # We may safely create a new systemd dropin directory later,
        # but never replace an existing arbitrary symlink.
        if DROPIN.parent.exists():raise Stop("SERVICE_OVERRIDE_DIRECTORY_UNTRUSTED")
    timer_was_active=True
    backup=Path(tempfile.mkdtemp(prefix="episcene-remote-safety-",dir="/root"))
    backup.chmod(0o700)
    saved=backup/"skip_analysis.remote.before.py"
    shutil.copy2(REMOTE_SRC,saved)
    made_override=False
    changed_file=False
    timer_stopped=False
    try:
        cmd("systemctl","stop","--",TIMER_UNIT)
        timer_stopped=True
        if status(RUNNER_UNIT) in ("active","activating","deactivating"):
            raise Stop("ANALYSIS_BECAME_ACTIVE_ABORT")
        # Recheck worker idle before changing its import tree.
        h=local_health()
        if h.get("active") or h.get("active_count",0) not in (0,None):
            raise Stop("COMPUTE_WORK_BECAME_ACTIVE_ABORT")
        atomic_copy(API_SRC,REMOTE_SRC)
        changed_file=True
        if not restart_worker_and_wait(match_local=True):
            raise Stop("RESTARTED_WORKER_HEALTH_OR_VERSION_MISMATCH")
        # Only one single-file drop-in; no change to original unit.
        DROPIN.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
        if DROPIN.parent.is_symlink() or DROPIN.exists() or DROPIN.is_symlink():
            raise Stop("OVERRIDE_PATH_BECAME_UNTRUSTED")
        fd=os.open(DROPIN,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o644)
        with os.fdopen(fd,"w",encoding="utf-8") as out:
            out.write(ENV_CONTENT)
        made_override=True
        cmd("systemctl","daemon-reload")
        if not local_client_health():
            raise Stop("REAL_CLIENT_HEALTH_CHECK_FAILED")
        cmd("systemctl","start","--",TIMER_UNIT)
        if not active(TIMER_UNIT):
            raise Stop("ANALYSIS_TIMER_NOT_RESTORED")
        return {"mode":REPORT_MODE,"applied":True,"verified":True,
                "worker_versions_match":13,"client_health_via_loopback":True,
                "analysis_timer_active":True,"analysis_worker_active":True,
                "backup_created":True,"worker_restarted":True,
                "analysis_runner_restarted":False,"other_services_restarted":False,
                "provider_requests":0,"marker_db_writes":0,
                "worker_connection_exposed_to_network":False}
    except (Stop,OSError) as exc:
        restored=True
        try:
            if made_override and DROPIN.is_file() and not DROPIN.is_symlink():
                DROPIN.unlink()
                cmd("systemctl","daemon-reload")
            if changed_file:
                atomic_copy(saved,REMOTE_SRC)
                if not restart_worker_and_wait(match_local=False):restored=False
            if timer_stopped and timer_was_active:
                cmd("systemctl","start","--",TIMER_UNIT)
                if not active(TIMER_UNIT):restored=False
        except (Stop,OSError):
            restored=False
        return {"mode":REPORT_MODE,"applied":False,
                "failure_reason":str(exc) if isinstance(exc,Stop) else "IO_OR_SYSTEMD_ERROR",
                "rollback_restored":restored,
                "backup_created":saved.is_file(),
                "analysis_runner_restarted":False,
                "provider_requests":0,"marker_db_writes":0}

def verify():
    if not DROPIN.is_file() or DROPIN.is_symlink() or DROPIN.read_text("utf-8")!=ENV_CONTENT:
        raise Stop("RUNNER_LOCAL_OVERRIDE_MISSING_OR_DRIFTED")
    if not active(WORKER_UNIT) or not active(TIMER_UNIT):
        raise Stop("SERVICE_NOT_ACTIVE")
    if source_sha(REMOTE_SRC)!=source_sha(API_SRC):
        raise Stop("API_REMOTE_SOURCE_STILL_DIFFERENT")
    if local_health()["versions"]!=local_context()[0]:
        raise Stop("PROTOCOL_VERSION_DRIFT")
    if not local_client_health():
        raise Stop("LOCAL_CLIENT_HEALTH_FAILED")
    return {"mode":REPORT_MODE,"verified":True,"all_13_versions_match":True,
            "local_worker_health":True,"analysis_timer_active":True,
            "provider_requests":0,"marker_db_writes":0}

def main():
    parser=argparse.ArgumentParser()
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--check",action="store_true")
    choice.add_argument("--apply",action="store_true")
    choice.add_argument("--verify",action="store_true")
    args=parser.parse_args()
    try:
        value=guard() if args.check else apply() if args.apply else verify()
    except (Stop,OSError,ValueError,UnicodeError,PermissionError) as exc:
        value={"mode":REPORT_MODE,"status":"STOP_NO_FURTHER_CHANGES",
               "reason":str(exc) if isinstance(exc,Stop) else "UNEXPECTED_PRECHECK_FAILURE",
               "provider_requests":0,"marker_db_writes":0}
        print(json.dumps(value,sort_keys=True,indent=2))
        return 2
    print(json.dumps(value,sort_keys=True,indent=2))
    return 0 if not args.apply or value.get("applied") else 2

if __name__=="__main__":
    sys.exit(main())
