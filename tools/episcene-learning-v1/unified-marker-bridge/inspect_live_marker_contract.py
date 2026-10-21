#!/usr/bin/env python3
"""EpiScene read-only live route inventory.

Inspects Python syntax, file presence and systemd state WITHOUT importing
production modules, making network requests or reading production database
rows. Never prints server source code, credentials or raw log lines.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path("/opt/epimediahub/provisioning")
KEYWORDS = re.compile(r"skip|marker|intro|recap|outro|episcene|episode", re.I)
MAX_FILES = 200
MAX_BYTES = 3_000_000
MAX_ITEMS = 80
VERBS = {"route", "get", "post", "put", "delete", "patch"}


def safe_route(path: str) -> bool:
    return (
        isinstance(path, str)
        and 1 <= len(path) <= 180
        and path.startswith("/")
        and KEYWORDS.search(path) is not None
        and "://" not in path
        and "?" not in path
        and "\n" not in path
        and "\r" not in path
        and not any(word in path.casefold() for word in
                    ("/token/", "/secret/", "/password/", "/credential/"))
    )


def _str(node):
    return node.value if isinstance(node, ast.Constant) and type(node.value) is str else None


def route_inventory(source: str):
    """AST-only route enumeration: function and literal route patterns."""
    tree = ast.parse(source)
    routes = set()
    hits = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if KEYWORDS.search(node.name):
                hits.add(node.name)
            for d in node.decorator_list:
                if not isinstance(d, ast.Call) or not isinstance(d.func, ast.Attribute):
                    continue
                if d.func.attr not in VERBS or not d.args:
                    continue
                route = _str(d.args[0])
                if not safe_route(route):
                    continue
                methods = {d.func.attr.upper()} if d.func.attr != "route" else set()
                for k in d.keywords:
                    if k.arg == "methods" and isinstance(k.value, (ast.List, ast.Tuple)):
                        methods.update(s.upper() for n in k.value.elts
                                       if (s := _str(n)) and s.upper() in
                                       {"GET", "POST", "PUT", "PATCH", "DELETE"})
                routes.add((route, ",".join(sorted(methods)) if methods else "DECLARED",
                            node.name))
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_url_rule":
                continue
            if not node.args:
                continue
            path = _str(node.args[0])
            if safe_route(path):
                routes.add((path, "DYNAMIC", "add_url_rule"))
    return sorted(routes), sorted(hits)


def systemd_state(name):
    try:
        p = subprocess.run(["systemctl", "is-active", name],
                           capture_output=True, text=True, timeout=3)
        return "active" if p.returncode == 0 else "not_active"
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def inspect(root=ROOT, state=systemd_state):
    p = Path(root)
    if not p.is_dir() or p.is_symlink():
        return {"mode": "READ_ONLY", "backend_present": False,
                "backend_route_inventory": [], "status": "BLOCKED"}
    modules = []
    # Avoid walking the application virtualenv or secret/config subtrees.
    for base, directories, filenames in os.walk(p, followlinks=False):
        relbase = Path(base).relative_to(p)
        directories[:] = [d for d in directories if
                          d not in (".venv", "venv", ".git", "__pycache__",
                                    "site-packages", "secrets", "private",
                                    "certificates", "node_modules")
                          and len(relbase.parts) < 2
                          and not (Path(base) / d).is_symlink()]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            item = Path(base) / name
            try:
                if (item.is_symlink() or not item.is_file()
                        or item.stat().st_size > MAX_BYTES):
                    continue
                modules.append((str(item.relative_to(p)), item))
            except (OSError, ValueError):
                continue
            if len(modules) >= MAX_FILES:
                break
        if len(modules) >= MAX_FILES:
            break

    matches, scanned, unreadable, marker_modules = [], 0, 0, []
    for rel, file in sorted(modules):
        try:
            contents = file.read_text(encoding="utf-8")
            routes, handlers = route_inventory(contents)
        except (OSError, UnicodeError, SyntaxError):
            unreadable += 1
            continue
        scanned += 1
        if routes or handlers:
            marker_modules.append(rel)
        for path, methods, handler in routes:
            if len(matches) < MAX_ITEMS:
                matches.append({"module": rel, "route": path,
                                "methods": methods, "handler": handler})
    bridge_root = Path("/opt/episcene-learning/unified")
    return {
        "mode": "READ_ONLY",
        "backend_present": True,
        "python_modules_scanned": scanned,
        "python_modules_unreadable": unreadable,
        "possible_marker_modules": marker_modules[:50],
        "marker_routes": matches,
        "marker_routes_total_returned": len(matches),
        "production_service": state("epimediahub-provisioning.service"),
        "knowledge_sync_timer": state("episcene-unified-sync.timer"),
        "unified_bridge_code_present": all(
            (bridge_root / f).is_file() and not (bridge_root / f).is_symlink()
            for f in ("bridge.py", "runtime_integration.py")),
        "player_endpoint_integration": "NOT_PROVEN_BY_ROUTE_INVENTORY",
        "android_player_build": "NOT_INSPECTED",
        "caution": "Route names are signatures only: authorization and behavior not verified.",
        "no_source_code_or_secret_values_emitted": True,
        "no_service_database_or_file_modified": True,
    }


if __name__ == "__main__":
    print(json.dumps(inspect(), ensure_ascii=False, indent=2))
