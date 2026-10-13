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
# An older production VPN version was verified by its on-host SHA-256.
# Never replace an unknown/local custom VPN module.
TRUSTED_OLD_VPN_SHA256 = "1417f694f32f3b66ad715efad7c3cd8f76f0d6ccdcda6445cc4c8737294ee91a"
REVIEWED_VPN_SHA256 = "e52391fe2c34c93f35e10fd1a3d2e4eaa351bd0ad55a47f63ec574c933c15c22"
assert len(TRUSTED_OLD_VPN_SHA256) == 64 and len(REVIEWED_VPN_SHA256) == 64, (
    "VPN-Fingerprints muessen 64-stellige SHA-256-Werte sein"
)
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
    "vpn_dashboard.py",
    "vpn_auto_enroll.py",
    "dashboard_security.py",
    "device_diagnostics.py",
    "license_api.py",
    "annual_license.py",
    "templates/credits_v120.html",
    "templates/reseller_credits_v120.html",
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
        for name in ("customers", "resellers", "devices", "activations", "pairings",
                     "customer_playlists", "vpn_devices", "vpn_trials", "vpn_trial_authorizations", "vpn_credits",
                     "vpn_accounts", "vpn_orders", "vpn_operations", "vpn_plans",
                     "vpn_audit", "vpn_meta", "lifetime_licenses", "license_subjects",
                     "credit_ledger", "reseller_credit_ledger"):
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
    # Older installs do not yet have the manual trial feature. The module
    # version guard and migration test run before any live changes.
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
    require(len(env.get("EPIMEDIAHUB_SECRET_KEY", "")) >= 32,
            "Dauerhafter Flask-Session-Key mit mindestens 32 Zeichen erforderlich.")
    require(len(env.get("EPIMEDIAHUB_ADMIN_PASSWORD", "")) >= 12,
            "Das Admin-Passwort muss mindestens 12 Zeichen besitzen.")
    require(len(env.get("EPIMEDIAHUB_ADMIN_TOKEN", "")) >= 32,
            "Der Admin-API-Token ist zu kurz.")
    require(env.get("EPIMEDIAHUB_SECURE_COOKIES", "1") != "0",
            "Unsichere Session-Cookies sind in Produktion nicht zulässig.")
    require(env.get("EPIMEDIAHUB_PUBLIC_URL", "https://setup.epimediahub.com").startswith("https://"),
            "Öffentliche Setup-Links dürfen nur HTTPS verwenden.")
    # Automatic WireGuard enrollment must never start consuming trial days
    # until the correct Finland gateway PUBLIC metadata is provisioned.
    import base64
    import ipaddress
    vpn_key = env.get("EPIMEDIAHUB_VPN_SERVER_PUBLIC_KEY", "").strip()
    vpn_endpoint = env.get("EPIMEDIAHUB_VPN_ENDPOINT", "").strip()
    try:
        decoded = base64.b64decode(vpn_key, validate=True)
        key_ready = len(decoded) == 32 and any(decoded) and base64.b64encode(decoded).decode() == vpn_key
    except (ValueError, TypeError):
        key_ready = False
    require(key_ready, "Finnland: EPIMEDIAHUB_VPN_SERVER_PUBLIC_KEY muss der öffentliche 44-stellige WireGuard-Schlüssel des BESTEHENDEN Gateways sein.")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,251}:[0-9]{2,5}", vpn_endpoint),
            "Finnland: EPIMEDIAHUB_VPN_ENDPOINT muss den bestätigten Host:Port des BESTEHENDEN Gateways enthalten.")
    net = ipaddress.ip_network(env.get("EPIMEDIAHUB_VPN_SUBNET", "10.92.0.0/24"), strict=True)
    require(net.version == 4 and net.num_addresses <= 4096 and net.prefixlen <= 29,
            "Finnland: VPN-Adresspool ungültig (IPv4, 8 bis 4096 Adressen).")
    # Deliberately reserve a non-overlapping part of the real Finland network:
    # gateway peers absent from vpn_devices may already use 10.92.0.2/.3.
    raw_auto_pool = env.get("EPIMEDIAHUB_VPN_AUTO_POOL", "").strip()
    require(bool(raw_auto_pool),
            "Finnland: EPIMEDIAHUB_VPN_AUTO_POOL fehlt. Exklusiven, vorher am WireGuard-Server geprüften Adresspool festlegen.")
    try:
        auto_pool = ipaddress.ip_network(raw_auto_pool, strict=True)
    except ValueError:
        raise RuntimeError("Finnland: Ungültiger exklusiver Auto-VPN-Adresspool.") from None
    require(auto_pool.version == 4 and auto_pool.subnet_of(net) and auto_pool.num_addresses >= 8,
            "Finnland: Auto-IP-Pool muss innerhalb des Finnland-IPv4-Netzwerks liegen (mindestens 8 Adressen).")
    require(net.network_address not in auto_pool
            and ipaddress.ip_address(int(net.network_address) + 1) not in auto_pool,
            "Finnland: Auto-IP-Pool darf weder Netzadresse noch das Gateway enthalten. Ein /25-Broadcast wird niemals vergeben.")

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
            if "import license_api" not in wsgi:
                wsgi = wsgi.rstrip() + "\n\nimport license_api  # 7-day trial and Lifetime credits.\n"
            if "import annual_license" not in wsgi:
                wsgi = wsgi.rstrip() + "\n\nimport annual_license  # 365-day device licenses.\n"
            if "import device_diagnostics" not in wsgi:
                wsgi = wsgi.rstrip() + "\n\nimport device_diagnostics  # Opt-in failure counters.\n"
            if "import vpn_auto_enroll" not in wsgi:
                wsgi = wsgi.rstrip() + "\n\nimport vpn_auto_enroll  # Manually approved VPN auto enrollment.\n"
            if "install_dashboard_security" not in wsgi:
                wsgi = wsgi.rstrip() + "\n\nfrom dashboard_security import install as install_dashboard_security\ninstall_dashboard_security(app)\n"
            staged[name] = wsgi
        else:
            p = ROOT / name
            require(p.is_file(), "Quelldatei fehlt: " + name)
            installed = BASE / name
            preserved = {"license_api.py", "templates/credits_v120.html", "templates/reseller_credits_v120.html"}
            new = installed.read_text() if name in preserved and installed.is_file() else p.read_text()
            if name == "vpn_dashboard.py":
                current_hash = hashlib.sha256(installed.read_bytes()).hexdigest()
                source_hash = hashlib.sha256(p.read_bytes()).hexdigest()
                require(source_hash == REVIEWED_VPN_SHA256,
                        "Die geprüfte VPN-Quelldatei stimmt nicht mit der Release-Version überein.")
                require(current_hash in {TRUSTED_OLD_VPN_SHA256, REVIEWED_VPN_SHA256},
                        "Unbekannte VPN-Produktivversion: kein automatischer Austausch. Zuerst Diff und Datenbankschema prüfen.")
                # Preserve identical production code; upgrade only the known
                # older fingerprint. All changes are tested on a DB snapshot.
                new = installed.read_text() if current_hash == REVIEWED_VPN_SHA256 else p.read_text()
                require("vpn_trials" in new and "trial7" in new,
                        "Die vorbereitete VPN-Version enthält den 7-Tage-Test nicht.")
            if name == "license_api.py":
                require(all(marker in new for marker in (
                    "license_subjects", "trial_key_hash", "lifetime_licenses",
                    "def license_status", "def license_capabilities", "def admin_credits")),
                    "Bestehendes Lizenzmodul ist nicht kompatibel, keine riskante Überschreibung.")
            if name.startswith("templates/") and name.endswith("_v080.html"):
                new = preserve_links((BASE / name).read_text(), new)
            staged[name] = new
    require("beta-visible-playlists" in staged["templates/dashboard_v080.html"], "Kompakte Kundenansicht fehlt.")
    require("beta-visible-playlists" in staged["templates/reseller_dashboard_v080.html"], "Kompakte Reselleransicht fehlt.")
    require("operation\" value=\"trial7\"" in staged["templates/dashboard_v080.html"], "VPN-Test fehlt.")
    return staged

