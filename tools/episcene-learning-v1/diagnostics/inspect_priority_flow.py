#!/usr/bin/env python3
"""EpiScene: inspect active language-priority decisions, never print code or secrets.

No DB access, imports of production modules, provider requests or file writes.
"""
import ast
import json
import re
from pathlib import Path

ROOT=Path('/opt/epimediahub/provisioning')
FILES=('skip_schedule.py','skip_automation.py','skip_catalogue.py',
       'skip_source_preferences.py','skip_scene_reliability.py',
       'skip_app_capture.py','skip_analysis_worker.py',
       'skip_progress.py','skip_markers.py')
TOKENS=('skip_language_priority','language_priority','preferred_languages',
        'language_preferences','source_language','category_priorities')
FUNCTIONS=('discover_one','refresh_online_one','step','listing',
           'register_episodes','select','preference','category_priorities',
           'language_priority','process_one','schedule_view','overview')
DANGER=re.compile(r'(?i)(password|secret|token|api.key|authorization|cookie|https?://)')


def classify(node):
    terms=[]
    for leaf in ast.walk(node):
        if isinstance(leaf,(ast.Name,ast.Attribute)):
            terms.append((leaf.id if isinstance(leaf,ast.Name) else leaf.attr).lower())
        elif isinstance(leaf,ast.Constant) and isinstance(leaf.value,str):
            s=leaf.value.lower()
            terms += [term for term in TOKENS if term in s]
            if 'order by' in s:terms.append('sql_order_by')
            if 'join ' in s:terms.append('sql_join')
            if 'where ' in s:terms.append('sql_where')
    return set(terms)


def inspect_path(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>750000:
        return {'status':'unavailable'}
    try: tree=ast.parse(path.read_text(encoding='utf-8'))
    except (OSError,UnicodeError,SyntaxError):
        return {'status':'unreadable'}
    details=[]
    for fn in (node for node in ast.walk(tree) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))):
        refs=set()
        calls=set()
        shapes=set()
        for node in ast.walk(fn):
            # Do not include nested function bodies when reporting their parent.
            if isinstance(node,(ast.Name,ast.Attribute,ast.Constant)):
                uses=classify(node)
                for term in TOKENS:
                    if term in uses:refs.add(term)
                shapes.update(x for x in uses if x.startswith('sql_'))
            if isinstance(node,ast.Call):
                target=node.func
                if isinstance(target,ast.Name):name=target.id
                elif isinstance(target,ast.Attribute):name=target.attr
                else:continue
                if name in ('sorted','sort','select','preference','language_priority',
                            'category_priorities','step','request_series','discover_one',
                            'schedule','register_episodes','listing'):
                    calls.add(name)
        if refs or (fn.name in FUNCTIONS and calls):
            details.append({'fn':fn.name,'line':fn.lineno,
                            'priority_refs':sorted(refs),'sql_shapes':sorted(shapes),
                            'calls':sorted(calls)})
    return {'status':'ok','functions':details}


def main():
    print('EPISCENE ENTSCHEIDUNGSPFADE (NUR LESEN)')
    checked=0
    for filename in FILES:
        info=inspect_path(ROOT/filename)
        if info['status']!='ok':
            print(filename+': '+info['status'])
            continue
        records=info['functions']
        if not records:continue
        checked+=1
        print('--- '+filename+' ---')
        for row in records[:20]:
            print(str(row['line'])+' '+row['fn']+
                  ' refs='+','.join(row['priority_refs'])+
                  ' sql='+','.join(row['sql_shapes'])+
                  ' calls='+','.join(row['calls']))
        if len(records)>20:
            print('... '+str(len(records)-20)+' weitere')
    print('MODULE MIT POTENZIELLER SPRACH-/AUSWAHLLOGIK: '+str(checked))
    print('Nur statische Code-Analyse; kein Nachweis des geladenen Importpfads.')
    print('Keine Änderungen an Datenbank, Dateien, Markern oder Diensten.')


if __name__=='__main__':
    main()
