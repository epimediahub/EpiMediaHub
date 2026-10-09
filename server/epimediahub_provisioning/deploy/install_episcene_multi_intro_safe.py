#!/usr/bin/env python3
"""Three-way, fail-closed EpiScene dual-intro overlay for the LIVE independent-playlists Hetzner build.

check: offline stage + strict compatibility validation; no production changes.
apply: same checks, SQLite-consistent backup, natural idle wait and reversible restart.
No live provider credentials are fetched or logged. No queues/markers are reset.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

BASE = Path("/opt/epimediahub/provisioning")
OLD = "033271aaab94554652af866f4dadd0f06ec4d89f"
NEW = "356478005316c5dd40f6739bd8f25ce1c525d8ab"
FILES = (
    "skip_markers.py", "skip_automation.py", "skip_release.py",
    "skip_scene.py", "templates/skip_markers.html",
)
EXPECTED = (
    "bdbf0f9c7638396bfda4e0b0a260e8ee400771f833b8d8a9e74679cd3bf9e8c4",
    "227ece60a9a6fb633ddaf7d4ead0d9dbc4807a922554b44c294a45fc44014e24",
    "73b60544185e687953e20478832da39e30f31284566e88dd994e34de7e4399a0",
    "fe29ff124925901e6649de6621048384b81e3fdb0c4598a4e86cbb84e5c4b2d8",
    "02091c733944a4315006fc15a99c9bbd6b91ffdc02323c36075a815da443e853",
)
HELPER = "skip_intro_sections.py"
ORIGIN = "https://raw.githubusercontent.com/epimediahub/EpiMediaHub"


def run(*args, check=True):
    return subprocess.run(args, text=True, capture_output=True, check=check)


def active(name):
    return run("systemctl", "is-active", "--quiet", name, check=False).returncode == 0


def require(ok, detail):
    if not ok:
        raise RuntimeError(detail)


def fetch(ref, file):
    url = f"{ORIGIN}/{ref}/server/epimediahub_provisioning/{file}"
    with urlopen(url, timeout=40) as response:
        require(response.status == 200, f"Download failed: {file}")
        return response.read()


def db_path():
    directory = os.getenv("EPIMEDIAHUB_DATA_DIR", "/var/lib/epimediahub")
    envfile = Path("/etc/epimediahub/provisioning.env")
    if envfile.exists():
        import shlex
        for line in envfile.read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "EPIMEDIAHUB_DATA_DIR":
                values = shlex.split(value, comments=True)
                require(len(values) == 1 and Path(values[0]).is_absolute(),
                        "Invalid data directory in provisioning.env")
                directory = values[0]
    return Path(directory) / "provisioning.db"


def stage(work):
    require(BASE.is_dir() and (BASE / ".venv/bin/python").is_file(),
            "Actual Hetzner controller installation not found")
    require(not (BASE / HELPER).exists(),
            "Intro patch already present; no duplicate deployment")
    for name in ("skip_analysis_playlists.py", "skip_daily_reports.py",
                 "templates/skip_analysis_playlists.html",
                 "templates/skip_daily_report_launcher.html"):
        require((BASE / name).is_file(), f"Existing live feature missing: {name}")
    staged = {}
    print("Pruefe aktive Versionen und fuehre Aenderungen sicher zusammen ...", flush=True)
    for file, digest in zip(FILES, EXPECTED):
        live = (BASE / file).read_bytes()
        require(hashlib.sha256(live).hexdigest() == digest,
                f"{file} changed since diagnostic snapshot. No changes made.")
        current = work / "live" / file
        baseline = work / "baseline" / file
        proposed = work / "proposed" / file
        merged = work / "merged" / file
        for location in (current, baseline, proposed, merged):
            location.parent.mkdir(parents=True, exist_ok=True)
        current.write_bytes(live)
        baseline.write_bytes(fetch(OLD, file))
        proposed.write_bytes(fetch(NEW, file))
        result = run("diff3", "-m", "-L", f"LIVE:{file}",
                     "-L", f"OLD:{file}", "-L", f"NEW:{file}",
                     str(current), str(baseline), str(proposed), check=False)
        require(result.returncode == 0,
                f"Merge conflict in {file}: no live changes made. "
                "The independently updated module needs a targeted manual merge.")
        require(not re.search(r"(?m)^(<<<<<<<|=======|>>>>>>>)", result.stdout),
                f"Unresolved merge conflict: {file}")
        merged.write_text(result.stdout)
        staged[file] = merged

    helper = work / "merged" / HELPER
    helper.write_bytes(fetch(NEW, HELPER))
    staged[HELPER] = helper
    source = {name: path.read_text() for name, path in staged.items()}
    for key, required in {
        "skip_markers.py": ("skip_analysis_playlists", "skip_intro_roles", "def v152_intro_role"),
        "skip_automation.py": ("skip_analysis_playlists", "def protected(", "section=None"),
        "skip_release.py": ("skip_analysis_playlists", "section_groups"),
        "skip_scene.py": ("from skip_intro_sections import overlaps",),
        "templates/skip_markers.html": ("skip_analysis_playlists.html",
              "skip_daily_report_launcher.html", "intro_role"),
    }.items():
        for token in required:
            require(token in source[key], f"{key} lost required feature {token!r}")
    for name in FILES[:4] + (HELPER,):
        ast.parse(source[name], filename=name)
    for name, defs in {
        "skip_markers.py": {"migrate", "review_record", "marker_browser", "install"},
        "skip_automation.py": {"protected", "retire_proposals", "store_proposal"},
        "skip_release.py": {"approve_rows", "accept_pending"},
        "skip_scene.py": {"_compare"},
    }.items():
        known = {node.name for node in ast.parse(source[name]).body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        require(defs.issubset(known), f"{name} missing expected definitions")
    print("OK: unabh. Analyse-Playlists, Tagesbericht und neue Intro-Logik in Patch enthalten.",
          flush=True)
    return staged


def apply(staged):
    require(active("epimediahub-provisioning.service"),
            "Dashboard service inactive; installation refused")
    report_timer = "epimediahub-episcene-report.timer"
    require(active(report_timer), "Daily-report timer inactive; installation refused")
    backup = BASE / "backups" / ("multi-intro-" + time.strftime("%Y%m%d-%H%M%S"))
    backup.mkdir(parents=True, exist_ok=False)
    for name in FILES:
        dest = backup / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BASE / name, dest)
    for name in ("skip_analysis_playlists.py", "skip_daily_reports.py",
                 "templates/skip_analysis_playlists.html",
                 "templates/skip_daily_report_launcher.html"):
        dest = backup / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BASE / name, dest)
    database = db_path()
    require(database.is_file(), f"DB missing: {database}")
    src = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=25)
    try:
        dst = sqlite3.connect(backup / "provisioning.db")
        try:
            src.backup(dst, pages=500)
        finally:
            dst.close()
    finally:
        src.close()
    print(f"Gesicherte Originale und Datenbank: {backup}", flush=True)

    timer = "epimediahub-skip-analysis.timer"
    worker = "epimediahub-skip-analysis.service"
    timer_active = active(timer)
    files_changed = False
    try:
        if timer_active:
            run("systemctl", "stop", timer)
        print("Warte auf natuerliches Ende des aktuellen Analysejobs ...", flush=True)
        deadline = time.monotonic() + 360
        while active(worker) and time.monotonic() < deadline:
            time.sleep(2)
        require(not active(worker),
                "Analysis still busy. No files changed; timer will be restored.")
        files_changed = True
        for name, prepared in staged.items():
            dest = BASE / name
            tmp = dest.with_name("." + dest.name + ".multi-intro-tmp")
            shutil.copy2(prepared, tmp)
            os.chmod(tmp, 0o644)
            os.replace(tmp, dest)
        run("systemctl", "restart", "epimediahub-provisioning.service")
        require(active("epimediahub-provisioning.service"), "Dashboard restart failed")
        with urlopen("http://127.0.0.1:8787/health", timeout=20) as response:
            health = json.load(response)
        require(health.get("status") == "ok", "Dashboard health check failed")
        require(active(report_timer), "Daily report timer stopped")
        print("INSTALLIERT: EpiScene Mehrfach-Intros aktiv; Backup: " + str(backup),
              flush=True)
    except Exception:
        if files_changed:
            print("ROLLBACK: restoring the old live Python files and dashboard.", flush=True)
            for name in FILES:
                shutil.copy2(backup / name, BASE / name)
            (BASE / HELPER).unlink(missing_ok=True)
            run("systemctl", "restart", "epimediahub-provisioning.service",
                check=False)
        raise
    finally:
        if timer_active:
            run("systemctl", "start", timer, check=False)


def main():
    require(os.geteuid() == 0, "Root required")
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    require(mode in {"check", "apply"}, "Use check or apply")
    require(shutil.which("diff3") is not None, "diffutils (diff3) required")
    with tempfile.TemporaryDirectory(prefix="epi-multi-intro-") as temporary:
        staged = stage(Path(temporary))
        if mode == "check":
            print("VORPRUEFUNG OK. Noch keine Produktionsdateien oder Dienste veraendert.")
        else:
            apply(staged)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ABBRUCH OHNE BLINDES UEBERSCHREIBEN:", exc, file=sys.stderr)
        sys.exit(1)
