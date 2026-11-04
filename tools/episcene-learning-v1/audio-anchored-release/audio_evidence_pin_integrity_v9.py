#!/usr/bin/env python3
"""V9 read-only diagnosis of missing EpiScene audio cache pointers and pinning.

Existing V8 makes consistent SQLite snapshots before launching a restricted
systemd sandbox. This script reuses that mechanism, without source writes,
network access, media downloads, approval actions, or worker restarts.

Goal: distinguish evidence pointers that no longer refer to cached rows
from a retention-policy issue. Does not assume missing means pruned.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import os
from pathlib import Path
import re
import sqlite3
import sys

HERE=Path(__file__).resolve().parent
if (not (HERE/"audio_missing_cache_root_cause_v8.py").is_file() or
        (HERE/"audio_missing_cache_root_cause_v8.py").is_symlink()):
    raise RuntimeError("STOP: read-only V8 helper missing")
sys.path.insert(0,str(HERE))
import audio_missing_cache_root_cause_v8 as v8
base=v8.base

MAX_ROWS=15000


def pinned_keys_from_pending(con):
    """Mirror pinned-retention key extraction, but do not mutate/retain."""
    rows=con.execute("""SELECT r.segment_type,e.evidence_json
                        FROM skip_records r
                        LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
                        WHERE r.status='pending'""").fetchall()
    if len(rows)>MAX_ROWS:
        raise RuntimeError("STOP: too many pending records")
    pins=set()
    flags=Counter()
    for kind,raw in rows:
        if raw is None:
            flags["pending_rows_without_evidence"]=1+flags["pending_rows_without_evidence"]
            continue
        try:
            ev=base.as_json(raw)
        except Exception:
            flags["pending_invalid_evidence"]+=1
            continue
        # If malformed JSON is passed to as_json() it becomes {}, so this
        # check is intentionally not proof that the installed helper accepts it.
        windows=ev.get("windows")
        if windows is None:
            flags["pending_rows_without_windows_list"]+=1
            continue
        if not isinstance(windows,list):
            flags["pending_invalid_windows_list"]+=1
            continue
        for w in windows[:64]:
            if not isinstance(w,dict):
                flags["pending_invalid_window_item"]+=1
                continue
            if w.get("origin","server")!="server":
                continue
            key=w.get("asset_key")
            if not isinstance(key,str) or not key:
                flags["pending_server_window_without_key"]+=1
                continue
            pins.add((key,kind))
    return pins,flags


def evidence_pointer_availability(con,record):
    """Check every referenced server pointer: kind+key, then full metadata."""
    fields=base.as_json(record["evidence_json"]).get("windows")
    counts=Counter()
    if not isinstance(fields,list):
        return Counter({"NO_VALID_WINDOW_LIST":1})
    for window in fields[:64]:
        if not isinstance(window,dict) or window.get("origin","server")!="server":
            continue
        key=window.get("asset_key")
        if not isinstance(key,str) or not key:
            counts["SERVER_POINTER_NO_ASSET_KEY"]+=1
            continue
        cache=con.execute("""SELECT kind,duration_ms,offset_ms,length_ms,step_ms
            FROM skip_auto_windows
            WHERE asset_key=? AND kind=? ORDER BY created_at DESC LIMIT 1""",
            (key,record["segment_type"])).fetchone()
        position=("OWN" if key==record["asset_key"] else "OTHER")
        if cache is None:
            counts[position+"_POINTER_CACHE_ROW_MISSING"]+=1
            continue
        counts[position+"_POINTER_CACHE_ROW_PRESENT"]+=1
        required=("duration_ms","offset_ms","length_ms","step_ms")
        if all(window.get(field)==cache[field] for field in required):
            counts[position+"_POINTER_CACHE_METADATA_MATCH"]+=1
        else:
            counts[position+"_POINTER_CACHE_METADATA_DIFFERENT"]+=1
    return counts


def retention_status(path,count):
    """A code signature is not proof of a running scheduled prune."""
    kind=v8.installed_retention_mode(path)
    details=Counter()
    if kind!="PINNED_CACHE_RETENTION_HELPER_PRESENT":
        return kind,details
    if path.is_symlink() or not path.is_file() or path.stat().st_size>2_000_000:
        return "INVALID_SOURCE",details
    source=path.read_text(encoding="utf-8",errors="replace")
    # Verify call exists OUTSIDE the def declaration, not merely text presence.
    calls=len(re.findall(r"(?m)^\s*episcene_prune_audio_window_cache\s*\(",source))
    details["retention_helper_calls_in_source"]=calls
    details["below_8704_cache_cleanup_trigger"]=int(count<=8192+512)
    return kind,details


def diagnose(con,feedback):
    refs,_=base.select_references(feedback,con)
    index=base.reference_index(refs)
    rows=con.execute(base.SQL).fetchall()
    if len(rows)>MAX_ROWS:
        raise RuntimeError("STOP: too many source records")
    cohorts=defaultdict(list)
    for record in rows:
        if base.valid_asset(record):
            k=(record["playlist_id"],record["source_key"],
               record["season"],record["segment_type"])
            cohorts[k].append(record)
    pins,pin_flags=pinned_keys_from_pending(con)
    totals=Counter()
    scope=[]
    for key,records in base.prioritize_manual_cohorts(cohorts,index):
        if key not in index:
            continue
        targets=[r for r in records if r["status"]=="pending" and base.audio_confirmed(r)]
        if not targets:
            continue
        per=Counter()
        for row in targets[:32]:
            per["PENDING_AUDIO"]+=1
            if base.is_protected(con,row):
                per["EXPLICIT_PROTECTED_RECORD"]+=1
                continue
            issue=v8.window_reason(con,row)
            per[issue]+=1
            if issue=="NO_STORED_CACHE_FOR_EPISODE_SEGMENT":
                per["MISSING_CACHE_KEY_IS_PINNED_BY_PENDING_EVIDENCE"
                    if (row["asset_key"],row["segment_type"]) in pins
                    else "MISSING_CACHE_KEY_NOT_PINNED_BY_PENDING_EVIDENCE"]+=1
            per.update(evidence_pointer_availability(con,row))
        totals.update(per)
        scope.append((per,key[0],key[2],key[3]))
    return totals,scope,pin_flags,len(pins)


def launcher():
    """Snapshot both databases and invoke V9 itself in a restricted service."""
    import tempfile
    import subprocess
    if not v8.shutil.which("systemd-run"):
        raise SystemExit("STOP: systemd sandbox missing")
    if not base.PYTHON.is_file() or not os.access(base.PYTHON,os.X_OK):
        raise SystemExit("STOP: trusted provisioning Python missing")
    with tempfile.TemporaryDirectory(prefix="episcene_fp_shadow_",dir="/tmp") as d:
        snapshot=Path(d)/"snapshot.db"
        feedback=Path(d)/"feedback.db"
        base.snapshot_readonly_sqlite(base.DB,snapshot)
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
        for prop in props: cmd.extend(("-p",prop))
        cmd.extend((
            "--setenv=EPISCENE_FP_SHADOW=YES",
            "--setenv=EPISCENE_FP_SNAPSHOT="+str(snapshot),
            "--setenv=EPISCENE_FEEDBACK_SNAPSHOT="+str(feedback),
            str(base.PYTHON),"-I","-B",str(Path(__file__).resolve()),
        ))
        print("V9: Protected SQLite copies, no approvals.",flush=True)
        rc=subprocess.run(cmd,check=False).returncode
        if rc: raise SystemExit(f"STOP: sandbox diagnostic failed exit={rc}")


def audit():
    snapshot=Path(os.environ.get("EPISCENE_FP_SNAPSHOT",""))
    if (snapshot.is_symlink() or not snapshot.is_file()
            or not str(snapshot).startswith("/tmp/")):
        raise RuntimeError("STOP: invalid snapshot path")
    feedback_path=base.shadow_feedback_snapshot_path(
        os.environ.get("EPISCENE_FEEDBACK_SNAPSHOT",""),snapshot)
    with base.open_ro(snapshot) as con,base.open_ro(feedback_path) as fb:
        totals,cohorts,pin_flags,pin_count=diagnose(con,fb)
        cache_count=con.execute(
            "SELECT COUNT(*) FROM skip_auto_windows").fetchone()[0]
    status,retention=retention_status(base.APP/"skip_automation.py",cache_count)
    print("EPISCENE V9 – CACHE POINTER / RETENTION INTEGRITY, READ ONLY")
    print("Current cache windows:",cache_count)
    print("Installed retention source signature:",status)
    print("Known pending evidence pin keys:",pin_count)
    print("RETENTION CHECK")
    for name,value in sorted(retention.items()):
        print(f"  {name}: {value}")
    print("V9 AGGREGATE")
    for name,value in sorted(totals.items()):
        if value:print(f"  {name}: {value}")
    if pin_flags:
        print("PENDING EVIDENCE FORM")
        for name,value in sorted(pin_flags.items()):
            if value: print(f"  {name}: {value}")
    print("No changes, no downloads, no approvals, no worker restart.")
    print("Missing cache row does NOT establish whether it was deleted or never created.")


if __name__=="__main__":
    if os.environ.get("EPISCENE_FP_SHADOW")=="YES":
        audit()
    else:
        launcher()
