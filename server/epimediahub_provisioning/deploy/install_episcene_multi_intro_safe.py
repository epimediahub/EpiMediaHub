#!/usr/bin/env python3
"""Three-way, fail-closed EpiScene dual-intro overlay for the LIVE independent-playlists Hetzner build.

check: offline stage + strict compatibility validation; no production changes.
apply: same checks, SQLite-consistent backup, natural idle wait and reversible restart.
No live provider credentials are fetched or logged. No queues/markers are reset.
"""
import ast
import difflib
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


def busy(name):
    state = run("systemctl", "show", "--property=ActiveState", "--value",
                name, check=False).stdout.strip()
    # is-active alone does not reliably cover a starting oneshot worker.
    return state in {"active", "activating", "deactivating", "reloading"}


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


def _occurrences(lines, block):
    if not block:
        return list(range(len(lines) + 1))
    size = len(block)
    return [idx for idx in range(len(lines) - size + 1)
            if lines[idx:idx+size] == block]


def transplant(old_source, new_source, live_source, file):
    """Cherry-pick exact old->new hunks into an independently modified live file.

    Unlike diff3 this preserves concurrent edits *near* an unchanged anchor.
    Each changed old block must occur uniquely or have a unique context match.
    Ambiguity and changed source anchors always fail closed.
    """
    old = old_source.splitlines(keepends=True)
    new = new_source.splitlines(keepends=True)
    live = live_source.splitlines(keepends=True)
    changed = [(tag,a,b,c,d) for tag,a,b,c,d in
               difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
               if tag != 'equal']
    require(len(changed) <= 80, f"{file}: unexpected number of modifications")
    for tag, a, b, c, d in reversed(changed):
        prior = old[a:b]
        replacement = new[c:d]
        options = _occurrences(live, prior)
        if not options:
            raise RuntimeError(f"{file}: original changed at source lines {a+1}-{b}; "
                               "independent functionality touched this exact block")
        # Score candidate insertion/replacement locations against both unchanged
        # sides of the original. No character-level fuzzy or heuristic rewriting.
        scored = []
        for idx in options:
            left = 0
            while (left < min(6,a,idx)
                   and live[idx-left-1] == old[a-left-1]):
                left += 1
            right = 0
            while (right < min(6,len(old)-b,len(live)-(idx+len(prior)))
                   and live[idx+len(prior)+right] == old[b+right]):
                right += 1
            scored.append((left+right, min(left,right), idx))
        scored.sort(reverse=True)
        score, balance, idx = scored[0]
        if len(scored) > 1:
            nxt = scored[1]
            require((score,balance) > (nxt[0],nxt[1]) and score > 0,
                    f"{file}: ambiguous change at old line {a+1}: "
                    f"{len(options)} possible anchors")
        if not prior:
            require(score > 0, f"{file}: insertion has no proven source anchor")
        live[idx:idx+len(prior)] = replacement
    result = ''.join(live)
    require('<<<<<<<' not in result and '>>>>>>>' not in result,
            f"{file}: conflict markers in generated result")
    return result


def selftest():
    """Exercise exact feature recreation and independent additions for all files."""
    for file in FILES:
        original = fetch(OLD,file).decode()
        feature = fetch(NEW,file).decode()
        result = transplant(original,feature,original,file)
        require(result == feature, f"{file}: patch did not recreate approved feature")
        # Emulate unrelated preexisting user modifications, including the live
        # independent-playlist foreign keys on the real Hetzner controller.
        sentinel = '# preserved-independent-playlists\n' if file.endswith('.py') else '<!-- preserved-independent-playlists -->\n'
        simulated = sentinel + original.replace(
            "REFERENCES customer_playlists(id)", "REFERENCES skip_analysis_playlists(id)")
        patched = transplant(original,feature,simulated,file)
        require(sentinel in patched, f"{file}: lost existing independent code")
        require("REFERENCES customer_playlists(id)" not in patched or
                "REFERENCES customer_playlists(id)" in feature,
                f"{file}: old customer-playlist schema restored unexpectedly")
        if file.endswith(".py"):
            ast.parse(patched)
        print(f"OK targeted cherry-pick: {file}",flush=True)
    print("Transplant self-test passed.",flush=True)


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
        merged.write_text(transplant(
            baseline.read_text(), proposed.read_text(), live.decode(), file))
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
        while busy(worker) and time.monotonic() < deadline:
            time.sleep(2)
        require(not busy(worker),
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
        health = {}
        for _ in range(10):
            try:
                with urlopen("http://127.0.0.1:8787/health", timeout=5) as response:
                    health = json.load(response)
                if health.get("status") == "ok":
                    break
            except Exception:
                time.sleep(2)
        require(health.get("status") == "ok", "Dashboard health check failed")
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as check:
            tables = {r[0] for r in check.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        require({"skip_intro_roles", "skip_records", "skip_analysis_playlists"} <= tables,
                "New intro-role schema or independent playlist schema not initialized")
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
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    require(mode in {"check", "apply", "selftest"}, "Use check, apply or selftest")
    if mode == "selftest":
        selftest()
        return
    require(os.geteuid() == 0, "Root required")
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
