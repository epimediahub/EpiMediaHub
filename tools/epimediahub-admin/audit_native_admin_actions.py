#!/usr/bin/env python3
"""Read-only AST inventory of existing admin authentication & grant handlers.

No module imports from production and no live requests or database connections.
Returns *only* named call sites, form/JSON field names, control-flow flags and
decorator names. No function bodies, literals, passwords, session values,
license identifiers, customer names or user data are exported.
"""
from __future__ import annotations
import ast
import json
import os
from pathlib import Path
import re
import sys

BASE=Path("/opt/epimediahub/provisioning")
HANDLERS={
    "app.py":{"login"},
    "annual_license.py":{"admin_grant_year","admin_revoke_year"},
    "vpn_auto_enroll.py":{"grant_trial_auto","grant_year_auto"},
    "dashboard_v080.py":{"v080_create_reseller","v080_reseller_login"},
    "license_api.py":{"admin_activate_device","reseller_activate_device"},
}
SAFE=re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,75}$")
FIELD=re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,60}$")
SENSITIVE=re.compile(r"password|secret|private|token|credential|key|seed|auth",re.I)

def name(node):
    if isinstance(node,ast.Name):
        return node.id
    if isinstance(node,ast.Attribute):
        return name(node.value)+"."+node.attr
    return ""

def analyze(src: str, selectors):
    tree=ast.parse(src)
    output=[]
    for node in ast.walk(tree):
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) or node.name not in selectors:
            continue
        calls=set()
        inputs=set()
        for sub in ast.walk(node):
            if not isinstance(sub,ast.Call):
                continue
            target=name(sub.func)
            if target and len(target)<=95 and all(SAFE.fullmatch(p) for p in target.split(".")):
                if not SENSITIVE.search(target):
                    calls.add(target)
            if (target.startswith("request.form.") or target.startswith("request.args.") or
                    target.startswith("request.json.")):
                if sub.args and isinstance(sub.args[0],ast.Constant):
                    key=sub.args[0].value
                    if isinstance(key,str) and FIELD.fullmatch(key):
                        inputs.add(key if not SENSITIVE.search(key) else "[SENSITIVE_FIELD]")
        output.append({
            "handler":node.name,
            "decorator_names":[name(d.func if isinstance(d,ast.Call) else d)
                 for d in node.decorator_list
                 if name(d.func if isinstance(d,ast.Call) else d) and
                 not SENSITIVE.search(name(d.func if isinstance(d,ast.Call) else d))][:12],
            "call_names":sorted(calls)[:85],
            "request_field_names":sorted(inputs)[:25],
            "uses_request_form":any(name(c.func).startswith("request.form")
                for c in ast.walk(node) if isinstance(c,ast.Call)),
            "uses_request_json":any(name(c.func).startswith("request.json")
                for c in ast.walk(node) if isinstance(c,ast.Call)),
            "has_exception_handler":any(isinstance(c,ast.ExceptHandler)
                for c in ast.walk(node)),
            "has_return":any(isinstance(c,ast.Return) for c in ast.walk(node)),
        })
    return output

def main():
    if os.geteuid()!=0 or BASE.is_symlink() or not BASE.is_dir():
        raise RuntimeError("Unexpected runtime or path")
    result={"format":"epimediahub-admin-action-contract-v1",
            "scope":"AST-names-only; no function code, values or customer data",
            "handlers":[]}
    for file,selectors in HANDLERS.items():
        path=BASE/file
        if path.is_symlink() or not path.is_file() or path.stat().st_size>2_000_000:
            continue
        matches=analyze(path.read_text(encoding="utf-8",errors="replace"),selectors)
        result["handlers"].extend({"module":file,**item} for item in matches)
    destination=Path("/root/epimediahub-admin-action-contract.json")
    flags=os.O_WRONLY|os.O_CREAT|os.O_TRUNC
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    with os.fdopen(os.open(destination,flags,0o600),"w",encoding="utf-8") as stream:
        os.fchmod(stream.fileno(),0o600)
        json.dump(result,stream,ensure_ascii=False,indent=2)
        stream.write("\n")
    print("NATIVE_ACTION_CONTRACT_READY")
    print("PATH="+str(destination))
    print("HANDLERS="+str(len(result["handlers"])))
    print("Only AST names/field keys; no code bodies or runtime data.")

if __name__=="__main__":
    try:main()
    except (OSError,RuntimeError,ValueError,SyntaxError) as exc:
        print("NATIVE_ACTION_CONTRACT_FAILED:"+type(exc).__name__)
        sys.exit(2)
