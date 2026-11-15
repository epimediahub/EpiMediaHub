#!/usr/bin/env python3
"""Read-only global asset registration and SQL upsert safety audit.

Examines *all* records sharing keys with pending Lincoln Lawyer S4 marks.
No customer/device IDs, titles, keys, URLs, file contents, durations, or
credentials are printed. No provider requests, DB writes or worker restarts.
"""
from __future__ import annotations
import ast
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

DB=Path("/var/lib/epimediahub/provisioning.db")
MARKER=Path("/opt/epimediahub/provisioning/skip_markers.py")
ANALYSIS=Path("/opt/epimediahub/provisioning/skip_analysis.py")
REQUIRED={
 "skip_records":{"asset_key","customer_id","source","status","media_type","title",
                 "season","episode","duration_ms"},
 "skip_assets":{"asset_key","playlist_id","duration_ms","season","episode"},
 "customer_playlists":{"id","customer_id"},
}
MAX_TARGET_KEYS=100
MAX_RECORDS_PER_KEY=2000


def read_only(path=DB):
    if path.is_symlink() or not path.is_file():
        raise ValueError("DB_UNAVAILABLE")
    db=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=8)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    db.execute("BEGIN")
    return db


def parse_iso(raw):
    if not isinstance(raw,str):
        return None
    try:
        stamp=datetime.fromisoformat(raw.replace("Z","+00:00"))
        if stamp.tzinfo is None:
            return None
        return stamp.astimezone(timezone.utc)
    except (OverflowError,ValueError):
        return None


def analyze(db):
    for table,required in REQUIRED.items():
        cols={r["name"] for r in db.execute("PRAGMA table_info("+table+")")}
        if not required <= cols:
            raise ValueError("SCHEMA_MISMATCH_"+table)
    record_cols={r["name"] for r in db.execute("PRAGMA table_info(skip_records)")}
    asset_cols={r["name"] for r in db.execute("PRAGMA table_info(skip_assets)")}
    select_r_created="r.created_at" if "created_at" in record_cols else "NULL"
    select_a_updated="a.updated_at" if "updated_at" in asset_cols else "NULL"
    targets=db.execute("""
       SELECT DISTINCT asset_key
       FROM skip_records
       WHERE source='device' AND status='pending' AND media_type='episode'
         AND season=4 AND lower(title) LIKE '%lincoln%' AND lower(title) LIKE '%lawyer%'
       ORDER BY asset_key LIMIT ?
    """,(MAX_TARGET_KEYS+1,)).fetchall()
    if len(targets)>MAX_TARGET_KEYS:
        raise ValueError("TOO_MANY_TARGET_ASSETS")
    rows_seen=0
    with_other_record_owner=0
    current_reg_owner_disagrees_all_record_owners=0
    currently_registered_owner_same_as_some_historical_record=0
    with_historical_different_episode=0
    with_historical_different_runtime=0
    with_historical_approved_from_different_owner=0
    registry_newer_than_earliest_pending=0
    comparable_dates=0
    runtime_delta_bands=Counter()
    for target in targets:
        key=target["asset_key"]
        all_rows=db.execute(f"""
            SELECT r.customer_id,r.status,r.season,r.episode,r.duration_ms,
                   {select_r_created} AS created_at
            FROM skip_records r
            WHERE r.asset_key=?
            LIMIT ?
        """,(key,MAX_RECORDS_PER_KEY+1)).fetchall()
        if len(all_rows)>MAX_RECORDS_PER_KEY:
            raise ValueError("KEY_HAS_TOO_MANY_RECORDS")
        rows_seen+=len(all_rows)
        current=db.execute(f"""
            SELECT a.playlist_id,a.season,a.episode,a.duration_ms,
                   {select_a_updated} AS updated_at,p.customer_id AS owner
            FROM skip_assets a LEFT JOIN customer_playlists p ON p.id=a.playlist_id
            WHERE a.asset_key=? LIMIT 1
        """,(key,)).fetchone()
        if current is None:
            continue
        pending=[r for r in all_rows if r["status"]=="pending"
                 and r["season"]==4 and
                 isinstance(r["episode"],int)]
        if not pending:
            continue
        owners={r["customer_id"] for r in all_rows}
        this_owner={r["customer_id"] for r in pending}
        if len(owners)>1:
            with_other_record_owner+=1
        if current["owner"] not in owners:
            current_reg_owner_disagrees_all_record_owners+=1
        elif current["owner"] not in this_owner:
            currently_registered_owner_same_as_some_historical_record+=1
        episodes={(r["season"],r["episode"]) for r in all_rows}
        if len(episodes)>1:
            with_historical_different_episode+=1
        run_values={r["duration_ms"] for r in all_rows if isinstance(r["duration_ms"],int)}
        if len(run_values)>1:
            with_historical_different_runtime+=1
        if any(r["status"]=="approved" and r["customer_id"] not in this_owner for r in all_rows):
            with_historical_approved_from_different_owner+=1
        ts=parse_iso(current["updated_at"])
        dates=[parse_iso(r["created_at"]) for r in pending]
        dates=[d for d in dates if d is not None]
        if ts and dates:
            comparable_dates+=1
            if ts>min(dates):
                registry_newer_than_earliest_pending+=1
        if isinstance(current["duration_ms"],int):
            # Aggregate coarse duration error bands, never reveal video durations.
            for r in pending:
                if isinstance(r["duration_ms"],int):
                    delta=abs(current["duration_ms"]-r["duration_ms"])
                    band=("<2s" if delta<2000 else "2s-1min" if delta<60000
                          else "1-10min" if delta<600000 else ">10min")
                    runtime_delta_bands[band]+=1
    return {
       "candidate_asset_keys":len(targets),
       "all_record_rows_sharing_keys":rows_seen,
       "keys_with_multiple_marker_customer_owners_globally":with_other_record_owner,
       "keys_where_registered_owner_is_no_marker_owner":current_reg_owner_disagrees_all_record_owners,
       "keys_where_registered_owner_only_matches_another_historical_marker":currently_registered_owner_same_as_some_historical_record,
       "keys_with_records_from_different_episodes_globally":with_historical_different_episode,
       "keys_with_different_recorded_durations_globally":with_historical_different_runtime,
       "keys_with_approved_marks_from_another_customer":with_historical_approved_from_different_owner,
       "registry_timestamp_comparisons_available":comparable_dates,
       "registry_updated_after_earliest_pending":registry_newer_than_earliest_pending,
       "runtime_difference_bands":dict(runtime_delta_bands),
    }


