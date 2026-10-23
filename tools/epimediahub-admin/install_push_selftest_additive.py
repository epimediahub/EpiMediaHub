#!/usr/bin/env python3
"""Guarded, additive deployment of EpiMediaHub Admin push self-test.

Only modifies the existing admin mobile Flask API, private device registry and
FCM kind allowlist. Refuses unexpected local sources. Keeps backups and
automatically rolls back if syntax, service restart, or health probe fails.

No APK, Fire TV, customer, reseller, IPTV, EpiScene worker or VPN change.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

BASE = Path("/opt/epimediahub/provisioning")
BACKUP_ROOT = Path("/var/backups/epimediahub")
SERVICE = "epimediahub-provisioning.service"
FILES = ("fcm_sender.py", "mobile_registry.py", "mobile_flask.py")

TEST_REGISTRY = '''    def begin_push_test(self, installation_id: str, now_epoch: int | None=None):
        """Throttle generic push test to once per two minutes per opted-in device."""
        try:
            normalized=str(uuid.UUID(installation_id))
        except (TypeError,ValueError,AttributeError):
            return "not_registered", None
        now=int(time.time()) if now_epoch is None else int(now_epoch)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS admin_mobile_push_tests(
                installation_id TEXT PRIMARY KEY,
                attempted_epoch INTEGER NOT NULL
            )""")
            row=db.execute("""SELECT fcm_token FROM admin_mobile_devices
                WHERE installation_id=? AND enabled=1""",(normalized,)).fetchone()
            if row is None:
                return "not_registered", None
            previous=db.execute("""SELECT attempted_epoch FROM admin_mobile_push_tests
                WHERE installation_id=?""",(normalized,)).fetchone()
            if previous and now-int(previous[0])<120:
                return "rate_limited", None
            db.execute("""INSERT INTO admin_mobile_push_tests(
                installation_id,attempted_epoch) VALUES(?,?)
                ON CONFLICT(installation_id)
                DO UPDATE SET attempted_epoch=excluded.attempted_epoch
            """,(normalized,now))
            return "ready", row["fcm_token"]

'''

TEST_FLASK = '''@bp.post("/admin/mobile/test-push")
def test_push():
    """Private one-device FCM test: server accepts a device ID, never a token."""
    _require_admin()
    _require_csrf()
    if not _push_transport_prepared():
        return _response({"error":"push_sender_not_configured"},503)
    if (request.content_length is None or request.content_length>400
            or not request.is_json):
        return _response({"error":"invalid_request"},400)
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)!={"installation_id"}:
        return _response({"error":"invalid_request"},400)
    state,token=_registry().begin_push_test(data["installation_id"])
    if state=="not_registered":
        return _response({"error":"device_not_registered"},404)
    if state=="rate_limited":
        return _response({"error":"retry_after_two_minutes"},429)
    try:
        accepted=fcm_sender.send(token,"push_test")
    except Exception:
        accepted=False
    if not accepted:
        return _response({"error":"fcm_delivery_not_accepted"},503)
    return _response({"fcm_accepted":True,
                      "device_receipt_not_yet_confirmed":True})


'''

TEST_PREPARED = '''def _push_transport_prepared():
    """Metadata check only: readiness still requires an actual FCM delivery test."""
    credential_path=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS","")
    if not fcm_sender.enabled() or not credential_path:
        return False
    file=Path(credential_path)
    return file.is_file() and not file.is_symlink() and not file.stat().st_mode & 0o077


