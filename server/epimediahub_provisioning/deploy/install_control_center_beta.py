#!/usr/bin/env python3
"""Protected, additive EpiMediaHub admin/reseller dashboard beta installation.

Run on the machine running epimediahub-provisioning.service, never on the VPN
gateway or the EpiScene compute worker.  --check is strictly read-only on the
live service and database; --apply preserves the database and installed addons.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

BASE = Path("/opt/epimediahub/provisioning")
SERVICE = "epimediahub-provisioning.service"
ROOT = Path(__file__).resolve().parents[1]
UPDATED = (
    "templates/dashboard_v080.html",
    "templates/reseller_dashboard_v080.html",
    "static/beta-admin.css",
    "dashboard_diagnostics.py",
    "templates/dashboard_diagnostics.html",
    "static/beta-diagnostics.css",
    "wsgi.py",
)

def require(condition, description):
    if not condition:
        raise RuntimeError(description)

def command(*args):
    return subprocess.check_output(args, text=True, timeout=35).strip()

def snapshot(source: Path, dest: Path):
    with sqlite3.connect("file:" + str(source) + "?mode=ro", uri=True, timeout=25) as src, sqlite3.connect(dest) as dst:
        src.backup(dst)
        require(dst.execute("PRAGMA quick_check").fetchone()[0] == "ok", "SQLite Backup ist beschädigt.")

def hash_protected(database: Path):
    checks = {}
    with sqlite3.connect("file:" + str(database) + "?mode=ro", uri=True) as con:
        for name in ("customers", "resellers", "devices", "activations", "pairings", "customer_playlists"):
            if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone():
                continue
            cols = [c[1] for c in con.execute('PRAGMA table_info("' + name + '")')]
            # Staged module bootstrapping may add new feature columns.
            cols = [c for c in cols if c not in {"credit_price_cents"}]
            select = ",".join('"' + col.replace('"','""') + '"' for col in cols)
            digest = hashlib.sha256()
            for row in con.execute('SELECT ' + select + ' FROM "' + name + '" ORDER BY 1'):
                digest.update(repr(tuple(row)).encode())
            checks[name] = digest.hexdigest()
    return checks

def base_environment():
    require(os.geteuid() == 0, "Als root ausführen (sudo).")
    require(BASE.joinpath("wsgi.py").is_file(), "Dies ist nicht der Dashboard-Server: " + str(BASE))
    require(BASE.joinpath("dashboard_v080.py").is_file(), "Dashboard-Version 0.8.x fehlt.")
    require(BASE.joinpath("vpn_dashboard.py").is_file(), "VPN-Modul fehlt. Zuerst VPN-Dashboard prüfen.")
    vpn = BASE.joinpath("vpn_dashboard.py").read_text()
    require("vpn_trials" in vpn and 'trial7' in vpn,
            "Der 7-Tage-VPN-Test fehlt im installierten Backend; keine unsichere Überschreibung.")
    require(command("systemctl", "is-active", SERVICE) == "active", "Dashboard-Dienst läuft nicht.")
    require(command("systemctl", "show", SERVICE, "-p", "WorkingDirectory", "--value") == str(BASE),
            "Der Dienst läuft an einem unerwarteten Ort.")
    username = command("systemctl", "show", SERVICE, "-p", "User", "--value")
    require(username and username != "root", "Ein eigener Dienstbenutzer ist erforderlich.")
    account = pwd.getpwnam(username)
    pid = int(command("systemctl", "show", SERVICE, "-p", "MainPID", "--value"))
    require(pid > 0, "Hauptprozess fehlt.")
    raw = Path("/proc").joinpath(str(pid), "environ").read_bytes().split(b"\0")
    env = dict(part.decode("utf-8", "surrogateescape").split("=", 1) for part in raw if b"=" in part)
    data = Path(env.get("EPIMEDIAHUB_DATA_DIR", "/var/lib/epimediahub"))
    require(data.is_absolute() and (data / "provisioning.db").is_file(), "Die produktive SQLite-Datenbank fehlt.")
    env["EPIMEDIAHUB_DATA_DIR"] = str(data)
    python = BASE / ".venv/bin/python"
    require(python.is_file(), "Die aktive Python-Umgebung fehlt.")
    return env, python, account, data / "provisioning.db"

def preserve_links(previous, replacement):
    def nav(source):
        return re.search(r'(<div class="hierarchy-topbar-actions">)(.*?)(</div>)', source, re.S)
    current, newer = nav(previous), nav(replacement)
    require(current is not None and newer is not None, "Dashboard-Navigation unerwartet.")
    old_links = re.findall(r'<a\b[^>]*>.*?</a>', current.group(2), re.S)
    # Keep optional earlier product-module navigation; do not discard existing links.
    missing = [link for link in old_links if link not in replacement]
    return replacement.replace(newer.group(1), newer.group(1) + "\n    " + "\n    ".join(missing), 1) if missing else replacement

def package():
    staged = {}
    for name in UPDATED:
        if name == "wsgi.py":
            wsgi = (BASE / name).read_text()
            require("install_dashboard_v080" in wsgi and "install_vpn_dashboard" in wsgi,
                    "Bestehende Admin-/VPN-Registrierung unbekannt; nicht überschrieben.")
            if "import dashboard_diagnostics" not in wsgi:
                wsgi = wsgi.rstrip() + "\n\nimport dashboard_diagnostics  # Read-only admin metrics.\n"
            staged[name] = wsgi
        else:
            p = ROOT / name
            require(p.is_file(), "Quelldatei fehlt: " + name)
            new = p.read_text()
            if name.startswith("templates/") and name.endswith("_v080.html"):
                new = preserve_links((BASE / name).read_text(), new)
            staged[name] = new
    require("beta-visible-playlists" in staged["templates/dashboard_v080.html"], "Kompakte Kundenansicht fehlt.")
    require("beta-visible-playlists" in staged["templates/reseller_dashboard_v080.html"], "Kompakte Reselleransicht fehlt.")
    require("operation\" value=\"trial7\"" in staged["templates/dashboard_v080.html"], "VPN-Test fehlt.")
    return staged

def stage_check(files, env, python, account, dbfile, directory):
    stage = directory / "code"
    stage.mkdir()
    for item in BASE.glob("*.py"):
        shutil.copy2(item, stage / item.name)
    for folder in ("templates", "static"):
        shutil.copytree(BASE / folder, stage / folder)
    for rel, content in files.items():
        dest = stage / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
    test_db_dir = directory / "db"
    test_db_dir.mkdir()
    snapshot(dbfile, test_db_dir / "provisioning.db")
    before = hash_protected(test_db_dir / "provisioning.db")
    for item in [stage, *stage.rglob("*"), test_db_dir, *test_db_dir.rglob("*")]:
        os.chown(item, account.pw_uid, account.pw_gid)
    test_env = dict(env, PYTHONPATH=str(stage), EPIMEDIAHUB_DATA_DIR=str(test_db_dir),
                    PYTHONDONTWRITEBYTECODE="1")
    program = """
