#!/usr/bin/env python3
"""EpiScene: isolated A/B test for one visual fingerprint grouping parameter.

A = current installed visual detector (unchanged).
B = same detector, but adjacent fingerprint matches may be separated by
    two instead of one missing sample (np.diff(matched) > 2 -> > 3).

Both arms retain the original minimum duration, match ratio, diversity,
boundary rules, peer consensus, and output status thresholds.
NO approvals, production DB writes, media downloads, or worker restarts.
Only aggregated results leave the isolated service.
"""
from __future__ import annotations

import collections
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
APP = Path("/opt/epimediahub/provisioning")
COMPUTE = Path("/opt/epimediahub/analysis")
DB = Path("/var/lib/epimediahub/provisioning.db")
PYTHON = APP / ".venv/bin/python"
MAX_PER_PLAYLIST_AND_KIND = 6
NEEDLE = "np.flatnonzero(np.diff(matched) > 2)"
REPLACEMENT = "np.flatnonzero(np.diff(matched) > 3)"

SQL = """
SELECT r.*, e.evidence_json, a.playlist_id
FROM skip_records r
JOIN skip_assets a ON a.asset_key=r.asset_key
LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
WHERE r.status='pending' AND a.playlist_id IN (8,10)
  AND r.source IN ('audio','chapter','theintrodb','audio_repetition','auto_audio','episcene')
  AND COALESCE(e.human_review,0)=0
  AND a.source_key=r.source_key AND a.media_type=r.media_type
  AND a.season=r.season AND a.episode=r.episode
  AND a.duration_ms>0 AND ABS(a.duration_ms-r.duration_ms)<=2000
ORDER BY a.playlist_id, r.segment_type, r.id DESC
"""


def launch_isolated():
    if not shutil.which("systemd-run"):
        raise SystemExit("ABBRUCH: systemd-run fehlt. Kein unisolierter Ersatz.")
    for path in (DB, PYTHON, APP / "skip_scene.py", APP / "skip_release.py",
                 COMPUTE / "skip_visual.py"):
        if not path.is_file() or path.is_symlink():
            raise SystemExit("ABBRUCH: Datei fehlt oder Symlink: " + str(path))
    with tempfile.TemporaryDirectory(prefix="episcene_visual_ab_", dir="/tmp") as directory:
        snapshot = Path(directory) / "snapshot.db"
        src = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=60)
        dst = None
        try:
            src.execute("PRAGMA query_only=ON")
            dst = sqlite3.connect(snapshot, timeout=60)
            src.backup(dst, pages=2048, sleep=0.1)
        finally:
            src.close()
            if dst is not None:
                dst.close()
        os.chmod(snapshot, 0o600)
        props = (
            "PrivateNetwork=yes", "ProtectSystem=strict", "ReadWritePaths=/tmp",
            "ProtectHome=yes", "NoNewPrivileges=yes", "CapabilityBoundingSet=",
            "PrivateDevices=yes", "ProtectKernelTunables=yes",
            "ProtectKernelModules=yes", "ProtectControlGroups=yes",
            "RestrictAddressFamilies=AF_UNIX", "TemporaryFileSystem=/run",
            "PrivateTmp=no", "MemoryMax=1G", "CPUQuota=100%",
            "RuntimeMaxSec=240s",
        )
        cmd = ["systemd-run", "--pipe", "--wait", "--collect"]
        for prop in props:
            cmd += ["-p", prop]
        cmd += [
            "--setenv=EPISCENE_VISUAL_AB_SANDBOX=YES",
            "--setenv=EPISCENE_VISUAL_AB_SNAPSHOT=" + str(snapshot),
            str(PYTHON), "-I", "-B", str(Path(__file__).resolve())
        ]
        print("A/B-Test auf Datenbankkopie in isoliertem Dienst; keine Freigaben.", flush=True)
        status = subprocess.run(cmd, check=False).returncode
        if status:
            raise SystemExit(f"ABBRUCH: isolierter Test fehlgeschlagen (exit={status}).")


