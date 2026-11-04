#!/usr/bin/env python3
"""EpiScene V8: investigate missing cached audio for historical user markers.

No releases, no downloads, no worker changes. Existing production/feedback
databases are backed up with SQLite's online backup API, then read ONLY inside
the same restricted systemd-run sandbox as V7.

A missing row is NOT proof of pruning: classify the actual evidence before
considering a separate guarded retention/backfill fix.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import sys

HERE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
if not (HERE/"fingerprint_manual_gate_audit_v7.py").is_file() or (
        HERE/"fingerprint_manual_gate_audit_v7.py").is_symlink():
    raise RuntimeError("V7 module missing or symlink")
sys.path.insert(0,str(HERE))
import fingerprint_manual_gate_audit_v7 as base

MAX_SCAN=15000


def launcher():
    if not shutil.which("systemd-run"):
        raise SystemExit("STOP: systemd sandbox is missing")
    if not base.PYTHON.is_file() or not os.access(base.PYTHON,os.X_OK):
        raise SystemExit("STOP: provisioning Python unavailable")
    with tempfile.TemporaryDirectory(prefix="episcene_fp_shadow_",dir="/tmp") as d:
        snap=Path(d)/"snapshot.db"
        feedback=Path(d)/"feedback.db"
        base.snapshot_readonly_sqlite(base.DB,snap)
        base.snapshot_readonly_sqlite(base.FEEDBACK,feedback)
        props=(
            "PrivateNetwork=yes","ProtectSystem=strict","ReadWritePaths=/tmp",
            "ProtectHome=yes","NoNewPrivileges=yes","CapabilityBoundingSet=",
            "PrivateDevices=yes","ProtectKernelTunables=yes",
            "ProtectKernelModules=yes","ProtectControlGroups=yes",
            "RestrictAddressFamilies=AF_UNIX","TemporaryFileSystem=/run",
            "PrivateTmp=no","MemoryMax=1G","CPUQuota=100%","RuntimeMaxSec=180s",
        )
        cmd=["systemd-run","--pipe","--wait","--collect"]
        for item in props: cmd.extend(("-p",item))
        cmd.extend((
            "--setenv=EPISCENE_FP_SHADOW=YES",
            "--setenv=EPISCENE_FP_SNAPSHOT="+str(snap),
            "--setenv=EPISCENE_FEEDBACK_SNAPSHOT="+str(feedback),
            str(base.PYTHON),"-I","-B",str(Path(__file__).resolve())
        ))
        print("V8: 2 geschuetzte SQLite-Kopien; nur Cache-Diagnose.",flush=True)
        ret=subprocess.run(cmd,check=False).returncode
        if ret:
            raise SystemExit("STOP: readonly sandbox failed exit="+str(ret))


def installed_retention_mode(source):
    """Inspect a local source signature only; never import/execute it."""
    if source.is_symlink() or not source.is_file():
        return "SOURCE_NOT_AVAILABLE"
    if source.stat().st_size>2_000_000:
        return "SOURCE_TOO_LARGE"
    text=source.read_text(encoding="utf-8",errors="replace")
    if "episcene_prune_audio_window_cache" in text:
        return "PINNED_CACHE_RETENTION_HELPER_PRESENT"
    if ("DELETE FROM skip_auto_windows WHERE rowid NOT IN" in text
            and "LIMIT 256" in text):
        return "LEGACY_256_ROW_PRUNER_PRESENT"
    return "UNKNOWN_RETENTION_LOGIC"


def window_reason(con,row):
    key=row["asset_key"]
    kind=row["segment_type"]
    duration=row["asset_duration_ms"]
    exact=con.execute("""SELECT COUNT(*) FROM skip_auto_windows
                 WHERE asset_key=? AND kind=? AND duration_ms=?""",
                      (key,kind,duration)).fetchone()[0]
    if exact:
        return "EXACT_CACHE_EXISTS_UNEXPECTED"
    same_kind=con.execute("""SELECT COUNT(*) FROM skip_auto_windows
                 WHERE asset_key=? AND kind=?""",(key,kind)).fetchone()[0]
    if same_kind:
        return "SAME_ASSET_AND_KIND_BUT_OLD_DURATION"
    other_kind=con.execute("""SELECT COUNT(*) FROM skip_auto_windows
                 WHERE asset_key=?""",(key,)).fetchone()[0]
    if other_kind:
        return "SAME_ASSET_ONLY_OTHER_SEGMENT_TYPE"
    alt=con.execute("""SELECT COUNT(*) FROM skip_auto_windows w
                 JOIN skip_assets a ON a.asset_key=w.asset_key
                 WHERE a.playlist_id=? AND a.source_key=?
                   AND a.season=? AND a.episode=? AND w.kind=?
                   AND w.asset_key<>?""",
                 (row["playlist_id"],row["source_key"],row["season"],
                  row["episode"],kind,key)).fetchone()[0]
    if alt:
        return "SAME_EPISODE_OTHER_ASSET_VERSION_HAS_CACHE"
    return "NO_STORED_CACHE_FOR_EPISODE_SEGMENT"


def evidence_window_counts(row):
    payload=base.as_json(row["evidence_json"])
    items=payload.get("windows")
    if not isinstance(items,list):return Counter({"EVIDENCE_NO_WINDOWS_LIST":1})
    out=Counter()
    if not items:
        return Counter({"EVIDENCE_EMPTY_WINDOWS_LIST":1})
    for item in items[:64]:
        if not isinstance(item,dict):
            out["EVIDENCE_INVALID_WINDOW_ITEM"]+=1
        elif item.get("origin","server")!="server":
            out["EVIDENCE_NON_SERVER_WINDOW"]+=1
        elif item.get("asset_key")==row["asset_key"]:
            out["EVIDENCE_HAS_OWN_SERVER_WINDOW_POINTER"]+=1
        elif isinstance(item.get("asset_key"),str) and item["asset_key"]:
            out["EVIDENCE_HAS_OTHER_SERVER_WINDOW_POINTER"]+=1
        else:
            out["EVIDENCE_SERVER_POINTER_MISSING_ASSET"]+=1
    return out


def investigate(con,fb):
    refs,_=base.select_references(fb,con)
    reference_index=base.reference_index(refs)
    rows=con.execute(base.SQL).fetchall()
    if len(rows)>MAX_SCAN:
        raise RuntimeError("STOP: too many skip records")
    cohort=defaultdict(list)
    for row in rows:
        if base.valid_asset(row):
            k=(row["playlist_id"],row["source_key"],
               row["season"],row["segment_type"])
            cohort[k].append(row)
    totals=Counter()
    by_cohort=[]
    asset_cols=base._columns(con,"skip_assets") if hasattr(base,"_columns") else {
        r[1] for r in con.execute("PRAGMA table_info(skip_assets)")}
    for key,records in base.prioritize_manual_cohorts(cohort,reference_index):
        if key not in reference_index:continue
        candidates=[r for r in records if r["status"]=="pending" and base.audio_confirmed(r)]
        if not candidates:continue
        local=Counter()
        for row in candidates[:32]:
            local["PENDING_AUDIO_CANDIDATES"]+=1
            if base.is_protected(con,row):
                local["PROTECTED_REQUIRES_REVIEW"]+=1
                continue
            usable_refs=[
                ref for ref in reference_index[key]
                if ref.episode!=row["episode"] and not base.anchor_is_blocked(con,ref)
            ]
            local["HAS_UNBLOCKED_TRUSTED_REFERENCE"]+=int(bool(usable_refs))
            local["HAS_UNBLOCKED_DIRECT_USER_REFERENCE"]+=int(any(
                ref.is_user_marker for ref in usable_refs))
            local["HAS_UNBLOCKED_ADMIN_REVIEWED_REFERENCE"]+=int(any(
                not ref.is_user_marker for ref in usable_refs))
            local[window_reason(con,row)]+=1
            local.update(evidence_window_counts(row))
        totals.update(local)
        name=base.safe_title(con,candidates[0]["asset_key"],asset_cols)
        by_cohort.append((name or "anonymisierte Serie",key[0],key[2],key[3],local))
    return totals,by_cohort


def audit():
    snapshot=Path(os.environ.get("EPISCENE_FP_SNAPSHOT",""))
    if (not snapshot.is_file() or snapshot.is_symlink()
            or not str(snapshot).startswith("/tmp/")):
        raise RuntimeError("STOP: untrusted provisioning snapshot")
    raw=os.environ.get("EPISCENE_FEEDBACK_SNAPSHOT","")
    feedback_path=base.shadow_feedback_snapshot_path(raw,snapshot)
    with base.open_ro(snapshot) as con,base.open_ro(feedback_path) as fb:
        totals,groups=investigate(con,fb)
        cache_total=con.execute("SELECT COUNT(*) FROM skip_auto_windows").fetchone()[0]
    retention=installed_retention_mode(base.APP/"skip_automation.py")
    print("EPISCENE V8 – FEHLENDE AUDIO-CACHE-FENSTER / READ ONLY")
    print("Installierte Cache-Retention (Quelltext-Signatur):",retention)
    print("Audio-Cache-Fenster insgesamt:",cache_total)
    print("BETROFFENE REFERENZGRUPPEN")
    for name,pid,season,kind,counts in groups:
        playlist={8:"4K ANALYSE",10:"THE BEST"}.get(pid,"andere")
        print(f"  {playlist} | {name} | S{season} {kind}")
        for reason,value in sorted(counts.items()):
            if value:print(f"    {reason}: {value}")
    print("V8 AGGREGATE")
    for reason,value in sorted(totals.items()):
        if value: print(f"  {reason}: {value}")
    print("Missing != proven pruned. No downloads, approvals, or worker changes.")


if __name__=="__main__":
    if os.environ.get("EPISCENE_FP_SHADOW")=="YES":
        audit()
    else:
        launcher()
