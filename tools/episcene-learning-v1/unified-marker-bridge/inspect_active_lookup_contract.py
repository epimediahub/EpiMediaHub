#!/usr/bin/env python3
"""Read-only, redacted audit of the ACTIVE EpiScene device marker handlers.

Uses only Python's parser. Never executes/imports the backend; prints no raw
code, SQL strings, playlist or customer records, passwords, URLs or tokens.
"""
from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
import stat
from pathlib import Path

SOURCE = Path("/opt/epimediahub/provisioning/skip_markers.py")
STORE = Path("/var/lib/episcene-learning/unified-markers.sqlite3")
TARGETS = ("v082_skip_lookup", "v126_skip_fingerprint", "v082_skip_presence",
           "v082_skip_submit")

# Strict allowlists, not arbitrary literal values from production.
FIELD_KEYS = frozenset((
    "playlist_id", "asset_key", "source_key", "stream_id", "extension",
    "media_type", "season", "episode", "duration_ms", "year", "title",
    "start_ms", "end_ms", "kind", "segment_type", "confidence", "status",
    "markers", "segments", "records", "skip", "verified", "provider",
    "series_id", "tmdb_id", "imdb_id", "tvdb_id", "fingerprint",
    "frames_sha256", "fingerprint_sha256", "offset_ms", "length_ms",
    "step_ms", "source_version", "content_version", "device_id",
))
ROUTE_PREFIX = "/v1/device/skip/"
DB_TABLES = frozenset(("skip_records", "skip_assets", "skip_app_windows",
                       "skip_auto_evidence", "skip_analysis_playlists",
                       "skip_analysis_sources", "skip_jobs",
                       "skip_approved_records", "skip_marker_history",
                       "customer_playlists", "devices", "customers"))
TOKENS = frozenset((
    "get_json", "jsonify", "request", "with_db", "authorized_playlist",
    "provider_asset_key", "review_record", "verify_device", "device_auth",
    "lookup", "add_record", "get_device", "db", "sqlite3", "fingerprint",
    "source_url", "safe_json", "require_device", "check_device",
))
MAX_SOURCE_BYTES = 2_000_000


def regular_file(path):
    p = Path(path)
    try:
        return p.is_file() and not p.is_symlink() and stat.S_ISREG(p.lstat().st_mode)
    except OSError:
        return False


def _word(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _literal_str(node):
    return node.value if isinstance(node, ast.Constant) and type(node.value) is str else None


def _route_from(node):
    routes = []
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call) or not dec.args:
            continue
        first = _literal_str(dec.args[0])
        if first and first.startswith(ROUTE_PREFIX) and len(first) < 100 and "?" not in first:
            routes.append({"method": _word(dec.func).upper() if _word(dec.func) else "UNKNOWN",
                           "path": first})
    return routes[:4]


def _function_data(node):
    field_literals = set()
    dict_keys = set()
    call_signals = set()
    table_refs = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if child.value in FIELD_KEYS:
                field_literals.add(child.value)
            for tbl in DB_TABLES:
                if tbl in child.value.casefold():
                    table_refs.add(tbl)
        if isinstance(child, ast.Dict):
            for key in child.keys:
                val = _literal_str(key)
                if val in FIELD_KEYS:
                    dict_keys.add(val)
        if isinstance(child, ast.Call):
            name = _word(child.func)
            if name in TOKENS:
                call_signals.add(name)
    # This hash is of an abstract syntax tree, not production code text.
    source_digest = hashlib.sha256(
        ast.dump(node, include_attributes=False).encode("utf-8")).hexdigest()[:16]
    return {"present": True,
            "function_shape_sha256_prefix": source_digest,
            "route_declarations": _route_from(node),
            "possible_field_names": sorted(field_literals)[:32],
            "possible_response_dict_keys": sorted(dict_keys)[:28],
            "known_helper_signals": sorted(call_signals),
            "known_database_table_mentions": sorted(table_refs),
            "endpoint_authorization_verified": False}


def inspect_source(source):
    tree = ast.parse(source)
    nodes = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in TARGETS:
            nodes.setdefault(node.name, []).append(node)
    return {name: _function_data(nodes[name][0]) if len(nodes.get(name, [])) == 1
            else {"present": False, "candidates": len(nodes.get(name, [])),
                  "reason": "unknown_or_duplicate_definition"} for name in TARGETS}


def inspect_knowledge(path):
    if not regular_file(path):
        return {"exists": False, "readable": False}
    try:
        with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro",
                             uri=True, timeout=3) as con:
            con.execute("PRAGMA query_only=ON")
            available = {row[1] for row in con.execute("PRAGMA table_info(verified_markers)")}
            if not {"playlist_id", "marker_id"} <= available:
                return {"exists": True, "readable": True, "schema_ok": False}
            count = con.execute("SELECT COUNT(*) FROM verified_markers").fetchone()[0]
            counts = dict((str(p), n) for p, n in con.execute(
                "SELECT playlist_id,COUNT(*) FROM verified_markers "
                "WHERE playlist_id IN (8,10) GROUP BY playlist_id"))
            return {"exists": True, "readable": True, "schema_ok": True,
                    "verified_marker_count": count,
                    "by_analysis_source": {"4K_ANALYSE": counts.get("8", 0),
                                           "THE_BEST": counts.get("10", 0)}}
    except (sqlite3.Error, ValueError, OSError):
        return {"exists": True, "readable": False}


def report(path=SOURCE, store=STORE):
    if not regular_file(path) or Path(path).stat().st_size > MAX_SOURCE_BYTES:
        return {"mode": "READ_ONLY", "active_handler_file": "UNAVAILABLE",
                "status": "BLOCKED", "no_changes": True}
    try:
        source = Path(path).read_text(encoding="utf-8")
        functions = inspect_source(source)
    except (OSError, UnicodeError, SyntaxError):
        return {"mode": "READ_ONLY", "active_handler_file": "UNPARSABLE",
                "status": "BLOCKED", "no_changes": True}
    return {"mode": "READ_ONLY",
            "active_handler_file": "skip_markers.py",
            "handlers": functions,
            "separate_verified_knowledge": inspect_knowledge(store),
            "customer_playlists_inspected": False,
            "external_requests_made": False,
            "existing_server_or_data_modified": False,
            "handler_semantics_not_yet_proven": True,
            "note": "Names are AST hints, NOT evidence that a route authenticates or returns a particular shape."}


if __name__ == "__main__":
    print(json.dumps(report(), ensure_ascii=False, indent=2))