def load_visual(path, name, patch=False):
    """Import the installed detector at its exact path, with one guarded variant."""
    source = path.read_text(encoding="utf-8")
    if source.count(NEEDLE) != 1:
        raise RuntimeError("Unerwarteter Detektor-Code; A/B-Test abgebrochen.")
    if patch:
        source = source.replace(NEEDLE, REPLACEMENT, 1)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot resolve local visual module")
    module = importlib.util.module_from_spec(spec)
    if name in sys.modules:
        raise RuntimeError("Duplicate visual module")
    sys.modules[name] = module
    try:
        if patch:
            exec(compile(source, str(path), "exec"), module.__dict__)
        else:
            spec.loader.exec_module(module)
        if (Path(module.__file__).resolve() != path.resolve()
                or getattr(module, "POLICY", None) != "episcene_visual_v1"
                or not callable(getattr(module, "detect", None))):
            raise RuntimeError("Unexpected visual detector/policy")
    except BaseException:
        del sys.modules[name]
        raise
    return module


def selected_for_visual_only(release, con, row):
    """Replay existing release gates, rolling back any changes on the DB COPY."""
    if row["media_type"] == "episode" and (
            type(row["duration_ms"]) is not int or row["duration_ms"] < 300000):
        return False
    checks = (
        ("source", release.enabled, (con, row["playlist_id"])),
        ("visual", release.scene_release_ready, (con, row)),
        ("reference", release.current_reference, (con, row)),
        ("audio", release.reviewed_release_ready, (row,)),
        ("detector", release.detector_release_ready, (con, row)),
    )
    failed = []
    con.execute("SAVEPOINT visual_ab_gate")
    try:
        for label, fn, args in checks:
            try:
                if not bool(fn(*args)):
                    failed.append(label)
            except Exception:
                failed.append(label + "_error")
    finally:
        con.execute("ROLLBACK TO visual_ab_gate")
        con.execute("RELEASE visual_ab_gate")
    return failed == ["visual"]


def cached_windows(con, scene, row):
    asset = con.execute("SELECT * FROM skip_assets WHERE asset_key=?",
                        (row["asset_key"],)).fetchone()
    if asset is None:
        return None, []
    kind = row["segment_type"]
    own = con.execute("""
        SELECT * FROM skip_scene_windows
        WHERE asset_key=? AND kind=? AND duration_ms=?
        ORDER BY created_at DESC LIMIT 1
    """, (row["asset_key"], kind, asset["duration_ms"])).fetchone()
    if own is None:
        return None, []
    entries = scene._cached_rows(con, asset, kind)
    if entries is None:
        return None, []
    partners = []
    used = {asset["episode"]}
    for cached in entries:
        peer = con.execute("SELECT * FROM skip_assets WHERE asset_key=?",
                           (cached["asset_key"],)).fetchone()
        if peer is None or peer["source_key"] != asset["source_key"]:
            continue
        if peer["season"] != asset["season"] or peer["episode"] in used:
            continue
        if peer["episode"] is None or peer["asset_key"] == asset["asset_key"]:
            continue
        partners.append(scene._window(
            cached, peer, scene._human_markers(con, peer, kind)))
        used.add(peer["episode"])
        if len(partners) == 4:
            break
    return scene._window(own, asset), partners


def classify(module, own, partners, row):
    if own is None:
        return "NO_OWN_WINDOW"
    if not partners:
        return "NO_PEERS"
    result = module.detect(own, partners, row["segment_type"],
                           busy=lambda: False, cache=None)
    if not isinstance(result, dict):
        return "INVALID_RESULT"
    status = result.get("status")
    if status == "NO_MATCH":
        return "NO_MATCH"
    if status == "REVIEW":
        return "REVIEW"
    if status != "AUTO_CONFIRMED":
        return "UNEXPECTED_STATUS"
    start, end = result.get("start_ms"), result.get("end_ms")
    if not (type(start) is int and type(end) is int):
        return "AUTO_INVALID_BOUNDS"
    discrepancy = max(abs(start - row["start_ms"]), abs(end - row["end_ms"]))
    if discrepancy <= 2000:
        return "AUTO_ALIGNED_NOT_RELEASED"
    return "AUTO_DIFFERENT_BOUNDS_NOT_RELEASED"


