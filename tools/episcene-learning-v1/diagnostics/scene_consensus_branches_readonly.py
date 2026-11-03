#!/usr/bin/env python3
"""Safe static preflight: EpiScene _compare/analyze gates and branches.

Only parses source syntax, does not import/execute production code or use DB.
Sanitizes arbitrary string values; prints branch/return expressions needed
to locate REVIEW/missing consensus vs confidence/spacing checks.
"""
import ast
import copy
import hashlib
from pathlib import Path

SRC=Path('/opt/epimediahub/provisioning/skip_scene.py')
NAMES=('_compare','analyze','release_ready')
ALLOWED={'REVIEW','AUTO_CONFIRMED','NONE','rejected','review','confidence',
         'status','reason','decision','intro','outro','recap','audio','visual',
         'episcene_consensus','pending','approved','superseded','source',
         'start_ms','end_ms','kind','windows','support','policy',
         'ambiguous','truncated','boundaries_consistent'}
MAX_BRANCHES=95

class HideText(ast.NodeTransformer):
    def visit_Constant(self,node):
        if isinstance(node.value,str) and node.value not in ALLOWED:
            return ast.copy_location(ast.Constant(value='<redacted-string>'),node)
        return node

def safe_expr(node):
    if node is None:return 'none'
    try:
        redacted=HideText().visit(copy.deepcopy(node))
        expr=ast.unparse(redacted)
        return expr[:205]+('...' if len(expr)>205 else '')
    except (SyntaxError,ValueError,RecursionError):
        return 'not_renderable'

def main():
    if SRC.is_symlink() or not SRC.is_file():
        raise RuntimeError('Production source missing or symlink')
    raw=SRC.read_bytes()
    if len(raw)>2000000:raise RuntimeError('Unexpected source size')
    tree=ast.parse(raw.decode('utf-8'),filename=str(SRC))
    print('EPISCENE CONSENSUS BRANCHES / CODE READ ONLY')
    print('skip_scene.py sha256_16:',hashlib.sha256(raw).hexdigest()[:16])
    print('All unrelated string literals are redacted. No DB, imports or worker actions.')
    for name in NAMES:
        hits=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name]
        print('\nFUNCTION',name)
        if len(hits)!=1:
            print('  unavailable_or_ambiguous:',len(hits))
            continue
        fn=hits[0]
        print('  lines:',fn.lineno,'-',fn.end_lineno)
        print('  params:',','.join(a.arg for a in fn.args.args+fn.args.kwonlyargs))
        records=[]
        for n in ast.walk(fn):
            if isinstance(n,ast.If):
                records.append((n.lineno,'IF',safe_expr(n.test)))
            elif isinstance(n,ast.Return):
                records.append((n.lineno,'RETURN',safe_expr(n.value)))
            elif isinstance(n,ast.Raise):
                records.append((n.lineno,'RAISE',safe_expr(n.exc)))
            elif isinstance(n,ast.Call):
                if isinstance(n.func,ast.Name) and n.func.id in ('_compare','capture','store_proposal','publish','release_ready','validate_result'):
                    records.append((n.lineno,'CALL',n.func.id))
        records.sort(key=lambda x:(x[0],x[1]))
        print('  relevant_branch_and_return_count:',len(records))
        for lineno,kind,detail in records[:MAX_BRANCHES]:
            print('  L'+str(lineno)+' '+kind+': '+detail)
        if len(records)>MAX_BRANCHES:
            print('  TRUNCATED:',len(records)-MAX_BRANCHES,'additional branches')
    print('\nNO DATABASE CHANGES; NO PROVIDER CALLS; NO WORKER RESTARTS')

if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError,SyntaxError,UnicodeDecodeError) as e:
        print('BRANCH_AUDIT_STOP:',type(e).__name__,str(e)[:160])
        raise SystemExit(1)
