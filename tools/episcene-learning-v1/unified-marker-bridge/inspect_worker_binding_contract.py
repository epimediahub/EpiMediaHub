#!/usr/bin/env python3
"""EpiScene: read-only structural worker binding report without source or credentials.

Reads allowlisted worker Python modules only. Never imports them or opens
any provider connection. Output has no raw source, SQL text or secret values.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

APP = Path('/opt/epimediahub/provisioning')
TARGETS = {
    'skip_schedule.py': {'select_job': {'66ccd47b3f270d61'}},
    'skip_scene.py': {
        'capture': {'1d717bc5fd36ccdb'},
        'analyze': {'999539f90f059311'},
    },
    'skip_analysis.py': {
        'probe': {'9812694a67d85982'},
        'register_analysis_asset': {'338d30657c562421'},
    },
    'skip_scene_reliability.py': {
        'analysis_playlist': {'1c05272a17fb5700'},
        'capture': {'c876f299266f4c1a'},
        'analyze': {'9256681315517a3e','ac797952bcf1234f'},
        'probe': {'1dc4b9d213d609ea'},
    },
}
SAFE_FIELDS = frozenset(('id','asset_key','source_key','playlist_id','media_type',
    'season','episode','status','segment_type','start_ms','end_ms','duration_ms',
    'enabled','archived','jobs','job','kind','mode','attempts','window',
    'complete','intro','recap','outro','http_status','method'))
SAFE_STATUSES = frozenset(('queued','running','done','partial','review',
    'failed','no_match','no_reference','retry','approved','pending',
    'rejected','superseded','intro','recap','outro'))
SAFE_TABLES = ('skip_jobs','skip_assets','skip_records','skip_analysis_playlists',
    'skip_scene_windows','skip_auto_evidence','skip_presence',
    'skip_identities','skip_auto_identities')
KNOWN_CALLS = frozenset(('select_job','capture','analyze','probe',
    'register_analysis_asset','execute','executemany','fetchone','fetchall',
    'commit','rollback','analysis_playlist','release_ready','_cached_rows',
    'get','db','connect','requests','request','urlopen','open','ffmpeg',
    'run','subprocess','acquire','release','rate','provider','stream',
    'report','sleep','register_asset','dict','jsonify','lease'))
SECRET_NAMING = re.compile(
    r'pass|secret|token|cred|api.?key|bearer|cookie|url|auth|hostname|customer|device|stream', re.I)


def functions(tree):
    found = []
    def recurse(node, parents=()):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.append((child, parents))
                recurse(child, (*parents, child.name))
            elif isinstance(child, (ast.ClassDef, ast.Lambda)):
                recurse(child, parents + (child.name if isinstance(child, ast.ClassDef) else 'lambda',))
            else:
                recurse(child, parents)
    recurse(tree)
    return found


def describe(node, parent):
    sha = hashlib.sha256(
        ast.dump(node, include_attributes=False).encode()).hexdigest()[:16]
    args = node.args
    argnames = [a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]]
    if args.vararg: argnames.append('*'+args.vararg.arg)
    if args.kwarg: argnames.append('**'+args.kwarg.arg)
    argnames = [x if not SECRET_NAMING.search(x) else '<private-arg>'
                for x in argnames]
    calls, fields, statuses, tables, verbs, ret = (
        set(),set(),set(),set(),set(),set())
    loops = 0
    for x in ast.walk(node):
        if isinstance(x,ast.Call):
            f = x.func
            name = f.id if isinstance(f,ast.Name) else (
                f.attr if isinstance(f,ast.Attribute) else '')
            if name in KNOWN_CALLS: calls.add(name)
        elif isinstance(x,ast.Subscript) and isinstance(x.slice,ast.Constant) and isinstance(x.slice.value,str):
            if x.slice.value in SAFE_FIELDS: fields.add(x.slice.value)
        elif isinstance(x,ast.Constant) and isinstance(x.value,str):
            if x.value in SAFE_STATUSES: statuses.add(x.value)
            for table in SAFE_TABLES:
                if table in x.value: tables.add(table)
            for verb in ('SELECT','UPDATE','INSERT','DELETE'):
                if re.search(r'\b'+verb+r'\b',x.value,re.I): verbs.add(verb)
        elif isinstance(x,ast.Return):
            ret.add(type(x.value).__name__ if x.value else 'None')
        elif isinstance(x,(ast.For,ast.While,ast.AsyncFor)):
            loops+=1
    return {'function':node.name,'owner':'/'.join(parent) or 'module',
        'sha16':sha,'args':argnames,'calls':sorted(calls),
        'fields':sorted(fields),'statuses':sorted(statuses),
        'tables':sorted(tables),'sql_verbs':sorted(verbs),
        'returns':sorted(ret),'loops':loops}


def scan(base=APP, targets=TARGETS):
    result={'mode':'EPISCENE_WORKER_BINDING_READ_ONLY',
        'writes':0,'ip_requests':0,'production_code_exported':False,'files':[]}
    for filename,wanted in targets.items():
        path=base/filename
        row={'file':filename,'status':'unavailable','functions':[]}
        if path.is_file() and not path.is_symlink() and path.stat().st_size<=2_000_000:
            try:
                tree=ast.parse(path.read_text(encoding='utf-8'))
                allfn=functions(tree)
                row['functions']=[describe(node,parent)
                    for node,parent in allfn if node.name in wanted]
                matches={name:{f['sha16'] for f in row['functions']
                    if f['function']==name} for name in wanted}
                row['status']='known_shapes' if all(
                    matches[k]==v for k,v in wanted.items()) else 'changed_or_missing_shape'
            except (SyntaxError,UnicodeError,OSError):
                row['status']='invalid_or_unreadable'
        result['files'].append(row)
    result['ready_for_exact_patch_review']=all(
        x['status']=='known_shapes' for x in result['files'])
    return result


if __name__=='__main__':
    print(json.dumps(scan(),ensure_ascii=False,separators=(',',':')))
