#!/usr/bin/env python3
"""Read-only EpiScene ACTIVE worker wiring inventory; no source lines, SQL or credentials."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path

BASE=Path("/opt/epimediahub/provisioning")
FILES=("skip_analysis_worker.py","skip_automation.py","skip_schedule.py")
TERMS=("run","worker","job","analy","process","main","probe","scene",
       "select","capture","release","mark","complete","update","claim","finish","start")
CALLS=frozenset(("select_job","analyze","probe","capture","get","db","execute",
    "executemany","fetchone","fetchall","commit","rollback","update_job",
    "finish_job","complete_job","register_analysis_asset","heartbeat",
    "run","main","start","process","process_job","mark_job","set_status",
    "save","release","close","lock","unlock"))
FIELDS=frozenset(("id","asset_key","source_key","playlist_id","kind","status",
    "season","episode","duration_ms","media_type","intro","outro","recap",
    "start_ms","end_ms","attempts","worker_id","job_id"))
STATUSES=frozenset(("queued","running","done","partial","review","failed",
                    "no_match","no_reference","pending","intro","outro","recap"))
TABLES=("skip_jobs","skip_assets","skip_records","skip_auto_evidence",
        "skip_analysis_playlists","skip_presence","skip_analysis_sources")

def _functions(tree):
    found=[]
    def visit(node,owner=()):
        for child in ast.iter_child_nodes(node):
            if isinstance(child,(ast.FunctionDef,ast.AsyncFunctionDef)):
                found.append((child,owner))
                visit(child,(*owner,child.name))
            elif isinstance(child,ast.ClassDef):
                visit(child,(*owner,child.name))
            else:
                visit(child,owner)
    visit(tree)
    return found

def _name(call):
    x=call.func
    return x.id if isinstance(x,ast.Name) else (
        x.attr if isinstance(x,ast.Attribute) else "")

def _summary(node,owner):
    sha=hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()[:16]
    row={"name":node.name,"owner":"/".join(owner) or "module",
         "sha16":sha,"arg_count":len(node.args.posonlyargs)+
         len(node.args.args)+len(node.args.kwonlyargs)}
    calls=set();keys=set();literals=set();tables=set();returns=set()
    for n in ast.walk(node):
        if isinstance(n,ast.Call):
            if _name(n) in CALLS:calls.add(_name(n))
        elif isinstance(n,ast.Subscript) and isinstance(n.slice,ast.Constant):
            if type(n.slice.value) is str and n.slice.value in FIELDS:
                keys.add(n.slice.value)
        elif isinstance(n,ast.Constant) and isinstance(n.value,str):
            if n.value in STATUSES:literals.add(n.value)
            for t in TABLES:
                if t in n.value:tables.add(t)
        elif isinstance(n,ast.Return):
            returns.add(type(n.value).__name__ if n.value else "None")
    row.update(calls=sorted(calls),keys=sorted(keys),statuses=sorted(literals),
               tables=sorted(tables),returns=sorted(returns))
    return row

def scan(base=BASE):
    out={"mode":"EPISCENE_ACTIVE_RUNTIME_READ_ONLY",
         "production_writes":0,"provider_requests":0,
         "customer_data_exported":False,"source_lines_exported":False,"files":{}}
    for name in FILES:
        p=base/name
        if p.is_symlink() or not p.is_file() or p.stat().st_size>2_000_000:
            out["files"][name]={"status":"UNAVAILABLE"}
            continue
        try:
            tree=ast.parse(p.read_text(encoding="utf-8"))
            matches=[(n,owner) for n,owner in _functions(tree)
                     if any(x in n.name.lower() for x in TERMS)]
            out["files"][name]={"status":"OK","relevant_functions":len(matches),
                                "functions":[_summary(n,owner) for n,owner in matches[:30]]}
        except (OSError,SyntaxError,UnicodeError):
            out["files"][name]={"status":"UNREADABLE"}
    return out

if __name__=="__main__":
    print(json.dumps(scan(),ensure_ascii=False,separators=(",",":")))
