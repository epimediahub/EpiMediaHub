#!/usr/bin/env python3
"""Add 1.0.20 licensing to the installed 0.8.x backend without replacing it.

The payload is embedded and hashed. All preflight migrations run on a SQLite
backup before the provisioning service is stopped. Existing code/data is backed
up; failure restores the changed files, leaving additive database tables intact.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
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
import zlib

SERVICE = "epimediahub-provisioning.service"
BASE = Path("/opt/epimediahub/provisioning")
PAYLOAD_B64 = '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'
PAYLOAD_SHA256 = 'f71922338b010468b037ab81355249221b210a677abc36c3efbdc338dbe93172'
REQUIRED_CAPABILITIES = {
    "licensing_ready": True, "trial_days": 7, "activation_credits": 1,
    "retail_price_eur_cents": 1000, "manual_reseller_prices": True,
}
PAYLOAD_PATHS = {
    "license_api.py", "templates/credits_v120.html",
    "templates/reseller_credits_v120.html",
}

# Runs in the service's interpreter against either the staged copy or live DB.
CHECK_CODE = r'''
import hashlib,json,os,sqlite3
from pathlib import Path
database=Path(os.environ["EPIMEDIAHUB_DATA_DIR"])/"provisioning.db"
def protected_rows():
    result={}
    with sqlite3.connect(database) as con:
        tables=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            # Existing startup migrations may add bookkeeping for new customers.
            # Preserve the customer/playlist records, not their migration markers.
            if table.endswith("_migrations"):
                continue
            if table not in {"customers","resellers","devices","activations","pairings"} and "playlist" not in table:
                continue
            quoted='"'+table.replace('"','""')+'"'
            columns=[r[1] for r in con.execute("PRAGMA table_info("+quoted+")")]
            if table=="resellers":columns=[c for c in columns if c!="credit_price_cents"]
            selection=','.join('"'+c.replace('"','""')+'"' for c in columns)
            h=hashlib.sha256()
            count=0
            for row in con.execute("SELECT "+selection+" FROM "+quoted+" ORDER BY "+','.join(str(n+1) for n in range(len(columns)))):
                h.update(repr(tuple(row)).encode());count+=1
            result[table]=(columns,count,h.hexdigest())
    return result
snapshot_check=os.environ.get("EPIMEDIAHUB_CREDIT_SNAPSHOT_CHECK")=="1"
before=protected_rows() if snapshot_check else None
import wsgi
from app import app,db
app.config["TESTING"]=True
client=app.test_client()
expected={"licensing_ready":True,"trial_days":7,"activation_credits":1,"retail_price_eur_cents":1000,"manual_reseller_prices":True}
response=client.get("/v1/license/capabilities")
assert response.status_code==200 and all(response.json.get(k)==v for k,v in expected.items()), "Lizenz-API ist nicht bereit"
assert client.post("/v1/license/status",json={}).status_code==400
assert client.get("/health").status_code==200
if snapshot_check:
    with client.session_transaction() as session:session["admin"]=True
    for path in ("/admin","/admin/credits"):
        assert client.get(path).status_code==200, "Admin-Seite nicht erreichbar: "+path
    with db() as con:reseller=con.execute("SELECT id FROM resellers WHERE enabled=1 LIMIT 1").fetchone()
    if reseller:
        with client.session_transaction() as session:
            session.clear();session["reseller_id"]=reseller["id"]
        for path in ("/reseller","/reseller/credits"):
            assert client.get(path).status_code==200, "Reseller-Seite nicht erreichbar: "+path
    assert before==protected_rows(), "Bestehende Konten, Geräte oder Playlists würden verändert"
print("Lizenz-API und vorhandene Daten geprüft.")
'''


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def payload():
    raw = zlib.decompress(base64.b64decode(PAYLOAD_B64))
    require(hashlib.sha256(raw).hexdigest() == PAYLOAD_SHA256,
            "Die Prüfsumme des Installationspakets stimmt nicht.")
    files = json.loads(raw)
    require(set(files) == PAYLOAD_PATHS, "Unerwartete Dateien im Installationspaket.")
    return files


def patch_files(base, files):
    """Patch only the registration and navigation anchors in installed files."""
    result = dict(files)
    wsgi = (base / "wsgi.py").read_text()
    require("install_dashboard_v080" in wsgi and "install_skip_markers" in wsgi,
            "Erwartete Raspberry-Version 0.8.x wurde nicht erkannt.")
    if "import license_api" not in wsgi:
        wsgi = wsgi.rstrip() + "\n\nimport license_api  # Registers additive credit and license routes.\n"
    result["wsgi.py"] = wsgi
    for name, endpoint in (("dashboard_v080.html", "admin_credits"),
                           ("reseller_dashboard_v080.html", "reseller_dashboard")):
        relative = "templates/" + name
        source = (base / relative).read_text()
        marker = '  <div class="hierarchy-topbar-actions">'
        target = "{{ url_for('" + endpoint + "') }}"
        if target not in source:
            require(source.count(marker) == 1, "Navigationsanker nicht eindeutig: " + name)
            link = '\n    <a class="button button-ghost" href="' + target + '">Credits & Lizenzen</a>'
            source = source.replace(marker, marker + link, 1)
        result[relative] = source
    return result


def snapshot_db(source, destination):
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=30) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)
            require(dst.execute("PRAGMA quick_check").fetchone()[0] == "ok",
                    "Die Datenbankkopie konnte nicht geprüft werden.")


def run_service_check(python, directory, environment, account, log_path, snapshot=False):
    env = dict(environment)
    env.update(PYTHONPATH=str(directory), PYTHONDONTWRITEBYTECODE="1",
               EPIMEDIAHUB_CREDIT_SNAPSHOT_CHECK="1" if snapshot else "0")
    credentials = {}
    if (os.geteuid(), os.getegid()) != (account.pw_uid, account.pw_gid):
        credentials = dict(user=account.pw_uid, group=account.pw_gid, extra_groups=[])
    result = subprocess.run([str(python), "-c", CHECK_CODE], cwd=directory,
                            env=env, capture_output=True, text=True, timeout=120, **credentials)
    log_path.write_text(result.stdout + result.stderr)
    os.chmod(log_path, 0o600)
    # Do not echo exception output, which may contain customer or configuration data.
    require(result.returncode == 0, "Server-Prüfung fehlgeschlagen. Geschütztes Protokoll: " + str(log_path))
    return result


def systemctl(*arguments):
    return subprocess.check_output(["systemctl", *arguments], text=True, timeout=45).strip()


def local_json(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request("http://127.0.0.1:8787" + path, data=data,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def wait_healthy(baseline):
    for _ in range(30):
        try:
            status, capabilities = local_json("/v1/license/capabilities")
            require(status == 200 and all(capabilities.get(k) == v for k, v in REQUIRED_CAPABILITIES.items()), "Lizenz-API fehlt.")
            require(local_json("/v1/license/status", {})[0] == 400, "Lizenz-Validierung fehlt.")
            status, current = local_json("/health")
            require(status == 200 and current.get("status") == "ok", "Server nicht bereit.")
            for key in ("service", "api_version", "features"):
                if key in baseline:
                    require(current.get(key) == baseline[key], "Vorhandene Server-Funktionen fehlen: " + key)
            return
        except (OSError, ValueError, RuntimeError):
            time.sleep(1)
    raise RuntimeError("Der Server ist nach dem Update nicht vollständig bereit.")


def write_atomic(path, content):
    temporary = path.with_name(path.name + ".credits-new")
    temporary.write_text(content)
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def apply_update(files, backup, old_paths, database, python, environment, account, baseline_health):
    stopped = False
    changed = False
    try:
        stopped = True
        systemctl("stop", SERVICE)
        snapshot_db(database, backup / "provisioning-at-install.db")
        for relative, content in files.items():
            changed = True
            write_atomic(BASE / relative, content)
        run_service_check(python, BASE, environment, account, backup / "migration.log")
        systemctl("start", SERVICE)
        wait_healthy(baseline_health)
    except BaseException:
        if stopped:
            systemctl("stop", SERVICE)
            if changed:
                for relative in files:
                    target = BASE / relative
                    if relative in old_paths:
                        shutil.copy2(backup / "files" / relative, target)
                    else:
                        target.unlink(missing_ok=True)
            systemctl("start", SERVICE)
            print("Vorherige Serverdateien wiederhergestellt. Datenbank nicht zurückgesetzt.", file=sys.stderr)
        raise


def install():
    require(os.geteuid() == 0, "Bitte mit sudo python3 ausführen.")
    lock = open("/run/epimediahub-credits-install.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    require(systemctl("is-active", SERVICE) == "active", "Der vorhandene Server muss vor dem Update laufen.")
    require(systemctl("show", SERVICE, "--property=WorkingDirectory", "--value") == str(BASE),
            "Unerwartetes Installationsverzeichnis; keine Dateien verändert.")
    username = systemctl("show", SERVICE, "--property=User", "--value")
    require(bool(username) and username != "root", "Erwarteter Dienstbenutzer fehlt.")
    account = pwd.getpwnam(username)
    pid = int(systemctl("show", SERVICE, "--property=MainPID", "--value"))
    require(pid > 0, "Serverprozess fehlt.")
    # Read the actual service environment without evaluating or displaying secrets.
    pairs = (Path("/proc") / str(pid) / "environ").read_bytes().split(b"\0")
    environment = dict(item.decode().split("=", 1) for item in pairs if b"=" in item)
    data_dir = Path(environment.get("EPIMEDIAHUB_DATA_DIR", "/var/lib/epimediahub"))
    database = data_dir / "provisioning.db"
    require(data_dir.is_absolute() and database.is_file(), "Vorhandene Datenbank fehlt.")
    environment["EPIMEDIAHUB_DATA_DIR"] = str(data_dir)
    python = BASE / ".venv/bin/python"
    require(python.is_file(), "Python-Umgebung des Servers fehlt.")
    _, baseline_health = local_json("/health")
    files = patch_files(BASE, payload())
    backup = Path(tempfile.mkdtemp(prefix="credits-v120-" + time.strftime("%Y%m%d-%H%M%S") + "-",
                                   dir="/var/backups"))
    os.chmod(backup, 0o700)
    print("Sicherung:", backup, flush=True)
    old_paths = []
    for relative in files:
        old = BASE / relative
        if old.exists():
            destination = backup / "files" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old, destination)
            old_paths.append(relative)
    (backup / "manifest.json").write_text(json.dumps({"existing": old_paths, "changed": sorted(files)}, indent=2))
    snapshot_db(database, backup / "provisioning-before.db")
    print("Prüfe Installation mit einer Kopie der vorhandenen Daten ...", flush=True)
    with tempfile.TemporaryDirectory(prefix="epimediahub-credit-check-") as temp:
        stage = Path(temp)
        for source in BASE.glob("*.py"):
            shutil.copy2(source, stage / source.name)
        for directory in ("templates", "static"):
            shutil.copytree(BASE / directory, stage / directory)
        staged_data = stage / "data"
        staged_data.mkdir()
        shutil.copy2(backup / "provisioning-before.db", staged_data / "provisioning.db")
        for relative, content in files.items():
            (stage / relative).write_text(content)
        for entry in [stage, *stage.rglob("*")]:
            os.chown(entry, account.pw_uid, account.pw_gid)
        staged_env = dict(environment, EPIMEDIAHUB_DATA_DIR=str(staged_data))
        run_service_check(python, stage, staged_env, account, backup / "preflight.log", snapshot=True)
    print("Vorprüfung erfolgreich. Installiere Credits und Lizenzen ...", flush=True)
    apply_update(files, backup, old_paths, database, python, environment, account, baseline_health)
    print("FERTIG: 7 Tage Test, 1 Credit pro Gerät, freie Resellerpreise, Endkunden 10 Euro.")
    print("Admin: https://admin.epimediahub.com/admin/credits")
    print("Reseller: https://reseller.epimediahub.com/reseller/credits")
    print("Das signierte Android-Update kann jetzt veröffentlicht werden.")


if __name__ == "__main__":
    try:
        install()
    except Exception as error:
        print("FEHLER:", error, file=sys.stderr)
        sys.exit(1)
