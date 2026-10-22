#!/usr/bin/env python3
"""Neutralize obsolete EpiScene language-ranking decisions on a known live baseline.

AST-scoped source patcher. No database writes, no installer, no service actions.
A separately reviewed installer must apply the returned files atomically.
"""
from __future__ import annotations
import ast
import hashlib
from pathlib import Path

BASELINE={
    'skip_schedule.py':'73ccc374078c4eeb3d36213be7f2094d0a98ec7bf0277f767276973b7721c440',
    'skip_automation.py':'2e5eb7e178775d3fbb4113560161fbcd5f883251a1c9162f768d49beb4561787',
    'skip_catalogue.py':'943bc691bb81e689ac1c644bdbd033df0ac453fbeb3cea9ada64ba905efb2080',
    'skip_source_preferences.py':'40ca6a40b0399f9da3e223e17d9bc6947ee848ae62215de97b45051688ce91ba',
    'skip_app_capture.py':'ec5023f67fc6670bf1fecc3f6a91a90ef1e1959232256a428d4da6c5a0acfbd5',
}
# Functions in which the ranking is only metadata are left intact.
SIMPLE={
    'skip_schedule.py':{'language_stage':'return 2', 'lane_stage':'return 2'},
    'skip_source_preferences.py':{'preferred_keys':'return []',
                                  'source_stage':'return fallback'},
    'skip_catalogue.py':{'language_priority':'return 2'},
}
NEUTRAL_SQL={
    'COALESCE(l.priority,2)':'(0+2)',
    'COALESCE(l.priority,1)':'(0+2)',
    'COALESCE(lang.priority,1)':'(0+2)',
}
SQL_FUNCTIONS={
    'skip_schedule.py':{'requests','should_pause','select_job'},
    'skip_automation.py':{'discover_one','refresh_online_one'},
    'skip_catalogue.py':{'step'},
    'skip_app_capture.py':{'process_one'},
}
# These catalogue writers continue to maintain the legacy schema with neutral rank.
SETTERS={'skip_catalogue.py':{'set_asset_language','set_series_language'}}

class UnexpectedLiveCode(ValueError):
    pass


def _functions(src):
    try:
        tree=ast.parse(src)
    except SyntaxError as e:
        raise UnexpectedLiveCode('Invalid Python source') from e
    nodes={x.name:x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))}
    return tree,nodes


def rewrite(name,src):
    if name not in BASELINE:
        raise UnexpectedLiveCode('Unknown module name')
    original_tree,nodes=_functions(src)
    targeted=set(SIMPLE.get(name,{}))|SQL_FUNCTIONS.get(name,set())|SETTERS.get(name,set())
    if not targeted<=nodes.keys():
        raise UnexpectedLiveCode('Missing expected function(s): '+str(sorted(targeted-nodes.keys())))
    lines=src.splitlines(keepends=True)
    pieces=[]
    altered=[]
    for fn in targeted:
        node=nodes[fn]
        if node.decorator_list or node.body[0].lineno<=node.lineno:
            raise UnexpectedLiveCode('Unexpected function declaration shape: '+fn)
        initial=node.body[0].lineno-1
        end=node.end_lineno
        fragment=''.join(lines[initial:end])
        if fn in SIMPLE.get(name,{}):
            replacement='    '+SIMPLE[name][fn]+'\n'
        elif fn in SETTERS.get(name,set()):
            replacement='    priority = 2\n'+fragment
        else:
            replacement=fragment
            modified=0
            for old,new in NEUTRAL_SQL.items():
                hits=replacement.count(old)
                if hits:
                    replacement=replacement.replace(old,new)
                    modified+=hits
            if modified==0:
                raise UnexpectedLiveCode('Priority expression unexpectedly absent: '+fn)
        pieces.append((initial,end,replacement,fn))
    for start,end,replacement,fn in sorted(pieces,reverse=True):
        lines[start:end]=replacement.splitlines(keepends=True)
        altered.append(fn)
    patched=''.join(lines)
    after_tree,after_nodes=_functions(patched)
    before_unmodified={x.name:ast.dump(x,include_attributes=False)
                       for x in original_tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))
                       and x.name not in targeted}
    after_unmodified={x.name:ast.dump(x,include_attributes=False)
                      for x in after_tree.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))
                      and x.name not in targeted}
    if before_unmodified!=after_unmodified:
        raise UnexpectedLiveCode('Unexpected change outside allowlisted functions')
    if len(after_nodes)<len(nodes):
        raise UnexpectedLiveCode('Lost function declarations')
    return patched,sorted(altered)


def patch_known_files(root, *, verify_sha=True):
    """Return {filename: bytes}; never change originals."""
    result={}
    for name,expected in BASELINE.items():
        path=Path(root)/name
        if path.is_symlink() or not path.is_file():
            raise UnexpectedLiveCode('Missing or symlink module: '+name)
        contents=path.read_bytes()
        if verify_sha and hashlib.sha256(contents).hexdigest()!=expected:
            raise UnexpectedLiveCode('LIVE CODE DRIFT: '+name)
        patched,_=rewrite(name,contents.decode('utf-8'))
        result[name]=patched.encode('utf-8')
    return result
