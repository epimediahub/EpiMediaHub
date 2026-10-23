#!/usr/bin/env python3
"""Private, non-delivering FCM HTTP v1 validation against one opted-in admin device.

Run as root on actual dashboard host using the installed provisioning venv.
Reads the daemon's two FCM environment variables and drops permanently to its
non-root service identity. Never prints token, project ID, service account
address/private key, API responses, credentials, or OAuth exception strings.
Does not modify code, DB, systemd or release files.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import pwd
import re
import sqlite3
import stat
import subprocess
import sys
import urllib.error
import urllib.request

BASE=Path("/opt/epimediahub/provisioning")
DATA=Path("/var/lib/epimediahub/admin-mobile/registrations.sqlite3")
SERVICE="epimediahub-provisioning.service"
SCOPED_ENV={"EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID","GOOGLE_APPLICATION_CREDENTIALS"}
SAFE_GOOGLE_STATUSES={
    "INVALID_ARGUMENT","UNAUTHENTICATED","PERMISSION_DENIED","NOT_FOUND",
    "RESOURCE_EXHAUSTED","FAILED_PRECONDITION","UNAVAILABLE","INTERNAL",
    "UNKNOWN","DEADLINE_EXCEEDED"
}
SAFE_FCM_CODES={
    "SENDER_ID_MISMATCH","UNREGISTERED","THIRD_PARTY_AUTH_ERROR",
    "QUOTA_EXCEEDED","INVALID_ARGUMENT","UNAVAILABLE",
    "INTERNAL","NOT_FOUND","PERMISSION_DENIED"
}
SAFE_GOOGLE_REASONS={
    "SERVICE_DISABLED","ACCESS_TOKEN_SCOPE_INSUFFICIENT",
    "IAM_PERMISSION_DENIED","API_KEY_INVALID","CONSUMER_INVALID",
    "SERVICE_USAGE_DENIED","SECURITY_POLICY_VIOLATED",
    "BILLING_DISABLED","RESOURCE_PROJECT_INVALID"
}

class Stop(Exception):
    pass

def system_value(field):
    result=subprocess.run(
        ["systemctl","show",SERVICE,"-p",field,"--value"],
        capture_output=True,text=True,timeout=8,check=False)
    if result.returncode:
        raise Stop("DASHBOARD_SERVICE_QUERY_FAILED")
    return result.stdout.strip()

def service_environment():
    pid=system_value("MainPID")
    username=system_value("User")
    if not pid.isdecimal() or int(pid)<=1 or not username or username=="root":
        raise Stop("DASHBOARD_NOT_RUNNING_AS_EXPECTED_USER")
    account=pwd.getpwnam(username)
    process=Path("/proc")/pid/"environ"
    values={}
    for part in process.read_bytes().split(b"\0"):
        if b"=" not in part:
            continue
        key,val=part.split(b"=",1)
        if key in {x.encode() for x in SCOPED_ENV}:
            values[key.decode()]=val.decode("utf-8","strict")
    return account,values

def validate_server_identity(account,env):
    project=env.get("EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID","")
    credential=env.get("GOOGLE_APPLICATION_CREDENTIALS","")
    if not re.fullmatch(r"[A-Za-z0-9_-]{5,120}",project):
        raise Stop("FCM_PROJECT_ENV_MISSING_OR_INVALID")
    if not credential or len(credential)>512:
        raise Stop("GOOGLE_APPLICATION_CREDENTIALS_NOT_SET")
    path=Path(credential)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise Stop("SERVICE_ACCOUNT_FILE_MISSING")
    metadata=path.stat()
    if metadata.st_uid!=account.pw_uid or stat.S_IMODE(metadata.st_mode)&0o077:
        raise Stop("SERVICE_ACCOUNT_OWNER_OR_PERMISSIONS_INVALID")
    if metadata.st_size>25000 or metadata.st_size<400:
        raise Stop("SERVICE_ACCOUNT_UNEXPECTED_FILE_SIZE")
    # Keys stay in memory only, and none are echoed.
    with path.open(encoding="utf-8") as source:
        obj=json.load(source)
    if not isinstance(obj,dict) or obj.get("type")!="service_account" or not obj.get("private_key"):
        raise Stop("SERVICE_ACCOUNT_NOT_VALID")
    return project,credential, bool(obj.get("project_id")==project)

def safe_fcm_error(response_bytes):
    """Only copy enum-shaped, whitelisted fields from untrusted Google JSON."""
    try:
        obj=json.loads(response_bytes[:8192])
    except (ValueError,TypeError,UnicodeError):
        return dict(fcm_status="UNKNOWN",fcm_code="UNKNOWN",google_reason="UNKNOWN")
    e=obj.get("error") if isinstance(obj,dict) else None
    if not isinstance(e,dict):
        return dict(fcm_status="UNKNOWN",fcm_code="UNKNOWN",google_reason="UNKNOWN")
    st=e.get("status","")
    status=st if st in SAFE_GOOGLE_STATUSES else "UNKNOWN"
    fcm="UNKNOWN"
    reason="UNKNOWN"
    details=e.get("details",[])
    if isinstance(details,list):
        for item in details[:12]:
            if not isinstance(item,dict):continue
            typ=item.get("@type","")
            if typ=="type.googleapis.com/google.firebase.fcm.v1.FcmError":
                raw=item.get("errorCode")
                if isinstance(raw,str) and raw in SAFE_FCM_CODES:
                    fcm=raw
            if typ=="type.googleapis.com/google.rpc.ErrorInfo":
                raw=item.get("reason")
                if isinstance(raw,str) and raw in SAFE_GOOGLE_REASONS:
                    reason=raw
    return dict(fcm_status=status,fcm_code=fcm,google_reason=reason)

def opted_in_admin_token():
    if DATA.is_symlink() or not DATA.is_file():
        raise Stop("PRIVATE_DEVICE_REGISTRY_MISSING")
    if DATA.stat().st_mode & 0o077:
        raise Stop("PRIVATE_DEVICE_REGISTRY_NOT_PRIVATE")
    with sqlite3.connect(DATA.resolve().as_uri()+"?mode=ro",uri=True,timeout=8) as db:
        db.execute("PRAGMA query_only=ON")
        rows=db.execute(
            "SELECT fcm_token FROM admin_mobile_devices WHERE enabled=1 LIMIT 2").fetchall()
    if len(rows)!=1 or not isinstance(rows[0][0],str) or not 80<=len(rows[0][0])<=4096:
        raise Stop("EXPECTED_EXACTLY_ONE_REGISTERED_ADMIN_DEVICE")
    return rows[0][0]

def perform():
    if os.geteuid()!=0 or BASE.is_symlink() or not BASE.is_dir():
        raise Stop("EXPECTED_ROOT_DASHBOARD_HOST")
    if sys.prefix!=str(BASE/".venv") and not Path(sys.executable).resolve().is_relative_to(
            (BASE/".venv").resolve()):
        raise Stop("RUN_USING_PROVISIONING_PYTHON")
    account,env=service_environment()
    project,credentials,matches=validate_server_identity(account,env)
    os.environ.update(env)
    os.environ["HOME"]=account.pw_dir
    os.setgroups([])
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
    os.umask(0o077)

    token=opted_in_admin_token()
    print("FCM_VALIDATE_ONLY: START")
    print("SERVICE_ACCOUNT_PROJECT_MATCHES_TARGET:",matches)
    print("TARGETS_ONE_OPTED_IN_ADMIN_DEVICE: true")
    try:
        import fcm_sender
        bearer=fcm_sender._access_token()
    except Exception as exc:
        cls=type(exc).__name__
        allowed={"DefaultCredentialsError","RefreshError","TransportError",
                 "ImportError","ModuleNotFoundError"}
        print("OAUTH_REFRESH: FAILED")
        print("OAUTH_FAILURE_CLASS:",cls if cls in allowed else "UNCLASSIFIED")
        return
    print("OAUTH_REFRESH: OK")
    payload=fcm_sender.make_payload(token,"push_test")
    # Google's validate_only checks sender, IAM, payload and registration
    # without sending a notification to the phone.
    payload["validate_only"]=True
    body=json.dumps(payload,separators=(",",":")).encode("utf-8")
    request=urllib.request.Request(
        "https://fcm.googleapis.com/v1/projects/"+project+"/messages:send",
        data=body,method="POST",
        headers={"Authorization":"Bearer "+bearer,
                 "Content-Type":"application/json;charset=UTF-8"}
    )
    try:
        with urllib.request.urlopen(request,timeout=12) as response:
            print("FCM_HTTP:",response.status)
            print("FCM_VALIDATE_ONLY_RESULT:",
                  "ACCEPTED" if response.status==200 else "UNEXPECTED_HTTP_SUCCESS")
    except urllib.error.HTTPError as e:
        print("FCM_HTTP:",e.code)
        classified=safe_fcm_error(e.read(8193))
        print("FCM_ERROR_CATEGORY:",json.dumps(classified,sort_keys=True))
        e.close()
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        typ=type(exc).__name__
        print("FCM_NETWORK_ERROR_CLASS:",typ if typ in
              {"URLError","TimeoutError","ConnectionError","OSError"} else "UNKNOWN")
    print("GOOGLE_REQUEST_DID_NOT_SEND_A_NOTIFICATION: true")
    print("NO_DATABASE_SERVICE_OR_APP_CHANGES: true")

if __name__=="__main__":
    try:
        perform()
    except Stop as exc:
        print("SAFE_STOP:",str(exc))
        raise SystemExit(1)
    except Exception as exc:
        # Reject leakage via stringified google-auth, HTTP or OS exceptions.
        cls=type(exc).__name__
        print("SAFE_STOP: UNEXPECTED_"+(
            cls if cls in {"PermissionError","FileNotFoundError","TimeoutExpired",
                           "OperationalError","KeyError","ValueError","JSONDecodeError"}
            else "CHECK_FAILED"))
        raise SystemExit(1)