def stage_check(files, env, python, account, dbfile, directory):
    # tempfile.TemporaryDirectory is root-only; stage code is tested as the service user.
    os.chown(directory, account.pw_uid, account.pw_gid)
    os.chmod(directory, 0o700)
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
assert b'beta-visible-playlists' in c.get('/admin').data
assert b'name="_dashboard_csrf"' in c.get('/admin').data
assert c.get('/v1/license/capabilities').json['annual_license_ready'] is True
assert c.post('/v1/license/status', json={}).status_code==400
assert c.get('/v1/device/vpn/status').status_code==401
assert c.post('/v1/device/vpn/enroll', json={}).status_code==401
assert '/admin/vpn/trial7-auto/<int:device_row_id>' in [rule.rule for rule in app.url_map.iter_rules()]
print('Staged dashboard, annual license, CSRF, VPN and admin diagnostics passed')
"""
    result = subprocess.run([str(python), "-c", program], env=test_env, cwd=stage,
                            user=account.pw_uid, group=account.pw_gid, extra_groups=[],
                            capture_output=True, text=True, timeout=100)
    # Intentionally withhold logs: service imports may print private details.
    require(result.returncode == 0, "Staging-Test fehlgeschlagen. Live-System unverändert; lokale Prüfung erforderlich.")
    after = hash_protected(test_db_dir / "provisioning.db")
    require(all(after.get(table) == original for table, original in before.items()),
            "Staging-Test würde bestehende Kunden-/Lizenz-/VPN-Daten verändern.")
    # New additive tables (vpn_trials, annual_device_licenses, etc.) are
    # intentionally allowed on the staging copy, never the live DB in --check.

def health():
    with urllib.request.urlopen("http://127.0.0.1:8787/v1/license/capabilities", timeout=5) as response:
        caps = json.load(response)
        require(caps.get("annual_license_ready") is True and caps.get("annual_days") == 365,
                "Server meldet keine einsatzbereite Jahreslizenz.")
    for path in ("/health", "/admin/diagnostics", "/v1/device/vpn/status"):
        opener = urllib.request.build_opener(NoRedirect())
        try:
            with opener.open("http://127.0.0.1:8787" + path, timeout=5) as response:
                code = response.status
        except urllib.error.HTTPError as exc:
            code = exc.code
        expected = 200 if path == "/health" else (401 if path == "/v1/device/vpn/status" else 302)
        require(code == expected, "Endpoint nicht bereit: " + path)

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
    print("Dashboard-Lizenzen aktiv. Android 1.0.64 bleibt ein eigener, noch freizugebender Testbuild.")

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
