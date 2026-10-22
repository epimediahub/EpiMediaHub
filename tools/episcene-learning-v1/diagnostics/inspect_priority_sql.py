#!/usr/bin/env python3
"""EpiScene: privacy-safe read-only SQL decision audit from active source files.

Output exposes ONLY identifiers / numeric operators from priority-bearing SQL
or AST condition shapes. It does NOT execute production code, query the DB,
reveal SQL literals, provider endpoints, customer names or credentials.
"""
from __future__ import annotations
import ast
import hashlib
import json
import re
from pathlib import Path

ROOT=Path('/opt/epimediahub/provisioning')
FILES={
    'skip_schedule.py':('language_stage','request_series','requests',
                        'should_pause','select_job','lane_stage'),
    'skip_automation.py':('discover_one','refresh_online_one'),
    'skip_catalogue.py':('step','register_episodes','listing','language_priority'),
    'skip_source_preferences.py':('preferred_keys','source_stage','select'),
    'skip_app_capture.py':('process_one',),
}
TERMS=('skip_language_priority','language_priority','source_language',
       'preferred_languages','language_preferences','category_priorities')
IDENT=re.compile(r'^[a-zA-Z_][a-zA-Z0-9_.]*$')
JOIN=re.compile(r'\b(left\s+join|inner\s+join|join)\s+(skip_language_priority|skip_source_preferences)\b(?:\s+(?:as\s+)?([a-z][a-z0-9_]*))?',re.I)
REF=re.compile(r'(?<![a-zA-Z0-9_])([a-z][a-z0-9_]*\.(?:priority|language_priority|source_language)|language_priority|skip_language_priority)(?![a-zA-Z0-9_])',re.I)
PRIOR_CMP=re.compile(r'(?:\b[a-z][a-z0-9_]*\.)?(?:language_priority|priority|source_language)\s*(?:=|<|>|<=|>=|!=|<>|\bin\b)\s*(?:\?|\d+|null|true|false)',re.I)


def inspect_file(path,functions):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>750000:
        return {'status':'UNAVAILABLE'}
    try:
        source=path.read_text(encoding='utf-8')
        tree=ast.parse(source)
    except (OSError,UnicodeError,SyntaxError):
        return {'status':'UNREADABLE'}
    digest=hashlib.sha256(source.encode('utf-8')).hexdigest()[:20]
    found={}
    for fn in (n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
               and n.name in functions):
        joins=set();referenced=set();compares=set(); sql_order=0; sql_where=0
        ifs=set(); sort_calls=0
        for node in ast.walk(fn):
            if isinstance(node,ast.Constant) and isinstance(node.value,str):
                sql=node.value
                if not any(t in sql.lower() for t in TERMS):continue
                # Only whitelisted SQL identifier / numeric comparator fragments
                # are exposed. Never disclose a complete statement.
                for join in JOIN.findall(sql):
                    joins.add((join[0].lower().replace('  ',' '),join[1].lower(),join[2].lower()))
                for ref in REF.findall(sql):
                    referenced.add(ref.lower())
                for cmp in PRIOR_CMP.findall(sql):
                    if len(cmp)<=90: compares.add(cmp.lower())
                if re.search(r'\border\s+by\b',sql,re.I): sql_order+=1
                if re.search(r'\bwhere\b',sql,re.I): sql_where+=1
            elif isinstance(node,(ast.If,ast.IfExp,ast.While)):
                names={str(x.id).lower() for x in ast.walk(node.test) if isinstance(x,ast.Name)}
                attrs={str(x.attr).lower() for x in ast.walk(node.test) if isinstance(x,ast.Attribute)}
                relevant=sorted((names|attrs)&set(TERMS))
                if relevant:ifs.add('+'.join(relevant))
            elif isinstance(node,ast.Call):
                method=node.func
                method=(method.id if isinstance(method,ast.Name)
                        else method.attr if isinstance(method,ast.Attribute) else '')
                if method in ('sort','sorted'):sort_calls+=1
        found[fn.name]={'line':fn.lineno,'joins':[list(x) for x in sorted(joins)],
                        'priority_columns':sorted(referenced),
                        'priority_comparisons':sorted(compares),
                        'priority_sql_with_order_by':sql_order,
                        'priority_sql_with_where':sql_where,
                        'python_priority_conditions':sorted(ifs),
                        'python_sort_calls':sort_calls}
    return {'status':'OK','sha256_prefix':digest,'functions':found}


def report(root=ROOT):
    return {filename:inspect_file(root/filename,functions)
            for filename,functions in FILES.items()}


def brief(data):
    lines=['EPISCENE PRIORITY SQL CHECK (NUR LESEN)']
    for name,info in data.items():
        lines.append('--- '+name+' '+info.get('sha256_prefix',info['status'])+' ---')
        for fn,entry in info.get('functions',{}).items():
            lines.append(fn+' @'+str(entry['line'])+' joins='+str(entry['joins'])+
                         ' cols='+','.join(entry['priority_columns'])+
                         ' ORDER='+str(entry['priority_sql_with_order_by'])+
                         ' WHERE='+str(entry['priority_sql_with_where'])+
                         ' PYIF='+','.join(entry['python_priority_conditions']))
            if entry['priority_comparisons']:
                lines.append('   CONDITIONS '+','.join(entry['priority_comparisons'][:5]))
    lines.append('Keine Geheimnisse, Quelltexte, Datenbankdaten oder Aenderungen.')
    return '\n'.join(lines)


if __name__=='__main__':
    print(brief(report()))