def sql_structure(path, *, function_names):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>2_000_000:
        return {"status":"unavailable"}
    raw=path.read_bytes()
    tree=ast.parse(raw.decode("utf8"))
    functions=[node for node in ast.walk(tree)
               if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))
               and node.name in function_names]
    sources=[]
    for function in functions:
        for node in ast.walk(function):
            if isinstance(node,ast.Constant) and isinstance(node.value,str):
                sources.append(node.value.lower())
    SQL=" ".join(sources)
    # No SQL, user ID, provider source, keys or password contents exported.
    return {
        "status":"parsed",
        "sha256_prefix":hashlib.sha256(raw).hexdigest()[:16],
        "target_functions_found":sorted({v.name for v in functions}),
        "target_functions_mention_skip_assets": "skip_assets" in SQL,
        "target_functions_contain_insert_or_replace":bool(re.search(r"insert\s+or\s+replace\s+into\s+skip_assets",SQL)),
        "target_functions_contain_insert_into":bool(re.search(r"insert\s+into\s+skip_assets",SQL)),
        "target_functions_contain_on_conflict": "on conflict" in SQL,
        "target_functions_update_playlist_id": bool(re.search(r"playlist_id\s*=",SQL)),
        "sql_or_python_source_exported":False,
    }


def run(db_path=DB, files=None):
    files=files or {
        "skip_markers.py":(MARKER,{"add_record"}),
        "skip_analysis.py":(ANALYSIS,{"provider_asset_key","register_asset"}),
    }
    with read_only(db_path) as db:
        counts=analyze(db)
    return {
      "mode":"EPISCENE_GLOBAL_MEDIA_KEY_PROVENANCE_READ_ONLY",
      "scope":"recorded_pending_Lincoln_S4",
      "counts":counts,
      "source_structure":{n:sql_structure(path,function_names=names)
                          for n,(path,names) in files.items()},
      "warnings":"Cross-account reuse not by itself proof of unauthorized submission; verify provider stream before recovery",
      "identifiers_or_source_exported":False,
      "database_writes":0,"workers_restarted":0,"provider_requests":0,
    }


if __name__=="__main__":
    try:
        print(json.dumps(run(),indent=2,sort_keys=True))
    except (sqlite3.Error,OSError,ValueError,SyntaxError,UnicodeError):
        print(json.dumps({"status":"STOP_READ_ONLY","reason":"DATA_OR_CODE_INCOMPATIBLE","database_writes":0}))
        raise SystemExit(2)
