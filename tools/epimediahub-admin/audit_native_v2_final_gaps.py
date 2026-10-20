#!/usr/bin/env python3
"""Read-only, narrowly scoped final native Admin V2 source-contract audit.

Parses Python source AST only; never imports production modules, opens DBs,
runs Flask, invokes network connections, or exports passwords/SQL/source literals.
Form key NAMES are permitted, along with a short allowlist of known enum words.
Review JSON locally before uploading it.
"""
from __future__ import annotations
import ast
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path("/opt/epimediahub/provisioning")
OUT = Path("/root/epimediahub-native-final-gaps.json")
MAX_MODULES = 500
MAX_SOURCE_BYTES = 2_500_000
MAX_FLOW = 18000
MAX_OUTPUT = 300_000

# Exact function names only. Callers and helpers are not executed.
TARGETS = {
    "_playlist_config",
    "_config",
    "csrf",
    "v073_delete_customer",
    "v074_delete_device",
    "v080_delete_reseller",
    "v082_skip_review",
    "v152_intro_role",
    "v082_skip_bulk_review",
    "valid_range",
    "review_record",
    "approve_pending_scope",
    "parse_time",
}
GETTERS = {
    "request.form.get", "request.form.getlist", "request.form.__getitem__",
    "request.values.get", "request.args.get", "request.json.get",
}
FIELD = re.compile(r"^[a-zA-Z_][a-zA-Z_0-9-]{0,55}$")

# Words useful for UI choice mapping that cannot contain credentials or URLs.
ENUMS = frozenset({
    "yes","no","true","false","on","off","1","0",
    "approve","approved","reject","rejected","accept","accepted",
    "deny","denied","confirm","confirmed","delete","DELETE",
    "intro","outro","none","opening","recap","credits","preview",
    "series","season","episode","all","bulk","single","auto","manual",
    "m3u","m3u8","xtream","xtream_codes","xui","portal","stalker",
    "url","userpass","enabled","disabled","activate","deactivate",
    "apply","skip","keep","invalidate","review","partial",
    "netflix","original","previously","next",
})

def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        root = dotted(node.value)
        return (root + "." if root else "") + node.attr
    return ""

def form_key(node):
    if isinstance(node, ast.Call) and node.args and dotted(node.func) in GETTERS:
        v = node.args[0]
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            return v.value
    if isinstance(node, ast.Subscript) and dotted(node.value) in {
        "request.form", "request.args", "request.values", "request.json"
    }:
        v = node.slice
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            return v.value
    return None

def keys_from(node):
    names = set()
    for item in ast.walk(node):
        value = form_key(item)
        if isinstance(value, str) and FIELD.fullmatch(value):
            names.add(value)
    return sorted(names)

class Scrub(ast.NodeTransformer):
    def visit_Constant(self, node):
        if node.value is None or isinstance(node.value, bool):
            return node
        if isinstance(node.value, str):
            return ast.copy_location(ast.Constant(
                node.value if node.value in ENUMS else "<redacted>"
            ), node)
        if isinstance(node.value, bytes):
            return ast.copy_location(ast.Constant(b""), node)
        return ast.copy_location(ast.Constant(0), node)

    def visit_JoinedStr(self, node):
        return ast.copy_location(ast.Constant("<redacted-format>"), node)

    def visit_Call(self, node):
        key = form_key(node)
        self.generic_visit(node)
        if key and FIELD.fullmatch(key):
            node.args[0] = ast.copy_location(ast.Constant(key), node.args[0])
        return node

    def visit_Subscript(self, node):
        key = form_key(node)
        self.generic_visit(node)
        if key and FIELD.fullmatch(key):
            node.slice = ast.copy_location(ast.Constant(key), node.slice)
        return node

def intro_roles(tree):
    """Only safe option-label identifiers from the specifically named mapping."""
    result = []
    for item in tree.body:
        if not isinstance(item, (ast.Assign, ast.AnnAssign)):
            continue
        targets = item.targets if isinstance(item, ast.Assign) else [item.target]
        if not any(isinstance(t, ast.Name) and t.id == "INTRO_ROLES" for t in targets):
            continue
        value = item.value
        if isinstance(value, ast.Dict):
            values = value.keys
        elif isinstance(value, (ast.Set, ast.Tuple, ast.List)):
            values = value.elts
        else:
            values = []
        for obj in values:
            if isinstance(obj, ast.Constant) and isinstance(obj.value, str):
                word = obj.value
                if re.fullmatch(r"[a-z][a-z0-9_-]{0,30}", word):
                    result.append(word)
    return sorted(set(result))[:32]

def inspect(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
        return [], []
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=path.name)
    result = []
    roles = intro_roles(tree) if path.name == "skip_intro_sections.py" else []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name not in TARGETS:
            continue
        if node.end_lineno - node.lineno > 700:
            flow = "<function-oversized>"
        else:
            # Round-trip to avoid mutating the original AST while walking it.
            isolated = ast.Module(body=[node], type_ignores=[])
            sanitized = Scrub().visit(isolated)
            ast.fix_missing_locations(sanitized)
            flow = ast.unparse(sanitized)
            if len(flow) > MAX_FLOW:
                flow = flow[:MAX_FLOW] + "\n<truncated>"
        result.append({
            "function": node.name,
            "field_name_only": keys_from(node),
            "redacted_structure": flow,
        })
    return result, roles

def main():
    if os.geteuid() != 0 or ROOT.is_symlink() or not ROOT.is_dir():
        raise RuntimeError("unexpected host/source path")
    modules = []
    all_roles = []
    for p in sorted(ROOT.glob("*.py"))[:MAX_MODULES]:
        functions, roles = inspect(p)
        if functions:
            modules.append({"file": p.name, "functions": functions})
        all_roles.extend(roles)
    result = {
        "format": "epimediahub-native-final-gaps-v1",
        "scope": "AST-only; field names and finite known enums; no SQL or runtime data",
        "modules": modules,
        "intro_role_identifiers": sorted(set(all_roles)),
    }
    raw = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if len(raw.encode("utf-8")) > MAX_OUTPUT:
        raise RuntimeError("audit exceeded safe output limit")
    flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(OUT, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(raw)
    print("NATIVE_V2_FINAL_GAPS_READY")
    print("OUTPUT=" + str(OUT))
    print("FUNCTIONS=" + str(sum(len(x["functions"]) for x in modules)))
    print("Please review locally before uploading. No data rows or secrets exported.")

if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, UnicodeError, SyntaxError, RecursionError) as exc:
        print("NATIVE_V2_FINAL_GAPS_FAILED:" + type(exc).__name__)
        sys.exit(2)