from app import app
import wsgi
app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
c=app.test_client()
assert c.get('/admin/diagnostics').status_code in (302, 303)
with c.session_transaction() as session: session['admin']=True
assert c.get('/admin/diagnostics').status_code==200
assert c.get('/admin').status_code==200
assert c.get('/admin/vpn').status_code==200
assert b'beta-visible-playlists' in c.get('/admin').data or b'ADMIN CONTROL CENTER' in c.get('/admin').data
print('Staged dashboard, VPN and admin diagnostics passed')
"""
    result = subprocess.run([str(python), "-c", program], env=test_env, cwd=stage,
                            user=account.pw_uid, group=account.pw_gid, extra_groups=[],
                            capture_output=True, text=True, timeout=100)
    # Intentionally withhold logs: service imports may print private details.
    require(result.returncode == 0, "Staging-Test fehlgeschlagen. Live-System unverändert; lokale Prüfung erforderlich.")
    require(before == hash_protected(test_db_dir / "provisioning.db"),
            "Staging-Test würde Kunden-/Gerätedaten verändern.")

def health():
    for path in ("/health", "/admin/diagnostics"):
        opener = urllib.request.build_opener(NoRedirect())
        try:
            with opener.open("http://127.0.0.1:8787" + path, timeout=5) as response:
                code = response.status
        except urllib.error.HTTPError as exc:
            code = exc.code
        require(code == (200 if path == "/health" else 302), "Endpoint nicht bereit: " + path)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def install(files, dbfile, env, python, account):
    backups = Path("/var/backups/epimediahub")
    backups.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="dashboard-beta-" + time.strftime("%Y%m%d-%H%M%S") + "-", dir=backups))
    backup.chmod(0o700)
    old = {}
    for rel in UPDATED:
        p = BASE / rel
        if p.exists():
            backup_file = backup / "code" / rel
            backup_file.parent.mkdir(exist_ok=True, parents=True)
            shutil.copy2(p, backup_file)
            old[rel] = True
        else:
            old[rel] = False
    snapshot(dbfile, backup / "provisioning.db")
    (backup / "files.json").write_text(json.dumps(old, indent=2))
    changed = []
    try:
        command("systemctl", "stop", SERVICE)
        for rel, content in files.items():
            target = BASE / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + ".beta-tmp")
            temp.write_text(content)
            os.chmod(temp, 0o644)
            os.chown(temp, account.pw_uid, account.pw_gid)
            os.replace(temp, target)
            changed.append(rel)
        command("systemctl", "start", SERVICE)
        for attempt in range(25):
            try:
                health()
                break
            except (RuntimeError, OSError):
                time.sleep(1)
        else:
            raise RuntimeError("Nach dem Start fehlen Health- oder Login-Endpunkte.")
    except BaseException:
        command("systemctl", "stop", SERVICE)
        for rel in changed:
            dest = BASE / rel
            if old[rel]:
                shutil.copy2(backup / "code" / rel, dest)
            else:
                dest.unlink(missing_ok=True)
        command("systemctl", "start", SERVICE)
        raise RuntimeError("Installation zurückgenommen; Kunden-Datenbank unberührt. Backup: " + str(backup))
    print("INSTALL OK – Dashboard-Beta und datensparsame Fehlerdiagnose aktiv.")
    print("Sicherung:", backup)
    print("Die App-Jahreslizenz benötigt weiterhin eine separat geprüfte App-/Lizenz-API-Anbindung.")

def main():
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    lock = open("/run/epimediahub-dashboard-beta.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    env, python, account, dbfile = base_environment()
    files = package()
    with tempfile.TemporaryDirectory(prefix="epimediahub-control-center-") as temp:
        stage_check(files, env, python, account, dbfile, Path(temp))
    print("CHECK OK – Server, Datenbanksicherung, Admin- und VPN-Routen geprüft.")
    if args.apply:
        install(files, dbfile, env, python, account)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ABBRUCH:", exc, file=sys.stderr)
        sys.exit(1)
