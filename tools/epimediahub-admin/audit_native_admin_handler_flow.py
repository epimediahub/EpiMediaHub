#!/usr/bin/env python3
"""Read-only, aggressively redacted AST audit for native Admin action adapters.

Only selected existing function ASTs are exported. All string/bytes/numeric
literals are replaced; source comments, docstrings and runtime data are never
exported. No modules are imported and no database, network or service is touched.

The purpose is to inspect control flow and helper boundaries, not credentials.
Always review the locally generated 0600 JSON before sharing.
"""
from __future__ import annotations
import ast
import json
import os
from pathlib import Path
import sys

SOURCE=Path("/opt/epimediahub/provisioning")
DEST=Path("/root/epimediahub-native-handler-flow.json")
ALLOW={
    "app.py": ("login",),
    "dashboard_security.py": ("_require_admin","_admin_guard","_require_csrf",
        "require_admin","require_csrf","admin_required","csrf"),
    "annual_license.py": ("admin_grant_year","admin_revoke_year","_device",
        "_lifetime","_parse","_audit"),
    "vpn_auto_enroll.py": ("grant_trial_auto","grant_year_auto","_auto_pool",
        "_public_settings","migrate"),
    "license_api.py": ("admin_activate_device","_admin_guard",
        "_activate_subject"),
}
MAX_FUNCTION_LINES=300
MAX_TOTAL_SIZE=80_000

class HideLiterals(ast.NodeTransformer):
    def visit_Constant(self,node):
        if node.value is None or isinstance(node.value,bool):
            return node
        if isinstance(node.value,str):
            return ast.copy_location(ast.Constant(value="<literal-redacted>"),node)
        if isinstance(node.value,bytes):
            return ast.copy_location(ast.Constant(value=b""),node)
        return ast.copy_location(ast.Constant(value=0),node)
    def visit_JoinedStr(self,node):
        return ast.copy_location(ast.Constant(value="<format-redacted>"),node)
    def visit_Dict(self,node):
        self.generic_visit(node)
        return node

def export_one(path: Path,names):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>2_000_000:
        return []
    tree=ast.parse(path.read_text(encoding="utf-8",errors="replace"),filename=path.name)
    found=[]
    for node in ast.walk(tree):
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) or node.name not in names:
            continue
        if getattr(node,"end_lineno",node.lineno)-node.lineno>MAX_FUNCTION_LINES:
            found.append({"function":node.name,"flow":"<too-long-to-export>"})
            continue
        # Work with a new node so other results cannot retain raw constants.
        snippet=ast.Module(body=[node],type_ignores=[])
        safe=HideLiterals().visit(snippet)
        ast.fix_missing_locations(safe)
        flow=ast.unparse(safe)
        if len(flow)>12_000:
            flow=flow[:12_000]+"\n<truncated>"
        found.append({"function":node.name,"flow":flow})
    return found

def main():
    if os.geteuid()!=0 or SOURCE.is_symlink() or not SOURCE.is_dir():
        raise RuntimeError("Expected root and production provisioning directory")
    output={"format":"epimediahub-redacted-flow-v1",
        "scope":"static AST only; all constants stripped, no comments, no runtime data",
        "files":[]}
    for name,functions in ALLOW.items():
        flows=export_one(SOURCE/name,functions)
        output["files"].append({"module":name,"functions":flows})
    raw=json.dumps(output,ensure_ascii=False,indent=2)+"\n"
    if len(raw)>MAX_TOTAL_SIZE:
        raise RuntimeError("Output too large; refusing unsafe truncation")
    flags=os.O_WRONLY|os.O_CREAT|os.O_TRUNC
    if hasattr(os,"O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd=os.open(DEST,flags,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as stream:
        os.fchmod(stream.fileno(),0o600)
        stream.write(raw)
    print("ADMIN_NATIVE_REDACTED_FLOW_READY")
    print("OUTPUT="+str(DEST))
    print("MODULES="+str(len(output["files"])))
    print("FUNCTIONS="+str(sum(len(x["functions"]) for x in output["files"])))
    print("All string and numeric constants removed; review output before sharing.")

if __name__=="__main__":
    try: main()
    except (OSError,RuntimeError,ValueError,SyntaxError,RecursionError) as exc:
        print("ADMIN_NATIVE_REDACTED_FLOW_FAILED:"+type(exc).__name__)
        sys.exit(2)
