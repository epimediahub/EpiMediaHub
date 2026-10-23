#!/usr/bin/env python3
"""Read-only EpiScene key-collision and source-code structure check.

We deliberately do not reveal any original account IDs, playlist IDs, asset
keys, URLs, file contents or secret-bearing source lines.
"""
from __future__ import annotations
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3

DATABASE=Path("/var/lib/epimediahub/provisioning.db")
CODE={
    "skip_markers.py": Path("/opt/epimediahub/provisioning/skip_markers.py"),
    "skip_analysis.py": Path("/opt/epimediahub/provisioning/skip_analysis.py"),
}
KNOWN_SCHEMA={
    "skip_records":{"id","asset_key","customer_id","source","status","media_type","title","season","episode","duration_ms"},
    "skip_assets":{"asset_key","playlist_id","duration_ms","season","episode","source_key","title"},
    "customer_playlists":{"id","customer_id"}
}
ALLOWED_IDENTIFIERS={
    "skip_assets","skip_records","asset_key","playlist_id",
    "source_key","upsert","register","provider_asset_key",
    "add_record","submit","skip_markers","skip_analysis","authorized_playlist"
}


def structure(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>2_000_000:
        return {"status":"unavailable"}
    content=path.read_bytes()
    try:
        tree=ast.parse(content.decode("utf-8"))
    except (UnicodeError,SyntaxError):
        return {"status":"invalid_python"}
    # The reported identifiers are all predefined allowlisted names. File bytes
    # only contribute to SHA, and never to any user-visible source excerpt.
    funcs={n.name for n in ast.walk(tree)
           if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    calls={n.func.id for n in ast.walk(tree)
           if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
    literals={n.value.lower() for n in ast.walk(tree)
              if isinstance(n,ast.Constant) and isinstance(n.value,str)
              and len(n.value)<2000}
    def seen(x):
        return any(x in literal for literal in literals)
    return {
        "status":"present",
        "sha256_prefix":hashlib.sha256(content).hexdigest()[:16],
        "functions_present":sorted(funcs & ALLOWED_IDENTIFIERS),
        "calls_present":sorted(calls & ALLOWED_IDENTIFIERS),
        "sql_mentions_skip_assets":seen("skip_assets"),
        "sql_mentions_on_conflict":seen("on conflict"),
        "sql_mentions_insert_or_replace":seen("insert or replace"),
        "source_content_exported":False,
    }


def run(db_path=DATABASE,code=CODE):
    if db_path.is_symlink() or not db_path.is_file():
        raise ValueError("DB_NOT_FOUND")
    with sqlite3.connect(db_path.resolve().as_uri()+"?mode=ro",uri=True,timeout=10) as db:
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        for table,cols in KNOWN_SCHEMA.items():
            names={x["name"] for x in db.execute("PRAGMA table_info("+table+")")}
            if not cols.issubset(names):
                raise ValueError("SCHEMA_UNEXPECTED")
        db.execute("BEGIN")
        rows=db.execute("""
            SELECT r.asset_key,r.customer_id,r.duration_ms,r.season,r.episode,
                   a.playlist_id, a.duration_ms AS asset_runtime,
                   p.customer_id AS asset_owner
              FROM skip_records r
              JOIN skip_assets a ON a.asset_key=r.asset_key
              LEFT JOIN customer_playlists p ON p.id=a.playlist_id
             WHERE r.source='device'
               AND r.media_type='episode'
               AND r.season=4
               AND r.status='pending'
               AND (LOWER(TRIM(r.title))='the lincoln lawyer'
                    OR (LOWER(r.title) LIKE '%lincoln%' AND
                        LOWER(r.title) LIKE '%lawyer%'))
        """).fetchall()
        groups=defaultdict(list)
        for r in rows:
            groups[r["asset_key"]].append(r)
        mismatch=[r for r in rows
                  if r["asset_owner"] is not None
                  and r["customer_id"] != r["asset_owner"]]
        counts=Counter()
        counts["s4_pending_records"]=len(rows)
        counts["s4_distinct_asset_keys"]=len(groups)
        counts["s4_owner_mismatch"]=len(mismatch)
        counts["s4_asset_keys_with_multiple_marker_customers"]=sum(
            len({r["customer_id"] for r in g})>1 for g in groups.values())
        counts["s4_asset_keys_with_multiple_record_runtimes"]=sum(
            len({r["duration_ms"] for r in g})>1 for g in groups.values())
        counts["s4_runtime_mismatch_gt_500ms"]=sum(
            type(r["duration_ms"]) is int and
            type(r["asset_runtime"]) is int and
            abs(r["duration_ms"]-r["asset_runtime"])>500
            for r in rows)
        counts["s4_asset_keys_shared_by_different_episodes"]=sum(
            len({(r["season"],r["episode"]) for r in g})>1
            for g in groups.values())
        # Stable counts only. Never export asset keys, customer/device IDs or
        # names of the underlying playlists or the registered source.
    return {
        "mode":"EPISCENE_LINCOLN_S4_COLLISION_ROOT_CAUSE",
        "marker_identity_collisions":dict(counts),
        "deployed_code_structure":{name:structure(path) for name,path in code.items()},
        "security_note":"Diagnose does not authenticate the original provider stream",
        "no_credentials_or_identifiers_exported":True,
        "database_writes":0,"service_restarts":0,"provider_requests":0,
    }


if __name__=="__main__":
    try:
        print(json.dumps(run(),sort_keys=True,indent=2))
    except (ValueError,sqlite3.Error,OSError):
        print(json.dumps({"status":"STOP","reason":"DB_OR_SCHEMA_UNAVAILABLE",
                          "database_writes":0}))
        raise SystemExit(2)
