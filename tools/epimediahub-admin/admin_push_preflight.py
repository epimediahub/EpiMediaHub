#!/usr/bin/env python3
"""Read-only EpiMediaHub Admin FCM deployment diagnostics.

Runs only on the dashboard host and does not access credentials contents,
export tokens, call Google/Firebase or alter production services.
"""
from __future__ import annotations
from pathlib import Path
import json
import os
import sqlite3
import stat
import subprocess

ROOT=Path('/opt/epimediahub/provisioning')
DATA=Path('/var/lib/epimediahub/admin-mobile')
DASH='epimediahub-provisioning.service'
TIMER='epimediahub-admin-monitor.timer'

def show(*args):
    try:
        result=subprocess.run(['systemctl',*args],text=True,capture_output=True,timeout=7,
                              check=False)
        return (result.stdout or '').strip() if result.returncode==0 else ''
    except (OSError,subprocess.TimeoutExpired):
        return ''

def running(service):
    return show('is-active',service)=='active'

def service_environment():
    # Only inspect named nonsecret switches and path. Never display raw env values.
    pid=show('show',DASH,'-p','MainPID','--value')
    if not pid.isdigit() or int(pid)<=1:
        return {}
    try:
        raw=(Path('/proc')/pid/'environ').read_bytes()
    except (OSError,ValueError):
        return {}
    permitted={b'EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID',b'GOOGLE_APPLICATION_CREDENTIALS'}
    values={}
    for chunk in raw.split(b'\0'):
        if b'=' not in chunk:continue
        key,value=chunk.split(b'=',1)
        if key in permitted:
            values[key.decode()]=value.decode('utf-8','replace')
    return values

def private_file(name, owner):
    if not name or len(name)>512:return False
    try:
        path=Path(name)
        return (path.is_file() and not path.is_symlink() and
                not(path.stat().st_mode & 0o077) and
                (owner is None or path.stat().st_uid==owner))
    except (ValueError,OSError):
        return False

def active_count():
    db=DATA/'registrations.sqlite3'
    if not db.is_file() or db.is_symlink():
        return None
    try:
        with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True,timeout=4) as con:
            con.execute('PRAGMA query_only=ON')
            return int(con.execute(
                'SELECT COUNT(*) FROM admin_mobile_devices WHERE enabled=1').fetchone()[0])
    except sqlite3.Error:
        return None

def main():
    service_alive=running(DASH)
    env=service_environment() if service_alive else {}
    sender_file=ROOT/'fcm_sender.py'
    endpoint_file=ROOT/'mobile_flask.py'
    sender_present=sender_file.is_file() and not sender_file.is_symlink()
    endpoint_present=endpoint_file.is_file() and not endpoint_file.is_symlink()
    sender_test_code=False
    endpoint_test_code=False
    try:
        if sender_present:
            sender_test_code='"push_test"' in sender_file.read_text(encoding='utf-8')
        if endpoint_present:
            endpoint_test_code='@bp.post("/admin/mobile/test-push")' in endpoint_file.read_text(encoding='utf-8')
    except OSError:
        pass
    userid=show('show',DASH,'-p','User','--value')
    uid=None
    if userid:
        try:
            import pwd
            uid=pwd.getpwnam(userid).pw_uid
        except (KeyError,ValueError):
            pass
    configured=bool(env.get('EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID'))
    keyfile=private_file(env.get('GOOGLE_APPLICATION_CREDENTIALS',''),uid)
    summary={
        'dashboard_active':service_alive,
        'android_registration_endpoint_installed':endpoint_present,
        'push_test_endpoint_installed':endpoint_test_code,
        'fcm_sender_installed':sender_present,
        'fcm_test_kind_installed':sender_test_code,
        'firebase_project_configured_on_dashboard':configured,
        'firebase_server_identity_file_private':keyfile,
        'monitor_timer_active':running(TIMER),
        'registered_admin_devices':active_count(),
        'credentials_or_tokens_output':False,
        'database_or_service_modified':False
    }
    print(json.dumps(summary,sort_keys=True,ensure_ascii=False))
    blockers=[k for k in ('dashboard_active','push_test_endpoint_installed',
                         'fcm_test_kind_installed','firebase_project_configured_on_dashboard',
                         'firebase_server_identity_file_private','monitor_timer_active')
              if not summary[k]]
    if summary['registered_admin_devices'] in (None,0):
        blockers.append('no_verified_registered_admin_device')
    if blockers:
        print('PUSH_BLOCKERS:',','.join(blockers))
    else:
        print('READY_FOR_DEVICE_PUSH_TEST: server prerequisites present; delivery unproven')

if __name__=='__main__':
    main()
