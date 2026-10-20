#!/usr/bin/env python3
"""One-time, read-only source contract for completing native Admin CRUD.

Inspects *only* named customer/reseller/playlist and EpiScene handlers.
Does not import production modules or execute any route. No network/db read.
All string, number and bytes *values*, SQL, provider URLs, login secrets,
comments and source docstrings are removed from emitted AST. Only recognized
form field *names* (not submitted form values) are preserved.
Review the generated mode-0600 JSON before sharing it.
"""
from __future__ import annotations
import ast
import json
import os
from pathlib import Path
import re
import sys

ROOT=Path("/opt/epimediahub/provisioning")
OUT=Path("/root/epimediahub-native-crud-contract.json")
ALLOW={
    "dashboard_v070.py":(
        "v070_create_customer","v070_rename_customer",
        "v073_delete_customer","v074_rename_device","v074_delete_device",
        "v076_add_customer_playlist","v076_update_customer_playlist",
        "v076_delete_customer_playlist","v070_add_playlist",
        "v070_update_playlist","v070_delete_playlist",
        "v070_sync_device","v070_move_device",
    ),
    "dashboard_v080.py":(
        "v080_create_reseller","v080_update_reseller",
        "v080_toggle_reseller","v080_delete_reseller",
        "v080_assign_customer_reseller","v080_reseller_add_playlist",
        "v080_reseller_update_playlist","v080_reseller_delete_playlist",
        "v080_reseller_create_customer","v080_reseller_rename_customer"
    ),
    "skip_markers.py":(
        "v082_skip_review","v152_intro_role","v082_skip_bulk_review"
    )
}
FIELD=re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,65}$")

class Sanitize(ast.NodeTransformer):
    def visit_Constant(self,node):
        if node.value is None or type(node.value) is bool:
            return node
        if isinstance(node.value,str):
            return ast.copy_location(ast.Constant("<redacted-value>"),node)
        if isinstance(node.value,bytes):
            return ast.copy_location(ast.Constant(b""),node)
        return ast.copy_location(ast.Constant(0),node)
    def visit_JoinedStr(self,node):
        return ast.copy_location(ast.Constant("<redacted-format>"),node)

def _name(node):
    if isinstance(node,ast.Name):
        return node.id
    if isinstance(node,ast.Attribute):
        return _name(node.value)+"."+node.attr
    return ""

def _fields(fn):
    result=set()
    for node in ast.walk(fn):
        if isinstance(node,ast.Call) and node.args:
            target=_name(node.func)
            if target in (
                "request.form.get","request.form.getlist",
                "request.args.get","request.values.get",
                "request.json.get","data.get"
            ) and isinstance(node.args[0],ast.Constant):
                key=node.args[0].value
                if isinstance(key,str) and FIELD.fullmatch(key):
                    result.add(key)
        if isinstance(node,ast.Subscript):
            target=_name(node.value)
            if target in ("request.form","request.args","request.json"):
                v=node.slice
                if isinstance(v,ast.Constant) and isinstance(v.value,str) and FIELD.fullmatch(v.value):
                    result.add(v.value)
    return sorted(result)

def _scan(path,names):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>3_000_000:
        return []
    result=[]
    tree=ast.parse(path.read_text(encoding="utf-8",errors="replace"),filename=path.name)
    for node in ast.walk(tree):
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) or node.name not in names:
            continue
        fields=_fields(node)
        source_lines=getattr(node,"end_lineno",node.lineno)-node.lineno
        if source_lines>950:
            flow="<oversized-function-not-exported>"
        else:
            scrubbed=Sanitize().visit(ast.Module(body=[node],type_ignores=[]))
            ast.fix_missing_locations(scrubbed)
            flow=ast.unparse(scrubbed)
            if len(flow)>18_000:
                flow=flow[:18_000]+"\n<truncated>"
        result.append({"handler":node.name,"form_field_names":fields,"redacted_flow":flow})
    return result

def main():
    if os.geteuid()!=0 or ROOT.is_symlink() or not ROOT.is_dir():
        raise RuntimeError("UNEXPECTED_HOST")
    result={"format":"epimediahub-native-crud-flow-v1",
            "scope":"static-redacted-AST-only-no-sql-no-form-values",
            "modules":[]}
    for filename,names in ALLOW.items():
        result["modules"].append({"file":filename,"functions":_scan(ROOT/filename,names)})
    data=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if len(data.encode("utf-8"))>400_000:
        raise RuntimeError("CONTRACT_TOO_LARGE")
    flags=os.O_CREAT|os.O_TRUNC|os.O_WRONLY
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(OUT,flags,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as file:
        os.fchmod(file.fileno(),0o600)
        file.write(data)
    print("NATIVE_CRUD_CONTRACT_READY")
    print("OUTPUT="+str(OUT))
    print("HANDLERS="+str(sum(len(x["functions"]) for x in result["modules"])))
    print("Review locally before uploading; no runtime data or values exported.")

if __name__=="__main__":
    try:main()
    except (OSError,ValueError,RuntimeError,SyntaxError,RecursionError) as exc:
        print("NATIVE_CRUD_CONTRACT_FAILED:"+type(exc).__name__)
        sys.exit(2)
