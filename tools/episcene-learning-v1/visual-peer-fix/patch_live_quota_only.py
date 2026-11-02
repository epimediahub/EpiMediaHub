#!/usr/bin/env python3
"""Surgically stage 3 reviewed EpiScene retry quotas, preserving all live functions.

This does NOT install anything. Strict old-value and structural preconditions
refuse unknown source shapes; all function/class AST digests remain unchanged.
The actual 1-command installer must pin the complete live source hash, make a
private backup, and check worker-version integrity before/after installation.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
from pathlib import Path
import re

QUOTAS = {
    "MAX_NEW_PER_RUN": (4,6),
    "MAX_DAILY": (8,16),
    "MAX_PER_PLAYLIST": (2,3),
}
ASSIGN = re.compile(r"^(?P<space>\s*)(?P<name>MAX_NEW_PER_RUN|MAX_DAILY|MAX_PER_PLAYLIST)(?P<gap>\s*=\s*)(?P<value>\d+)(?P<comment>\s*(?:#.*)?)$")


def components(tree):
    return [ast.dump(n,include_attributes=False)
            for n in tree.body
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]


def patch(source):
    before=ast.parse(source)
    assignments={}
    for node in before.body:
        if not isinstance(node,ast.Assign) or len(node.targets)!=1:
            continue
        target=node.targets[0]
        if not isinstance(target,ast.Name) or target.id not in QUOTAS:
            continue
        if target.id in assignments:
            raise ValueError("DUPLICATE_QUOTA")
        if not isinstance(node.value,ast.Constant) or type(node.value.value) is not int:
            raise ValueError("NON_LITERAL_QUOTA")
        assignments[target.id]=(node.lineno,node.value.value)
    if set(assignments)!=set(QUOTAS):
        raise ValueError("UNKNOWN_QUOTA_SOURCE")
    raw=source.splitlines(keepends=True)
    for name,(old,new) in QUOTAS.items():
        lineno,value=assignments[name]
        if value not in (old,new):
            raise ValueError("QUOTA_SOURCE_DRIFT")
        line=raw[lineno-1]
        content=line.rstrip("\r\n")
        m=ASSIGN.fullmatch(content)
        if not m or m.group("name")!=name or int(m.group("value"))!=value:
            raise ValueError("UNEXPECTED_QUOTA_LINE")
        if value==old:
            raw[lineno-1]=(m.group("space")+name+m.group("gap")+str(new)+m.group("comment")+line[len(content):])
    result="".join(raw)
    after=ast.parse(result)
    if components(before)!=components(after):
        raise ValueError("FUNCTION_OR_CLASS_CHANGED")
    for name,(_,new) in QUOTAS.items():
        found=[n.value.value for n in after.body
               if isinstance(n,ast.Assign) and len(n.targets)==1 and
               isinstance(n.targets[0],ast.Name) and n.targets[0].id==name]
        if found!=[new]:
            raise ValueError("QUOTA_NOT_APPLIED")
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.source.resolve()==a.output.resolve() or a.source.is_symlink():
        raise SystemExit("STOP: source must be a regular file, output must be separate")
    raw=a.source.read_text(encoding="utf-8")
    changed=patch(raw)
    a.output.write_text(changed,encoding="utf-8")
    print("STAGED: QUOTAS_ONLY, 0 live writes, 0 function changes")

if __name__=="__main__":
    main()
