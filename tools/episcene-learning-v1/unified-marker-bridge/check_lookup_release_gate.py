#!/usr/bin/env python3
"""EpiScene final read-only lookup compatibility gate.

Never imports production code; prints no raw Python, SQL, request values, asset
identifiers or customer records. No HTTP, IPTV or service restarts. Reports
whether the unified snapshot already matches the original approved markers.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import sqlite3
import stat
from collections import Counter
from pathlib import Path

SOURCE = Path("/opt/epimediahub/provisioning/skip_markers.py")
PRODUCTION = Path("/var/lib/epimediahub/provisioning.db")
UNIFIED = Path("/var/lib/episcene-learning/unified-markers.sqlite3")
ROUTE_NAME = "v082_skip_lookup"
ROUTE = "/v1/device/skip/lookup"
SAFE_KEYS = frozenset({
    "ok", "success", "found", "status", "error", "code", "markers", "segments",
    "records", "items", "skips", "intro", "outro", "recap", "start_ms", "end_ms",
    "kind", "segment_type", "duration_ms", "season", "episode", "playlist_id",
    "asset_key", "source_key", "enabled", "available", "version", "data",
    "result", "approved", "reason", "skip", "no_intro"
})
SAFE_CALLS = frozenset({
    "jsonify", "make_response", "request", "get_json", "get_device",
    "authorized_playlist", "verify_device", "device_from_request", "device_auth",
    "require_device", "get_device_from_request", "authorization",
    "source_url", "provider_asset_key", "lookup", "db", "connect_db",
    "with_db", "get_db", "get_json", "is_authorized", "device",
    "rate_limit", "validate", "request_device",
})
FIELDS = ("marker_id", "asset_key", "playlist_id", "kind",
          "start_ms", "end_ms")
EXACT_SOURCE_SHA_PREFIX = "b76093afb2f7b452"
MAX_FILE_SIZE = 2_000_000


def safe_file(path):
    p = Path(path)
    try:
        return (p.is_file() and not p.is_symlink()
                and stat.S_ISREG(p.lstat().st_mode))
    except OSError:
        return False


def readonly_db(path):
    if not safe_file(path):
        raise ValueError("Missing or symbolic-link SQLite source")
    con = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True,
                          timeout=4)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def _method(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _safe_str(node):
    value = node.value if isinstance(node, ast.Constant) else None
    return value if type(value) is str and value in SAFE_KEYS else None


def _result_shape(expr):
    """Recognizes top-level response builders without executing them."""
    if isinstance(expr, ast.Call):
        call = _method(expr.func)
        keys = set()
        for kw in expr.keywords:
            if kw.arg in SAFE_KEYS:
                keys.add(kw.arg)
        for arg in expr.args:
            if isinstance(arg, ast.Dict):
                keys.update(x for key in arg.keys if (x := _safe_str(key)))
        return {"builder": call if call in {"jsonify", "make_response", "dict"} else
                "other_or_helper",
                "visible_response_keys": sorted(keys)}
    if isinstance(expr, ast.Dict):
        return {"builder": "dict", "visible_response_keys":
                sorted(x for k in expr.keys if (x := _safe_str(k)))}
    return {"builder": "other_or_helper", "visible_response_keys": []}


def inspect_lookup(source):
    tree = ast.parse(source)
    funcs = [x for x in ast.walk(tree) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
             and x.name == ROUTE_NAME]
    if len(funcs) != 1:
        return {"single_active_handler": False, "candidate_count": len(funcs)}
    fn = funcs[0]
    shape = hashlib.sha256(ast.dump(fn, include_attributes=False).encode()).hexdigest()[:16]
    declared = any(
        isinstance(d, ast.Call) and d.args
        and isinstance(d.args[0], ast.Constant) and d.args[0].value == ROUTE
        and _method(d.func) in {"route", "post"}
        for d in fn.decorator_list)
    call_names = sorted({_method(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)
                         and _method(n.func) in SAFE_CALLS})
    results = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Return):
            val = _result_shape(node.value)
            if val not in results:
                results.append(val)
    return {
        "single_active_handler": True,
        "expected_lookup_route_present": declared,
        "active_shape_sha256_prefix": shape,
        "matches_previous_audit": shape == EXACT_SOURCE_SHA_PREFIX,
        "static_helper_hints": call_names,
        "return_shapes": results[:12],
        "authorization_verified": False,
        "response_runtime_verified": False
    }


def inspect_overlap(production_path, unified_path):
    """Compare only validated marker row IDs: no personal data is returned."""
    with readonly_db(unified_path) as kb, readonly_db(production_path) as prod:
        cols = {x["name"] for x in kb.execute("PRAGMA table_info(verified_markers)")}
        if not set(FIELDS) <= cols:
            return {"schema_ok": False}
        pc = {x["name"] for x in prod.execute("PRAGMA table_info(skip_records)")}
        if not {"id", "asset_key", "segment_type", "start_ms", "end_ms", "status"} <= pc:
            return {"schema_ok": False}
        totals = Counter()
        for record in kb.execute(
                "SELECT marker_id,asset_key,playlist_id,kind,start_ms,end_ms "
                "FROM verified_markers WHERE playlist_id IN (8,10)"):
            totals["all"] += 1
            totals["playlist_" + str(record["playlist_id"])] += 1
            row = prod.execute(
                "SELECT asset_key,segment_type,start_ms,end_ms,status "
                "FROM skip_records WHERE id=?", (record["marker_id"],)).fetchone()
            if row is None:
                totals["missing_from_original_table"] += 1
            elif (row["asset_key"], row["segment_type"], row["start_ms"],
                  row["end_ms"]) != (record["asset_key"], record["kind"],
                                    record["start_ms"], record["end_ms"]):
                totals["different_original_identity_or_bounds"] += 1
            elif row["status"] == "approved":
                totals["same_original_approved_marker"] += 1
            else:
                totals["same_original_not_approved"] += 1
        return {
            "schema_ok": True,
            "unified_total": totals["all"],
            "source_4K_ANALYSE": totals["playlist_8"],
            "source_THE_BEST": totals["playlist_10"],
            "already_identical_and_approved_in_original":
                totals["same_original_approved_marker"],
            "identical_but_not_approved_in_original":
                totals["same_original_not_approved"],
            "different_identity_or_time_bounds":
                totals["different_original_identity_or_bounds"],
            "not_in_original_records_by_id":
                totals["missing_from_original_table"],
            "does_not_prove_player_is_receiving_markers": True
        }


def report(source=SOURCE, production=PRODUCTION, unified=UNIFIED):
    summary = {"mode": "READ_ONLY",
               "original_skip_endpoint": ROUTE,
               "no_service_or_database_modified": True,
               "customer_playlists_or_secret_values_printed": False,
               "new_markers_auto_published": False}
    if not safe_file(source) or Path(source).stat().st_size > MAX_FILE_SIZE:
        return dict(summary, status="STOP_SOURCE_UNAVAILABLE")
    try:
        summary["lookup"] = inspect_lookup(Path(source).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError):
        return dict(summary, status="STOP_SOURCE_PARSE")
    try:
        summary["knowledge_vs_original"] = inspect_overlap(production, unified)
    except (sqlite3.Error, OSError, ValueError):
        return dict(summary, status="STOP_DB_SCHEMA_OR_ACCESS")
    summary["status"] = "INSPECTED_READ_ONLY"
    summary["next_step"] = "Use this shape/overlap to implement a guarded existing-lookup integration."
    return summary


if __name__ == "__main__":
    print(json.dumps(report(), ensure_ascii=False, indent=2, sort_keys=True))
