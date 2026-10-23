#!/usr/bin/env python3
"""Secure one-shot diagnosis of EpiMediaHub Admin FCM HTTP v1 sending.

Runs the probe as the provisioning service account with ONLY the relevant
existing environment names, never prints credentials, FCM tokens, URLs or
Google's raw error messages. Reads registry read-only. Sends one generic
push_test to one opted-in administrator only; no customer/playlist data,
no new registration, no database mutation, no service restarts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import shutil
import re
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request

PROVISIONING=Path("/opt/epimediahub/provisioning")
DB=Path("/var/lib/epimediahub/admin-mobile/registrations.sqlite3")
SVC="epimediahub-provisioning.service"
ENV_NAMES=("EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID","GOOGLE_APPLICATION_CREDENTIALS",
           "EPIMEDIAHUB_DATA_DIR")
STATUSES={"ABORTED","ALREADY_EXISTS","CANCELLED","DATA_LOSS","DEADLINE_EXCEEDED",
          "FAILED_PRECONDITION","INTERNAL","INVALID_ARGUMENT","NOT_FOUND",
          "OUT_OF_RANGE","PERMISSION_DENIED","RESOURCE_EXHAUSTED",
          "UNAUTHENTICATED","UNAVAILABLE","UNIMPLEMENTED","UNKNOWN"}
FCM_CODES={"UNREGISTERED","SENDER_ID_MISMATCH","INVALID_ARGUMENT",
           "THIRD_PARTY_AUTH_ERROR","QUOTA_EXCEEDED","UNAVAILABLE","INTERNAL",
           "APNS_AUTH_ERROR","UNSPECIFIED_ERROR"}
GOOGLE_REASONS={"SERVICE_DISABLED","API_DISABLED","ACCESS_TOKEN_SCOPE_INSUFFICIENT",
                "IAM_PERMISSION_DENIED","CONSUMER_INVALID","USER_PROJECT_DENIED",
                "SERVICE_USAGE_DENIED","PERMISSION_DENIED"}
FIELDS=("http_status","google_status","fcm_error","google_reason")

def category(payload):
    """Parse only explicitly whitelisted Google error enums; discard messages."""
    result={k:"NOT_REPORTED" for k in FIELDS[1:]}
    if not isinstance(payload,dict):
        return result
    detail=payload.get("error")
    if not isinstance(detail,dict):
        return result
    status=detail.get("status")
    if type(status) is str and status in STATUSES:
        result["google_status"]=status
    entries=detail.get("details")
    if isinstance(entries,list):
        for entry in entries[:12]:
            if not isinstance(entry,dict):
                continue
            typename=entry.get("@type")
            if typename=="type.googleapis.com/google.firebase.fcm.v1.FcmError":
                code=entry.get("errorCode")
                if type(code) is str and code in FCM_CODES:
                    result["fcm_error"]=code
            if typename=="type.googleapis.com/google.rpc.ErrorInfo":
                reason=entry.get("reason")
                if type(reason) is str and reason in GOOGLE_REASONS:
                    result["google_reason"]=reason
    return result

def classify_exception(error):
    """No repr or exception message; they may contain a private URL."""
    name=type(error).__name__
    if isinstance(error,ModuleNotFoundError):
        return "GOOGLE_AUTH_DEPENDENCY_MISSING" if getattr(error,"name","").startswith(
            ("google","requests","cachecontrol")) else "PYTHON_MODULE_MISSING"
    if isinstance(error,ImportError):
        return "GOOGLE_AUTH_IMPORT_FAILED"
    if isinstance(error,FileNotFoundError):
        return "SERVICE_ACCOUNT_FILE_NOT_FOUND"
    if isinstance(error,PermissionError):
        return "SERVICE_ACCOUNT_FILE_NOT_READABLE"
    if isinstance(error,TimeoutError):
        return "GOOGLE_REQUEST_TIMEOUT"
    if isinstance(error,urllib.error.URLError):
        return "GOOGLE_NETWORK_OR_DNS_FAILURE"
    if isinstance(error,OSError):
        return "GOOGLE_NETWORK_OR_CREDENTIAL_IO"
    if name in {"DefaultCredentialsError","RefreshError","TransportError",
                "MalformedError","InvalidValue","InvalidOperation"}:
        return "GOOGLE_AUTH_"+name.upper()
    return "FCM_OTHER_"+re.sub(r"[^A-Z_]","",name.upper())[:40]

def environment_of_service():
    if os.geteuid()!=0 or not PROVISIONING.is_dir() or PROVISIONING.is_symlink():
        raise RuntimeError("STOP_ROOT_AND_PROVISIONING_REQUIRED")
    def systemctl(*args):
        response=subprocess.run(["systemctl",*args],text=True,capture_output=True,
                                timeout=8,check=False)
        return response.stdout.strip() if response.returncode==0 else ""
    if systemctl("is-active",SVC)!="active":
        raise RuntimeError("STOP_ADMIN_DASHBOARD_NOT_ACTIVE")
    name=systemctl("show",SVC,"-p","User","--value")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}",name) or name=="root":
        raise RuntimeError("STOP_INVALID_SERVICE_ACCOUNT")
    account=pwd.getpwnam(name)
    pid=systemctl("show",SVC,"-p","MainPID","--value")
    if not pid.isdigit() or int(pid)<=1:
        raise RuntimeError("STOP_UNAVAILABLE_DASHBOARD_PID")
    raw=(Path("/proc")/pid/"environ").read_bytes()
    found={}
    for item in raw.split(b"\0"):
        if b"=" not in item:
            continue
        key, value=item.split(b"=",1)
        if key.decode("utf-8","replace") in ENV_NAMES:
            found[key.decode()]=value.decode("utf-8","replace")
    project=found.get("EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID","")
    credential=found.get("GOOGLE_APPLICATION_CREDENTIALS","")
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,80}",project):
        raise RuntimeError("STOP_FCM_PROJECT_ID_MISSING_OR_INVALID")
    if not credential or len(credential)>500:
        raise RuntimeError("STOP_GOOGLE_CREDENTIAL_PATH_MISSING")
    credential_path=Path(credential)
    if (credential_path.is_symlink() or not credential_path.is_file() or
        credential_path.stat().st_uid!=account.pw_uid or
        credential_path.stat().st_mode&0o077):
        raise RuntimeError("STOP_SERVER_ACCOUNT_FILE_UNSAFE")
    return name,found

def child():
    sys.path.insert(0,str(PROVISIONING))
    from fcm_sender import make_payload
    project=os.environ.get("EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID","")
    credential=Path(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS","/dev/null"))
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,80}",project):
        raise RuntimeError("STOP_FCM_PROJECT_INVALID_IN_CHILD")
    if not credential.is_file() or credential.is_symlink():
        raise RuntimeError("STOP_SERVICE_ACCOUNT_NOT_READABLE_BY_SERVICE")
    try:
        config=json.loads(credential.read_text(encoding="utf-8"))
    except (ValueError,OSError,UnicodeDecodeError):
        raise RuntimeError("STOP_SERVICE_ACCOUNT_NOT_VALID_JSON") from None
    if not isinstance(config,dict) or config.get("type")!="service_account":
        raise RuntimeError("STOP_NOT_GOOGLE_SERVICE_ACCOUNT")
    credentials_source_project=config.get("project_id","")
    print("SERVER_SERVICE_ACCOUNT_PROJECT_MATCH:",
          credentials_source_project==project,flush=True)
    identity=config.get("client_email","")
    print("SERVER_USES_EPIMEDIAHUB_FCM_ACCOUNT:",
          identity=="epimediahub-admin-fcm@epimediahub-admin.iam.gserviceaccount.com",
          flush=True)
    print("SERVER_USES_FIREBASE_ADMIN_SDK_ACCOUNT:",
          identity=="firebase-adminsdk-fbsvc@epimediahub-admin.iam.gserviceaccount.com",
          flush=True)
    if credentials_source_project!=project:
        print("NOTE: cross-project service accounts require explicit FCM IAM access")
    if DB.is_symlink() or not DB.is_file():
        raise RuntimeError("STOP_PRIVATE_PUSH_REGISTRY_MISSING")
    with sqlite3.connect(DB.resolve().as_uri()+"?mode=ro",uri=True,timeout=10) as db:
        db.execute("PRAGMA query_only=ON")
        records=db.execute("""SELECT fcm_token FROM admin_mobile_devices
                             WHERE enabled=1 LIMIT 2""").fetchall()
    print("REGISTERED_ADMIN_DEVICE_COUNT_BOUND:",
          "ONE" if len(records)==1 else "ZERO" if not records else "MULTIPLE",flush=True)
    if len(records)!=1:
        raise RuntimeError("STOP_EXPECTED_ONE_ADMIN_INSTALLATION_FOR_TEST")
    fcm_token=records[0][0]
    if not isinstance(fcm_token,str) or not re.fullmatch(r"[A-Za-z0-9:_-]{80,4096}",fcm_token):
        raise RuntimeError("STOP_REGISTERED_FCM_TOKEN_UNEXPECTED")
    try:
        from fcm_sender import _access_token
        oauth=_access_token()
        if not oauth:
            raise RuntimeError("STOP_EMPTY_OAUTH_TOKEN")
    except Exception as error:
        print("FCM_AUTH_STAGE:",classify_exception(error),flush=True)
        return 2
    print("FCM_AUTH_STAGE: OAUTH_TOKEN_REFRESH_OK",flush=True)
    request=urllib.request.Request(
        "https://fcm.googleapis.com/v1/projects/"+project+"/messages:send",
        method="POST",
        data=json.dumps(make_payload(fcm_token,"push_test"),
                        separators=(",",":")).encode("utf-8"),
        headers={"Authorization":"Bearer "+oauth,
                 "Content-Type":"application/json;charset=UTF-8"})
    try:
        with urllib.request.urlopen(request,timeout=12) as response:
            status=response.status
            print("FCM_SEND_STATUS: ACCEPTED" if status==200 else
                  "FCM_SEND_STATUS: UNEXPECTED_HTTP_STATUS",flush=True)
            print("FCM_HTTP_STATUS:",status,flush=True)
            return 0 if status==200 else 2
    except urllib.error.HTTPError as error:
        code=error.code
        try:
            raw=error.read(8192)
            detail=json.loads(raw)
        except (ValueError,UnicodeDecodeError,OSError):
            detail={}
        finally:
            error.close()
        print("FCM_SEND_STATUS: REJECTED_BY_GOOGLE",flush=True)
        print("FCM_HTTP_STATUS:",code,flush=True)
        for key,value in category(detail).items():
            print(key.upper()+":",value,flush=True)
        return 3
    except Exception as error:
        print("FCM_SEND_STATUS:",classify_exception(error),flush=True)
        return 4

def main():
    if len(sys.argv)==2 and sys.argv[1]=="--service-probe":
        return child()
    if len(sys.argv)!=1:
        raise RuntimeError("STOP_INVALID_ARGS")
    name,provider_env=environment_of_service()
    allowed_env={"PATH":"/usr/bin:/bin","PYTHONDONTWRITEBYTECODE":"1"}
    allowed_env.update(provider_env)
    venv=PROVISIONING/".venv/bin/python"
    if not venv.is_file():
        raise RuntimeError("STOP_BACKEND_PYTHON_NOT_FOUND")
    runuser=shutil.which("runuser") or "/usr/sbin/runuser"
    run=subprocess.run(
        [runuser,"-u",name,"--",str(venv),str(Path(__file__).resolve()),
         "--service-probe"],
        cwd=str(PROVISIONING),capture_output=True,text=True,timeout=60,
        env=allowed_env,check=False)
    # Child prints only categories; never echo raw stderr, even on failure.
    if run.stdout:
        safe_lines=run.stdout.splitlines()
        allowed_prefix=("SERVER_SERVICE_ACCOUNT_PROJECT_MATCH:",
                        "NOTE: cross-project","REGISTERED_ADMIN_DEVICE_COUNT_BOUND:",
                        "FCM_AUTH_STAGE:","FCM_SEND_STATUS:","FCM_HTTP_STATUS:",
                        "GOOGLE_STATUS:","FCM_ERROR:","GOOGLE_REASON:",
                        "SAFE_STOP:")
        for line in safe_lines[:24]:
            if line.startswith(allowed_prefix) and len(line)<190:
                print(line)
    if run.returncode not in (0,2,3,4):
        print("SAFE_STOP: SERVICE_PROBE_PROCESS_FAILED")
    print("NO_FCM_TOKEN_OR_CREDENTIAL_DISCLOSED")
    print("NO_DATABASE_CHANGES_OR_DASHBOARD_RESTART")
    return run.returncode

if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as error:
        reason=str(error)
        print("SAFE_STOP:",reason if isinstance(error,RuntimeError) and
              reason.startswith("STOP_") else
              "UNEXPECTED_"+type(error).__name__)
        sys.exit(5)
