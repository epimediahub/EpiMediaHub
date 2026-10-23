"""FCM HTTP v1 transport for the private EpiMediaHub Admin app.

Only a backend with a Google service-account identity may send messages.
FCM private credentials NEVER enter this repository or the Android APK.
Network failures leave incidents open and must not be reported as delivered.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

PROJECT_VAR="EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID"
ALLOWED_KINDS=frozenset((
    "analysis_stalled","playlist_access","worker_preflight","service_down",
    "build_failed","playback_errors","daily_report",
    "expiry_monthly","expiry_weekly","push_test",
))


def enabled() -> bool:
    return bool(os.getenv(PROJECT_VAR, "").strip())


def _access_token():
    # google-auth is installed ONLY on the protected production backend,
    # never in the private Android app. ADC uses a private service account.
    import google.auth
    from google.auth.transport.requests import Request
    credentials,_=google.auth.default(
        scopes=["https://www.googleapis.com/auth/firebase.messaging"])
    credentials.refresh(Request())
    if not credentials.token:
        raise RuntimeError("FCM server credentials unavailable")
    return credentials.token


def make_payload(fcm_token: str, kind: str) -> dict:
    if kind not in ALLOWED_KINDS:
        raise ValueError("Unknown admin alert")
    # Only the generic category is transmitted, never free-text incidents or
    # customer/playlist/device identifiers. This can be safely shown on lock.
    return {
        "message":{
            "token":fcm_token,
            "data":{"kind":kind},
            "android":{"priority":"high"},
        }
    }


def send(fcm_token: str, kind: str) -> bool:
    project=os.getenv(PROJECT_VAR, "").strip()
    if not project or not project.replace("-","").isalnum():
        raise RuntimeError("FCM project not configured")
    bearer=_access_token()
    data=json.dumps(make_payload(fcm_token,kind),
                    separators=(",",":"),ensure_ascii=True).encode()
    request=urllib.request.Request(
        "https://fcm.googleapis.com/v1/projects/"+project+"/messages:send",
        data=data,method="POST",
        headers={"Authorization":"Bearer "+bearer,
                 "Content-Type":"application/json;charset=UTF-8"},
    )
    try:
        with urllib.request.urlopen(request,timeout=8) as response:
            return response.status==200
    except (urllib.error.URLError,OSError):
        # Do not log exception: some HTTP clients include the token URL or
        # sensitive bearer values in error strings.
        return False
