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
PAYLOAD_SHA256 = 'feba1f08945908f45f46fd64269d6599eb25120430221ee23d89868d2dcc0a9f'
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