'''


def insert_once(source: str, anchor: str, replacement: str, label: str):
    if source.count(anchor) != 1:
        raise RuntimeError("STOP_UNEXPECTED_SOURCE_" + label)
    return source.replace(anchor, replacement, 1)


def patch_sender(source: str):
    if '"push_test"' in source:
        if '"push_test"' not in source.split("ALLOWED_KINDS=", 1)[-1]:
            raise RuntimeError("STOP_PUSH_TEST_NOT_ALLOWLISTED")
        return source
    if 'ALLOWED_KINDS=' not in source:
        raise RuntimeError("STOP_NO_SENDER_ALLOWLIST")
    return insert_once(source, '"expiry_monthly","expiry_weekly",',
                       '"expiry_monthly","expiry_weekly","push_test",',
                       'SENDER_ALLOWLIST')


def patch_registry(source: str):
    if "def begin_push_test(" in source:
        if "admin_mobile_push_tests" not in source:
            raise RuntimeError("STOP_UNEXPECTED_REGISTRY_TEST_IMPL")
        return source
    for marker in ("class AdminMobileRegistry:", "import uuid", "import time",
                   "def _connect(self):", "def unregister(self,"):
        if marker not in source:
            raise RuntimeError("STOP_REGISTRY_EXPECTED_PATTERN_MISSING")
    new=insert_once(source,"    def _connect(self):",
                    TEST_REGISTRY+"    def _connect(self):","REGISTRY_METHOD")
    old='            return row.rowcount==1'
    replacement='''            if db.execute("""SELECT 1 FROM sqlite_master WHERE
                  type='table' AND name='admin_mobile_push_tests'""").fetchone():
                db.execute("DELETE FROM admin_mobile_push_tests WHERE installation_id=?",
                           (normalized,))
            return row.rowcount==1'''
    return insert_once(new,old,replacement,"REGISTRY_UNREGISTER")


def patch_flask(source: str):
    if '@bp.post("/admin/mobile/test-push")' in source:
        if "push_sender_configured" not in source or "import fcm_sender" not in source:
            raise RuntimeError("STOP_UNEXPECTED_EXISTING_PUSH_TEST")
        return source
    anchors=("@bp.get(\"/admin/mobile/bootstrap\")",
             "@bp.post(\"/admin/mobile/unregister\")",
             "from mobile_registry import AdminMobileRegistry",
             "def _require_csrf():")
    if any(source.count(needle)!=1 for needle in anchors):
        raise RuntimeError("STOP_UNEXPECTED_FLASK_API_REVISION")
    if "import fcm_sender" not in source:
        source=insert_once(source,"from mobile_registry import AdminMobileRegistry",
            "from mobile_registry import AdminMobileRegistry\nimport fcm_sender","FLASK_IMPORT")
    source=insert_once(source,'@bp.get("/admin/mobile/bootstrap")',
                       TEST_PREPARED+'@bp.get("/admin/mobile/bootstrap")',"FLASK_BOOTSTRAP")
    source=insert_once(source,
        '       "app":"EpiMediaHub Admin"})',
        '       "push_sender_configured":_push_transport_prepared(),\n'
        '       "app":"EpiMediaHub Admin"})', "FLASK_CONFIG_RESPONSE")
    source=insert_once(source,'@bp.post("/admin/mobile/unregister")',
                       TEST_FLASK+'@bp.post("/admin/mobile/unregister")',
                       "FLASK_TEST_ENDPOINT")
    return source


def run(*args, timeout=35):
    return subprocess.run(args, capture_output=True, text=True,
                          timeout=timeout, check=False)


def service_ready():
    return run("systemctl","is-active","--quiet",SERVICE).returncode == 0


def preflight():
    if os.geteuid()!=0 or BASE.is_symlink() or not BASE.is_dir():
        raise RuntimeError("STOP_EXPECTED_ROOT_DASHBOARD_HOST")
    if not service_ready():
        raise RuntimeError("STOP_DASHBOARD_NOT_ACTIVE")
    workspace=run("systemctl","show",SERVICE,"-p","WorkingDirectory","--value")
    if workspace.returncode!=0 or workspace.stdout.strip()!=str(BASE):
        raise RuntimeError("STOP_WRONG_DASHBOARD_WORKING_DIRECTORY")
    owner=run("systemctl","show",SERVICE,"-p","User","--value")
    if owner.returncode!=0 or not owner.stdout.strip() or owner.stdout.strip()=="root":
        raise RuntimeError("STOP_ADMIN_SERVICE_OWNER_INVALID")
    original={}
    for name in FILES:
        file=BASE/name
        if not file.is_file() or file.is_symlink() or file.stat().st_size>200_000:
            raise RuntimeError("STOP_MISSING_OR_UNSAFE_"+name.upper())
        original[name]=file.read_text(encoding="utf-8")
    replacements={
        "fcm_sender.py":patch_sender(original["fcm_sender.py"]),
        "mobile_registry.py":patch_registry(original["mobile_registry.py"]),
        "mobile_flask.py":patch_flask(original["mobile_flask.py"]),
    }
    for name,source in replacements.items():
        compile(source,str(BASE/name),"exec")
    if not (all("push_test" in replacements[name] for name in FILES) and
            'push_sender_configured' in replacements['mobile_flask.py']):
        raise RuntimeError("STOP_MISSING_PUSH_API_COMPONENT")
    return original,replacements


def healthy():
    deadline=time.monotonic()+40
    while time.monotonic()<deadline:
        if service_ready():
            try:
                with urllib.request.urlopen("http://127.0.0.1:8787/health",timeout=3) as response:
                    if response.status==200:
                        return True
            except (urllib.error.URLError,OSError):
                pass
        time.sleep(1)
    return False


def save_and_install(original,replacements):
    if BACKUP_ROOT.is_symlink():
        raise RuntimeError("STOP_UNSAFE_BACKUP_DIRECTORY")
    BACKUP_ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    if BACKUP_ROOT.stat().st_mode & 0o077:
        raise RuntimeError("STOP_BACKUP_NOT_PRIVATE")
    backup=Path(tempfile.mkdtemp(prefix="admin-push-selftest-",dir=BACKUP_ROOT))
    backup.chmod(0o700)
    changed=[name for name in FILES if original[name]!=replacements[name]]
    for name in FILES:
        shutil.copy2(BASE/name,backup/name)
    print("BACKUP_OK:",backup,flush=True)
    if not changed:
        print("PUSH_TEST_ALREADY_INSTALLED; NO_DASHBOARD_RESTART")
        return
    service_touched=False
    try:
        if not service_ready():
            raise RuntimeError("STOP_DASHBOARD_BECAME_INACTIVE")
        # Refuse to replace files that changed between validation and backup.
        for name in FILES:
            if (BASE/name).read_text(encoding="utf-8")!=original[name]:
                raise RuntimeError("STOP_CONCURRENT_SOURCE_EDIT")
        for name in changed:
            target=BASE/name
            mode=stat.S_IMODE(target.stat().st_mode)
            with tempfile.NamedTemporaryFile(
                    mode="w",dir=BASE,prefix=".admin-push-selftest-",
                    encoding="utf-8",delete=False) as handle:
                tmp=Path(handle.name)
                handle.write(replacements[name])
            try:
                tmp.chmod(mode)
                shutil.chown(tmp,user=target.stat().st_uid,group=target.stat().st_gid)
                os.replace(tmp,target)
            finally:
                tmp.unlink(missing_ok=True)
        service_touched=True
        restart=run("systemctl","restart",SERVICE,timeout=45)
        if restart.returncode!=0 or not healthy():
            raise RuntimeError("STOP_SERVICE_HEALTH_AFTER_INSTALL")
        print("ADMIN_PUSH_TEST_INSTALLED: safe backend self-test API + FCM kind")
        print("DASHBOARD_HEALTH_OK; PUSH_DELIVERY_NOT_YET_TESTED")
        print("CUSTOMERS_PLAYLISTS_EPISCENE_AND_MARKERS_UNCHANGED")
    except BaseException:
        for name in changed:
            shutil.copy2(backup/name,BASE/name)
        if service_touched:
            restored=run("systemctl","restart",SERVICE,timeout=45)
            print("ROLLBACK_DASHBOARD_RESTART:",restored.returncode,flush=True)
        print("ROLLBACK_ATTEMPTED:",backup,flush=True)
        raise


def main():
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check",action="store_true")
    mode.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    original,replacements=preflight()
    changed=[name for name in FILES if original[name]!=replacements[name]]
    print("PREFLIGHT_OK: local admin mobile API matches audited patterns")
    print("CHANGED_MODULES:",",".join(changed) or "none")
    if args.check:
        print("READ_ONLY_CHECK_COMPLETE")
        return
    if os.environ.get("EPI_ADMIN_PUSH_SELFTEST_APPROVED")!="YES":
        raise RuntimeError("STOP_OWNER_CONFIRMATION_REQUIRED")
    save_and_install(original,replacements)


if __name__=="__main__":
    try:
        main()
    except (OSError,RuntimeError,ValueError,SyntaxError,UnicodeError,
            subprocess.TimeoutExpired) as error:
        label=str(error)
        safe=label if label.startswith("STOP_") else "STOP_"+type(error).__name__
        print("SAFE_STOP:",safe)
        sys.exit(2)
