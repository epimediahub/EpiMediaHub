"""Guarded native Admin grants that delegate to existing audited business handlers.

No duplicated grant SQL: the existing Flask license/VPN handlers are the single
authority for eligibility, idempotence, transaction logic and audit records.

This module only:
- reads existing entitlement state without writing it,
- requires the caller to authenticate + provide CSRF in mobile_flask,
- invokes the existing registered handler for the same device id,
- verifies the resulting database entitlement became active.

A redirect or flash from a legacy handler alone is NEVER interpreted as success.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import sqlite3
import stat
import time
import uuid
from flask import current_app
from native_management_data import SchemaUnavailable

HANDLERS={
    "grant-year":("admin_grant_year","annual_device_licenses"),
    "vpn-trial7":("grant_trial_auto","vpn_trial_authorizations")
}

def valid_confirmation(data):
    if not isinstance(data,dict) or set(data)!={"confirm","request_id"}:
        return False
    if data.get("confirm") is not True:
        return False
    rid=data.get("request_id")
    if not isinstance(rid,str) or len(rid)>50:
        return False
    try:
        return str(uuid.UUID(rid))==rid
    except (ValueError,TypeError):
        return False

def _date_active(value):
    if not isinstance(value,str) or not value:
        return False
    try:
        instant=datetime.fromisoformat(value.replace("Z","+00:00"))
        if instant.tzinfo is None:
            return False
        return instant.astimezone(timezone.utc)>datetime.now(timezone.utc)
    except (TypeError,ValueError,OverflowError):
        return False

def current_entitlement(path,device_row_id,action):
    if (action not in HANDLERS or
        not isinstance(device_row_id,int) or not 0<device_row_id<2**63):
        raise ValueError("invalid native grant request")
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise SchemaUnavailable("database unavailable")
    con=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=5)
    try:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")
        row=con.execute("SELECT device_id,enabled FROM devices WHERE id=?",
                        (device_row_id,)).fetchone()
        if row is None or row[1]!=1 or not row[0]:
            raise SchemaUnavailable("device not eligible for native grants")
        if action=="grant-year":
            values=con.execute("""
                SELECT expires_at FROM annual_device_licenses
                WHERE device_id=? AND revoked_at IS NULL
                ORDER BY granted_at DESC LIMIT 1
            """,(row[0],)).fetchall()
        else:
            values=con.execute("""
                SELECT expires_at FROM vpn_trial_authorizations
                WHERE device_row_id=?
                ORDER BY granted_at DESC LIMIT 1
            """,(device_row_id,)).fetchall()
        return any(_date_active(item[0]) for item in values)
    finally:
        con.close()

@contextmanager
def _device_lock(path, device_row_id, action):
    """Cross-worker serialization around the ORIGINAL handler and verification.

    SQLite transactions inside the existing handler cannot be nested in our
    connection. An OS file lock serializes requests for the same device/action
    on the single provisioning host, including separate Flask workers.
    """
    root=Path(path).parent/"admin-mobile"
    folder=root/"native-grant-locks"
    for candidate in (root,folder):
        if candidate.is_symlink():
            raise SchemaUnavailable("unsafe native grant lock directory")
        candidate.mkdir(mode=0o700,parents=True,exist_ok=True)
        info=candidate.stat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077
                or info.st_uid!=os.geteuid()):
            raise SchemaUnavailable("native grant lock directory is not private")
    flags=os.O_CREAT|os.O_RDWR
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    descriptor=os.open(folder/f"{device_row_id}-{action}.lock",flags,0o600)
    acquired=False
    try:
        info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid():
            raise SchemaUnavailable("unsafe native grant lock")
        os.fchmod(descriptor,0o600)
        deadline=time.monotonic()+8
        while not acquired:
            try:
                fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
                acquired=True
            except BlockingIOError:
                if time.monotonic()>=deadline:
                    raise SchemaUnavailable("native grant already in progress")
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            fcntl.flock(descriptor,fcntl.LOCK_UN)
        os.close(descriptor)

def invoke_grant(path,device_row_id,action):
    if action not in HANDLERS:
        raise ValueError("unsupported action")
    handler_name,_=HANDLERS[action]
    handler=current_app.view_functions.get(handler_name)
    if not callable(handler):
        raise SchemaUnavailable("original audited business action missing")
    # The eligibility check, real handler and post-condition must be one
    # serialized unit. Otherwise two concurrent POSTs can both see 'inactive'.
    with _device_lock(path,device_row_id,action):
        if current_entitlement(path,device_row_id,action):
            return {"applied":False,"error":"already_active"},409
        # Call the REAL business implementation. It owns all its original guards,
        # provider readiness checks, license transactions, and audit history.
        handler(device_row_id)
        if current_entitlement(path,device_row_id,action):
            return {"applied":True,"action":action},200
        return {"applied":False,"error":"not_applied"},409