def run_snapshot():
    raw = os.environ.get("EPISCENE_VISUAL_AB_SNAPSHOT", "")
    snapshot = Path(raw)
    if not raw.startswith("/tmp/") or not snapshot.is_file() or snapshot.is_symlink():
        raise RuntimeError("Untrusted/missing snapshot")
    for path in (COMPUTE / "skip_visual.py", APP / "skip_scene.py",
                 APP / "skip_release.py"):
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("Missing local module")
    source = (COMPUTE / "skip_visual.py").read_bytes()
    # A and B depend on the installed compute source. Fail if code shape differs.
    print("Installed visual SHA256:", hashlib.sha256(source).hexdigest()[:16])
    baseline = load_visual(COMPUTE / "skip_visual.py", "episcene_gap_original")
    variant = load_visual(COMPUTE / "skip_visual.py", "episcene_gap_variant",
                          patch=True)
    sys.path.insert(0, str(APP.resolve()))
    import skip_automation  # noqa: F401 (same patch layer as existing diagnostic)
    import skip_release as release
    import skip_scene as scene
    if Path(scene.__file__).resolve().parent != APP.resolve():
        raise RuntimeError("Unexpected scene module path")
    if Path(release.__file__).resolve().parent != APP.resolve():
        raise RuntimeError("Unexpected release module path")
    # Make a second disposable DB copy; imported code only sees the copy.
    with tempfile.TemporaryDirectory(prefix="episcene_visual_ab_inner_") as temp:
        src = sqlite3.connect(snapshot.resolve().as_uri() + "?mode=ro",
                              uri=True, timeout=60)
        con = sqlite3.connect(str(Path(temp) / "test.db"), timeout=60)
        try:
            src.backup(con)
        finally:
            src.close()
        try:
            con.row_factory = sqlite3.Row
            rows = con.execute(SQL).fetchall()
            chosen = collections.defaultdict(int)
            counts = collections.Counter()
            transitions = collections.Counter()
            evaluated = 0
            for row in rows:
                try:
                    ev = json.loads(row["evidence_json"] or "{}")
                except (ValueError, TypeError):
                    continue
                if not isinstance(ev, dict):
                    continue
                if (ev.get("episcene_required") is not True
                        or ev.get("status") != "AUTO_CONFIRMED"
                        or ev.get("method") == "episcene_consensus"):
                    continue
                bucket = (row["playlist_id"], row["segment_type"])
                if chosen[bucket] >= MAX_PER_PLAYLIST_AND_KIND:
                    continue
                if not selected_for_visual_only(release, con, row):
                    continue
                chosen[bucket] += 1
                evaluated += 1
                # Compare BOTH variants on exactly the same saved peers and frames.
                con.execute("SAVEPOINT visual_ab_detect")
                try:
                    own, peers = cached_windows(con, scene, row)
                    a = classify(baseline, own, peers, row)
                    b = classify(variant, own, peers, row)
                finally:
                    con.execute("ROLLBACK TO visual_ab_detect")
                    con.execute("RELEASE visual_ab_detect")
                counts[(bucket, "A", a)] += 1
                counts[(bucket, "B", b)] += 1
                transitions[(bucket, a, b)] += 1
            print("A/B: A=Original; B=ein fehlendes Sample mehr erlaubt.")
            print("Alle anderen Erkennungsschwellen unveraendert.")
            print("Visual-only Kandidaten geprueft:", evaluated)
            for pid, name in ((8, "4K ANALYSE"), (10, "THE BEST")):
                print("\n" + name)
                for kind in ("intro", "outro"):
                    key = (pid, kind)
                    print(f" {kind}: {chosen[key]} Faelle")
                    for arm in ("A", "B"):
                        parts = [f"{status}={number}" for (k, side, status), number
                                 in sorted(counts.items()) if k == key and side == arm]
                        print(f"   {arm}: " + (", ".join(parts) or "keine"))
                    changed = [(a, b, n) for (k, a, b), n in transitions.items()
                               if k == key and a != b]
                    print("   Veraendert: " +
                          (", ".join(f"{a} -> {b}: {n}" for a, b, n in changed)
                           or "keine"))
            print("\nNUR DIAGNOSE: keine Freigaben, keine Downloads, keine Worker-Aenderungen.")
            print("Ein guenstiger B-Ausgang ist kein Nachweis fuer sichere Freigaben.")
        finally:
            con.close()


if __name__ == "__main__":
    if os.environ.get("EPISCENE_VISUAL_AB_SANDBOX") == "YES":
        run_snapshot()
    else:
        launch_isolated()
