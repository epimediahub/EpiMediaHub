#!/usr/bin/env python3
"""Read-only contract inventory for building a *native* Android admin app.

No production imports; no API invocations; no table rows; no customer names,
tokens, stream URLs, session contents, password values, or secret values.
Only relevant SQLite table/column *names* and Python route declarations.
Review generated JSON locally before sharing.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

BASE=Path("/opt/epimediahub/provisioning")
DATABASE=Path("/var/lib/epimediahub/provisioning.db")
FILTER=("admin","login","auth","customer","reseller","playlist","licen",
        "vpn","trial","device","client","user","credit","subscription","activate")
SAFE_NAME=re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,95}$")
SKIP_NAME=re.compile(r"password|secret|private|bearer|token|api.?key|credential|hash",re.I)
ROUTE_METHODS={"route","get","post","put","patch","delete","add_url_rule"}
MAX_MODULES=250
MAX_TABLES=140
MAX_ROUTES=350

def _name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _name(node.value)+"."+node.attr
    return ""

def inspect_source(text:str,basename:str):
    try:
        tree=ast.parse(text,filename=basename)
    except (SyntaxError,ValueError):
        return []
    found=[]
    for node in ast.walk(tree):
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            continue
        for d in node.decorator_list:
            if not isinstance(d,ast.Call) or _name(d.func).split(".")[-1] not in ROUTE_METHODS:
                continue
            if not d.args or not isinstance(d.args[0],ast.Constant):
                continue
            path=d.args[0].value
            if not isinstance(path,str) or len(path)>170:
                continue
            if not (path.startswith("/") and any(k in path.lower() for k in FILTER)):
                continue
            methods=[]
            for kw in d.keywords:
                if kw.arg=="methods" and isinstance(kw.value,(ast.List,ast.Tuple)):
                    methods=[x.value for x in kw.value.elts
                             if isinstance(x,ast.Constant) and x.value in
                             ("GET","POST","PUT","PATCH","DELETE")]
            found.append({"module":basename,
                          "route":path if re.fullmatch(r"/[A-Za-z0-9_./<>:-]+",path) else "[REDACTED]",
                          "handler":node.name if SAFE_NAME.fullmatch(node.name) else "[REDACTED]",
                          "decorator":_name(d.func).split(".")[-1],
                          "methods":methods})
    return found

def collect(base:Path,db_path:Path):
    if base.is_symlink() or not base.is_dir():
        raise RuntimeError("Unexpected backend source path")
    if db_path.is_symlink() or not db_path.is_file():
        raise RuntimeError("Database missing or linked")
    tables=[]
    with sqlite3.connect(db_path.resolve().as_uri()+"?mode=ro",uri=True,timeout=5) as con:
        con.execute("PRAGMA query_only=ON")
        definitions=con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        for (name,) in definitions:
            if not isinstance(name,str) or not SAFE_NAME.fullmatch(name):
                continue
            if not any(k in name.lower() for k in FILTER):
                continue
            if len(tables)>=MAX_TABLES:
                break
            cols=[]
            for row in con.execute("PRAGMA table_info('"+name+"')"):
                col=row[1]
                if isinstance(col,str) and SAFE_NAME.fullmatch(col) and not SKIP_NAME.search(col):
                    cols.append(col)
            tables.append({"name":name,"columns":cols[:90]})
    routes=[]
    inspected=0
    for p in sorted(base.glob("*.py")):
        if inspected>=MAX_MODULES or len(routes)>=MAX_ROUTES:
            break
        if p.is_symlink() or p.stat().st_size>1_000_000:
            continue
        inspected+=1
        routes.extend(inspect_source(p.read_text(encoding="utf-8",errors="replace"),p.name))
    return {"format":"epimediahub-native-contract-v1",
            "created_at_utc":datetime.now(timezone.utc).isoformat(),
            "scope":"schema-and-route-names-only-no-rows-no-secrets",
            "tables":tables,
            "routes":routes[:MAX_ROUTES],
            "source_files_scanned":inspected}

def main():
    if os.geteuid()!=0:
        raise RuntimeError("Run this read-only audit as the server administrator")
    result=collect(BASE,DATABASE)
    out=Path("/root/epimediahub-native-admin-contract.json")
    flags=os.O_WRONLY|os.O_CREAT|os.O_TRUNC
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(out,flags,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as stream:
        os.fchmod(stream.fileno(),0o600)
        json.dump(result,stream,indent=2,ensure_ascii=False)
        stream.write("\n")
    print("NATIVE_ADMIN_CONTRACT_EXPORT_READY")
    print("OUTPUT="+str(out))
    print("TABLES="+str(len(result["tables"])))
    print("ROUTES="+str(len(result["routes"])))
    print("No row values, credentials, stream addresses or session data exported.")
    print("Please review the JSON before uploading it.")

if __name__=="__main__":
    try:
        main()
    except (OSError,ValueError,RuntimeError,sqlite3.Error) as error:
        print("NATIVE_ADMIN_CONTRACT_AUDIT_FAILED:"+type(error).__name__)
        sys.exit(2)
