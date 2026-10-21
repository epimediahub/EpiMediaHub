#!/usr/bin/env python3
"""Export sanitized EpiScene scheduling functions for a reviewed patch.

READ ONLY. Never copy raw files, env files, provider configuration, credential
values, customer data or database records. Output only allowlisted function
bodies with non-SQL string values redacted and a non-sensitive manifest.
"""
from __future__ import annotations

import ast
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT=Path('/opt/epimediahub/provisioning')
DEST=Path('/tmp/episcene-priority-review.zip')
FUNCTIONS={
 'skip_schedule.py':('language_stage','request_series','requests','should_pause',
                     'select_job','lane_stage'),
 'skip_automation.py':('discover_one','refresh_online_one'),
 'skip_catalogue.py':('language_priority','category_priorities',
                      'set_asset_language','set_series_language',
                      'provider_listing','listing','register_episodes','step'),
 'skip_source_preferences.py':('preferred_keys','source_stage','install','select'),
 'skip_app_capture.py':('process_one',),
}
ALLOWED_LITERAL={
 'queued','running','done','failed','review','partial','no_match',
 'no_reference','pending','approved','rejected','audio','chapter',
 'theintrodb','audio_repetition','auto_audio','episcene','device',
 'episode','movie','series','intro','outro','recap','playback',
 'direct','unknown','none','preferred','analysis','priority',
 'de','it','tr','en','4k','the best','4k analyse',
}
SQL_START=re.compile(r'(?is)^\s*(?:SELECT|WITH|UPDATE|INSERT|DELETE|REPLACE|CREATE|ALTER|DROP|JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|INNER\s+JOIN|ORDER\s+BY|WHERE|AND\s|OR\s)')
SENSITIVE=re.compile(r'(?i)(https?://|password|passwd|secret|token|authorization|credential|api.?key|bearer|cookie|private.?key|[a-z0-9_-]+@[a-z0-9.-]+|\b\d{1,3}(?:\.\d{1,3}){3}\b)')
DOMAIN=re.compile(r'(?i)\b[a-z0-9-]+\.(?:com|net|org|io|de|it|tv|xyz|info|local)\b')
SQL_INCLUDES=re.compile(r'(?is)\b(select|from|join|where|order\s+by|group\s+by|limit|skip_language_priority)\b')


def safe_literal(value):
    s=str(value)
    low=s.strip().lower()
    if low in ALLOWED_LITERAL:
        return s
    if SQL_START.search(s) and SQL_INCLUDES.search(s):
        if SENSITIVE.search(s) or DOMAIN.search(s) or len(s)>12000:
            return '<REDACTED_SQL_SENSITIVE>'
        # Quoted SQL values can contain unexpected provider secrets or personal
        # identifiers. Keep only the known finite set of machine-state labels.
        def clean(match):
            value=match.group(0)[1:-1].replace("''","'")
            return match.group(0) if value.strip().lower() in ALLOWED_LITERAL else "'<REDACTED>'"
        return SQL_QUOTED.sub(clean,s)
    return '<REDACTED>'


class Redact(ast.NodeTransformer):
    def visit_Constant(self,node):
        if isinstance(node.value,str):
            return ast.copy_location(ast.Constant(value=safe_literal(node.value)),node)
        if type(node.value) in (int,float) and abs(node.value)>100_000_000:
            return ast.copy_location(ast.Constant(value=0),node)
        return node
    def visit_JoinedStr(self,node):
        pieces=[]
        for p in node.values:
            if isinstance(p,ast.Constant) and isinstance(p.value,str):
                pieces.append(ast.copy_location(ast.Constant(value=safe_literal(p.value)),p))
            else:
                pieces.append(self.visit(p))
        node.values=pieces
        return node


def collect(root=ROOT):
    manifest={'schema':1,'mode':'SANITIZED_SOURCE_ONLY','generated_utc':datetime.now(timezone.utc).isoformat(),
              'modules':{},'caveat':'No raw files or secrets; verify snippets against source locally before applying any patch.'}
    exported={}
    for name,selected in FUNCTIONS.items():
        path=root/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size>750000:
            manifest['modules'][name]={'status':'UNAVAILABLE'}
            continue
        try:
            source=path.read_text(encoding='utf-8')
            tree=ast.parse(source)
        except (OSError,UnicodeError,SyntaxError):
            manifest['modules'][name]={'status':'UNREADABLE'}
            continue
        functions=[node for node in tree.body
                   if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))
                   and node.name in selected]
        details=[]
        output=[]
        for fn in functions:
            fragment=copy.deepcopy(fn)
            fragment.decorator_list=[]
            sanitized=Redact().visit(fragment)
            ast.fix_missing_locations(sanitized)
            safe=ast.unparse(sanitized)
            details.append({'function':fn.name,'line':fn.lineno,
                            'end_line':fn.end_lineno,
                            'ast_sha256':hashlib.sha256(ast.dump(fn,include_attributes=False).encode()).hexdigest()[:20]})
            output.append(safe)
        exported[name]='\n\n'.join(output)+'\n'
        manifest['modules'][name]={'status':'OK','function_count':len(functions),
                                   'functions':details,'file_sha256':hashlib.sha256(source.encode()).hexdigest()}
    return manifest,exported


def write_package(dest=DEST,root=ROOT):
    if dest.is_symlink():
        raise RuntimeError('Refusing symlink destination')
    m,ex=collect(root)
    # Never copy raw module bytes into the output archive.
    with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',json.dumps(m,ensure_ascii=False,indent=2))
        for name,source in ex.items():
            z.writestr('sanitized/'+name,source)
    dest.chmod(0o600)
    return m


if __name__=='__main__':
    info=write_package()
    print('EPISCENE CODE EXTRACT: '+str(DEST))
    for name,item in info['modules'].items():
        print(name+': '+str(item.get('function_count',0))+' functions ('+item['status']+')')
    print('Dies ist ein BEREINIGTES Quellcode-Archiv (nur gezielte Funktionen).')
    print('Keine Datenbankabfrage, keine Geheimnisse absichtlich kopiert, keine Produktionsaenderungen.')
    print('Bitte vor dem Teilen auf vertrauliche Inhalte pruefen.')
