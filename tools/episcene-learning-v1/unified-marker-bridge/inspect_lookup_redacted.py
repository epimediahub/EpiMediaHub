#!/usr/bin/env python3
"""Produce a REDACTED review of the active EpiScene device lookup.

- Parses (never imports/executes) the active /opt/.../skip_markers.py.
- Prints no source-code literals outside a small, audited allowlist.
- No SQL values, tokens, URLs, credentials, personal data, DB access, or HTTP.
- Does not alter the running service or original Python source.
- Redacted pseudocode is for review ONLY, not for production deployment.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path

ACTIVE = Path("/opt/epimediahub/provisioning/skip_markers.py")
TARGET = "v082_skip_lookup"
# Only string constants from a fixed structural vocabulary survive.
SAFE_LITERALS = frozenset((
    "GET", "POST", "approved", "pending", "intro", "recap", "outro",
    "segments", "asset_key", "source_key", "duration_ms", "media_type",
    "episode", "season", "series_id", "playlist_id", "stream_id",
    "provider", "type", "segment_type", "start_ms", "end_ms", "status",
    "records", "error", "ok", "success", "message", "code", "found",
    "data", "result", "skip", "v1", "id", "device_id", "tmdb_id",
    "imdb_id", "tvdb_id", "fingerprint", "source", "markers",
    "authorized", "verified", "active", "enabled", "valid",
    "true", "false", "all", "none", "device", "auth", "Bearer",
    "/v1/device/skip/lookup",
))
SAFE_SMALL_INTS = frozenset((-1, 0, 1, 2, 3, 4, 5, 10, 30, 100, 200,
                            201, 202, 204, 400, 401, 403, 404, 422,
                            429, 500, 1000))
MAX_SOURCE_BYTES = 2_000_000
MAX_FUNCTIONS = 10
MAX_OUTPUT_LINES = 300


def _check(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file() or not stat.S_ISREG(p.lstat().st_mode):
        raise ValueError("Active source unavailable or symlinked")
    if p.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Unexpected source size")
    return p


class Redact(ast.NodeTransformer):
    def visit_Expr(self, node):
        # Strip docstrings and other bare literals completely.
        if isinstance(node.value, ast.Constant) and type(node.value.value) is str:
            return None
        return self.generic_visit(node)

    def visit_Constant(self, node):
        if type(node.value) is str:
            if node.value in SAFE_LITERALS:
                return node
            return ast.copy_location(ast.Constant(value="<REDACTED_STRING>"), node)
        if type(node.value) is bytes:
            return ast.copy_location(ast.Constant(value=b"<REDACTED_BYTES>"), node)
        if type(node.value) is int and node.value not in SAFE_SMALL_INTS:
            return ast.copy_location(ast.Constant(value=-999), node)
        if type(node.value) is float:
            return ast.copy_location(ast.Constant(value=0.0), node)
        return node


def build_review(source: str):
    module = ast.parse(source)
    # The active server registers its device lookup inside a route-binding
    # function, not necessarily in module.body. The previous top-level-only
    # lookup incorrectly reported "Active lookup not found".
    defined = {}
    for fn in ast.walk(module):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.setdefault(fn.name, []).append(fn)
    candidates = defined.get(TARGET, [])
    def has_device_route(fn):
        return any(
            isinstance(dec, ast.Call) and dec.args
            and isinstance(dec.args[0], ast.Constant)
            and dec.args[0].value == "/v1/device/skip/lookup"
            for dec in fn.decorator_list
        )
    matching = [fn for fn in candidates if has_device_route(fn)]
    if len(matching) == 1:
        target = matching[0]
    elif len(candidates) == 1 and not matching:
        # Support routes registered via add_url_rule rather than a decorator.
        target = candidates[0]
    else:
        raise ValueError(
            "Expected one device lookup handler; found "
            + str(len(candidates)) + " candidate(s) and "
            + str(len(matching)) + " matching decorator(s)"
        )
    invoked = {node.func.id for node in ast.walk(target)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    # Duplicated helper names are ambiguous: never pick an arbitrary one.
    chosen = [(TARGET, target)] + [
        (name, defined[name][0]) for name in sorted(invoked)
        if name != TARGET and len(defined.get(name, [])) == 1
    ][:MAX_FUNCTIONS - 1]
    result = [
        "EpiScene /v1/device/skip/lookup — private redacted review",
        "READ ONLY: AST parse only; no backend import or execution.",
        "REDACTED: all non-allowlisted string/bytes/numeric literals.",
        "NOT A DEPLOYABLE PYTHON MODULE.",
        "Active function shape: " +
        hashlib.sha256(ast.dump(target, include_attributes=False).encode()).hexdigest()[:16],
        "Included functions: " + ", ".join(name for name, _ in chosen),
        "--- REDACTED CONTROL FLOW ---",
    ]
    for name, original in chosen:
        tree = Redact().visit(ast.fix_missing_locations(
            ast.parse(ast.unparse(original))))
        snippet = ast.unparse(tree)
        result.append("# FUNCTION: " + name)
        result.extend(snippet.splitlines())
    result.append("--- END REDACTED CONTROL FLOW ---")
    if len(result) > MAX_OUTPUT_LINES:
        result = result[:MAX_OUTPUT_LINES] + [
            "[TRUNCATED — only first 300 review lines shown]"
        ]
    return "\n".join(result) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(ACTIVE))
    args = parser.parse_args()
    src = _check(args.source).read_text(encoding="utf-8")
    review = build_review(src)
    # Secure transient file; no external transfers or automatic uploads.
    fd, path = tempfile.mkstemp(prefix="episcene-lookup-review-", suffix=".txt",
                                dir="/tmp", text=True)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(review)
    except BaseException:
        try:
            os.unlink(path)
        finally:
            raise
    print("REVIEW_CREATED: yes")
    print("REDACTED_REVIEW_PATH:", path)
    print("REVIEW_LINES:", len(review.splitlines()))
    print("NO_SERVICE_OR_DATABASE_CHANGED: true")
    print("NO_CREDENTIAL_VALUES_EMITTED: true (allowlist-only string constants)")
    print("NEXT: Inspect and upload the review TXT file; do not upload env,")
    print("token files, complete backups or raw provider access credentials.")


if __name__ == "__main__":
    main()
