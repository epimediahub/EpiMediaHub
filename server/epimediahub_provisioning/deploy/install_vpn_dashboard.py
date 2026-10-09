#!/usr/bin/env python3
"""Install only the VPN addon and navigation; preserve the installed backend."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import py_compile
import pwd
import re
import secrets
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

ADDON_FILES = ("vpn_dashboard.py", "vpn_autoprovision.py", "templates/vpn_dashboard.html", "static/vpn-dashboard.css", "static/vpn-dashboard.js")
IMPORT = "\n# EpiMediaHub VPN dashboard addon\nfrom vpn_dashboard import install as install_vpn_dashboard\ninstall_vpn_dashboard(app, db)\n"


def load_env(path):
    env = dict(os.environ)
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if sep and re.fullmatch(r"[A-Z_][A-Z0-9_]*", key):
            parsed = shlex.split(value, comments=True)
            if len(parsed) == 1:
                env[key] = parsed[0]
    return env


def patch_navigation(content, url):
    if re.search(r'href=[\'\"]' + re.escape(url) + r'[\'\"]', content):
        return content
    anchor = '<div class="hierarchy-topbar-actions">'
    if content.count(anchor) != 1:
        raise RuntimeError("Dashboard-Navigation hat sich geändert; vorhandene Oberfläche bleibt erhalten.")
    return content.replace(anchor, anchor + f'\n    <a class="button button-ghost" href="{url}">VPN Finnland</a>', 1)


def prepare(base, source, stage):
    for path in base.glob("*.py"):
        shutil.copy2(path, stage / path.name)
    for folder in ("templates", "static"):
        shutil.copytree(base / folder, stage / folder)
    for relative in ADDON_FILES:
        shutil.copy2(source / relative, stage / relative)
    wsgi = stage / "wsgi.py"
    content = wsgi.read_text()
    if not re.search(r"^from vpn_dashboard import install as install_vpn_dashboard$", content, re.M):
        content += IMPORT
    wsgi.write_text(content)
    for filename, url in (("dashboard_v080.html", "/admin/vpn"), ("reseller_dashboard_v080.html", "/reseller/vpn")):
        path = stage / "templates" / filename
        path.write_text(patch_navigation(path.read_text(), url))
    for filename in ("vpn_dashboard.py", "vpn_autoprovision.py", "wsgi.py"):
        py_compile.compile(str(stage / filename), doraise=True)


def verify_stage(stage, env, source_db):
    data = stage / "validation-data"
    data.mkdir()
    with sqlite3.connect(f"file:{source_db}?mode=ro", uri=True) as source, sqlite3.connect(data / "provisioning.db") as target:
        source.backup(target)
    isolated = dict(env, EPIMEDIAHUB_DATA_DIR=str(data), EPIMEDIAHUB_SECURE_COOKIES="0", PYTHONPATH=str(stage))
    check = """
from wsgi import app
app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
c=app.test_client()
assert c.get('/health').status_code == 200
assert c.get('/admin/vpn').status_code == 302
assert c.get('/reseller/vpn').status_code == 302
with c.session_transaction() as s: s['admin']=True
assert c.get('/admin/vpn').status_code == 200
assert c.get('/admin').status_code == 200
print('VPN und bestehendes Admin-Dashboard auf Datenbankkopie geprüft.')
"""
    result = subprocess.run([sys.executable, "-c", check], cwd=stage, env=isolated, capture_output=True, text=True, timeout=60)
    if result.returncode:
        # Do not print copied customer data or environment contents in errors.
        raise RuntimeError("Die Prüfung mit dem installierten Dashboard ist fehlgeschlagen. Keine Änderung am laufenden System.")
    print(result.stdout.strip())


def health_check():
    for attempt in range(10):
        try:
            import json
            with urllib.request.urlopen("http://127.0.0.1:8787/health", timeout=3) as response:
                assert json.load(response).get("status") == "ok"
            # A redirect to login proves that the new route is registered.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args):
                    return None
            try:
                urllib.request.build_opener(NoRedirect()).open("http://127.0.0.1:8787/admin/vpn", timeout=3)
            except urllib.error.HTTPError as error:
                if error.code == 302:
                    return
                raise
        except Exception:
            if attempt == 9:
                raise RuntimeError("Der Server hat die Gesundheitsprüfung nicht bestanden.") from None
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--base", type=Path, default=Path("/opt/epimediahub/provisioning"))
    parser.add_argument("--env", type=Path, default=Path("/etc/epimediahub/provisioning.env"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Bitte mit sudo ausführen.")
    env = load_env(args.env)
    data = Path(env.get("EPIMEDIAHUB_DATA_DIR", "/var/lib/epimediahub"))
    database = data / "provisioning.db"
    if not database.is_file():
        raise SystemExit("Die bestehende Kundendatenbank wurde nicht gefunden.")
    changes = (*ADDON_FILES, "wsgi.py", "templates/dashboard_v080.html", "templates/reseller_dashboard_v080.html")
    backup = args.base / "backups" / ("vpn-dashboard-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3))
    backup.mkdir(parents=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="epi-vpn-dashboard-") as directory:
        stage = Path(directory)
        prepare(args.base, args.source, stage)
        verify_stage(stage, env, database)
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as source, sqlite3.connect(backup / "provisioning.db") as target:
            source.backup(target)
        for relative in changes:
            old = args.base / relative
            if old.exists():
                saved = backup / relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, saved)
        token = data / "vpn-agent.token"
        if not token.exists():
            descriptor = os.open(token, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as output:
                output.write(secrets.token_urlsafe(48) + "\n")
            service_user = pwd.getpwnam("epimediahub")
            os.chown(token, service_user.pw_uid, service_user.pw_gid)
        service_stopped = False
        try:
            subprocess.run(["systemctl", "stop", "epimediahub-provisioning.service"], check=True, timeout=60)
            service_stopped = True
            for relative in changes:
                destination = args.base / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(stage / relative, destination)
                destination.chmod(0o644)
            subprocess.run(["systemctl", "start", "epimediahub-provisioning.service"], check=True, timeout=60)
            health_check()
        except Exception:
            if service_stopped:
                for relative in changes:
                    saved, destination = backup / relative, args.base / relative
                    if saved.exists():
                        shutil.copy2(saved, destination)
                    elif destination.exists():
                        destination.unlink()
                subprocess.run(["systemctl", "restart", "epimediahub-provisioning.service"], check=False, timeout=60)
            print("Update zurückgenommen. Kunden-, Analyse- und Creditdaten wurden nicht zurückgesetzt.", file=sys.stderr)
            raise
    print("Fertig: Admin- und Reseller-Dashboard → VPN Finnland.")
    print("Preise und Tarife im Admin festlegen; öffentliche Geräteschlüssel zuordnen.")
    print("Serverkopplung: den VPN-Agenten anschließend auf dem Finnland-Server installieren.")
    print(f"Kopplungstoken nur privat in der Serverkonsole verwenden: sudo cat {token}")
    print(f"Sicherung: {backup}")


if __name__ == "__main__":
    main()
