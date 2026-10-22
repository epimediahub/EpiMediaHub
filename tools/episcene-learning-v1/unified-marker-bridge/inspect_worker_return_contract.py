#!/usr/bin/env python3
"""Read-only outcome contract for exact on-server EpiScene worker functions.

We need to know how an existing job reports 'done', 'review', 'partial' and
missing types before binding the Knowledge-First planner. Never imports
production code, reads DB, prints source lines, SQL, provider URLs, values or
credentials, or modifies files.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

BASE=Path("/opt/epimediahub/provisioning")
EXPECTED={
    "skip_schedule.py": {"select_job": ("66ccd47b3f270d61",)},
    "skip_scene.py": {"analyze": ("999539f90f059311",)},
    "skip_scene_reliability.py": {"analyze": ("9256681315517a3e","ac797952bcf1234f")},
}
STATUS={"done","partial","review","failed","no_match","no_reference",
        "running","queued","pending","intro","recap","outro"}
NAMES={"status","kind","result","job","asset","markers","start_ms","end_ms",
       "episode","duration_ms","segments","detail","error","success"}
KNOWN_CALLS={"dict","tuple","list","analyze","capture","probe","get",
             "ready","result","jsonify","int","bool","str","len"}
MAX_SIZE=2_000_000


def _expr(node):
    if node is None: return "None"
    if isinstance(node,ast.Constant):
        return "Literal:"+node.value if isinstance(node.value,str) and node.value in STATUS else "Literal"
    if isinstance(node,ast.Name):
        return "Var:"+node.id if node.id in NAMES else "Var"
    if isinstance(node,ast.Tuple):return "Tuple("+",".join(_expr(v) for v in node.elts[:8])+")"
    if isinstance(node,ast.List):return "List("+str(len(node.elts))+")"
    if isinstance(node,ast.Dict):
        keys=sorted(k.value for k in node.keys if isinstance(k,ast.Constant) and
                    isinstance(k.value,str) and k.value in NAMES)
        return "Dict("+",".join(keys)+")"
    if isinstance(node,ast.Call):
        f=node.func
        name=f.id if isinstance(f,ast.Name) else f.attr if isinstance(f,ast.Attribute) else ""
        return "Call:"+(name if name in KNOWN_CALLS else "other")
    if isinstance(node,ast.IfExp):return "Conditional("+_expr(node.body)+","+_expr(node.orelse)+")"
    if isinstance(node,ast.BoolOp):return "BooleanExpression"
    if isinstance(node,ast.BinOp):return "BinaryExpression"
    return type(node).__name__


def summarize(source, targets):
    tree=ast.parse(source)
    functions=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
               and n.name in targets]
    seen={name:[] for name in targets}
    for fn in functions:
        digest=hashlib.sha256(ast.dump(fn,include_attributes=False).encode()).hexdigest()[:16]
        if digest not in targets[fn.name]:
            seen[fn.name].append({"shape":"UNEXPECTED","sha16":digest})
            continue
        returns=[]
        for n in ast.walk(fn):
            if isinstance(n,ast.Return):
                grammar=_expr(n.value)
                if grammar not in returns:returns.append(grammar)
        calls=set()
        for n in ast.walk(fn):
            if isinstance(n,ast.Call):
                f=n.func
                name=f.id if isinstance(f,ast.Name) else f.attr if isinstance(f,ast.Attribute) else ""
                if name in KNOWN_CALLS:calls.add(name)
        seen[fn.name].append({
            "shape":"EXPECTED","sha16":digest,
            "returns":returns[:24],
            "calls_allowlisted":sorted(calls),
            "has_final_return":isinstance(fn.body[-1],ast.Return) if fn.body else False,
        })
    return seen


def scan(root=BASE, expected=EXPECTED):
    result={"mode":"EPISCENE_RETURN_CONTRACT_READ_ONLY",
            "production_writes":0,"provider_requests":0,
            "source_text_exported":False,"files":{}}
    for filename,requested in expected.items():
        p=root/filename
        if not p.is_file() or p.is_symlink() or p.stat().st_size>MAX_SIZE:
            result["files"][filename]={"status":"UNAVAILABLE"};continue
        try:
            contents=summarize(p.read_text(encoding="utf-8"),requested)
            all_good=all(sorted(x["sha16"] for x in contents[k]
                                if x["shape"]=="EXPECTED") == sorted(requested[k]) and
                         all(x["shape"]=="EXPECTED" for x in contents[k])
                         for k in requested)
            result["files"][filename]={"status":"EXPECTED" if all_good else "CHANGED",
                                       "functions":contents}
        except (SyntaxError,UnicodeError,OSError,ValueError):
            result["files"][filename]={"status":"UNREADABLE"}
    result["exact_shape_gate"]=all(x["status"]=="EXPECTED"
                                   for x in result["files"].values())
    return result


if __name__=="__main__":
    print(json.dumps(scan(),ensure_ascii=False,separators=(",",":")))
