#!/usr/bin/env python3
"""Read-only, privacy-safe EpiScene production source-path preflight.

Only inspect Python ASTs and service states. This does NOT modify EpiScene,
query providers, restart processes, approve a marker or export source text.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

APP=Path('/opt/epimediahub/provisioning')
LEARNING=Path('/opt/episcene-learning')
LIMIT=750_000
LANGUAGE_PRIORITY=('skip_language_priority','language_priority',
                   'lang_priority','preferred_language','language_rank')
SOURCE_LANGUAGE=('skip_source_preferences','preferred_languages',
                 'language_preferences','source_language')
TARGETS=('skip_', 'safe_release_rollout', 'feedback_learning', 'reference_engine')


def static_module(path):
    """Return only names/counts and integer limits, never source or string values."""
    if path.is_symlink() or not path.is_file():
        return {'status':'UNAVAILABLE_OR_SYMLINK'}
    if path.stat().st_size>LIMIT:
        return {'status':'TOO_LARGE'}
    try:
        content=path.read_text(encoding='utf-8')
        tree=ast.parse(content,filename=path.name)
    except (OSError,UnicodeError,SyntaxError,ValueError):
        return {'status':'UNREADABLE_OR_SYNTAX_ERROR'}
    scope=[]
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            scope.append((node.lineno,node.end_lineno,node.name))
    scope.sort(key=lambda x:(x[1]-x[0],x[0]))
    def owner(node):
        line=node.lineno
        return next((name for start,end,name in scope if start<=line<=end),'module')
    refs={}
    # Inspect AST nodes: comments are intentionally NOT counted as code.
    for node in ast.walk(tree):
        s=''
        if isinstance(node,ast.Name):
            s=node.id.lower()
        elif isinstance(node,ast.Attribute):
            s=node.attr.lower()
        elif isinstance(node,ast.Constant) and isinstance(node.value,str):
            s=node.value.lower()
        if not s:continue
        kinds=[]
        if any(x in s for x in LANGUAGE_PRIORITY):kinds.append('LANGUAGE_PRIORITY')
        if any(x in s for x in SOURCE_LANGUAGE):kinds.append('SOURCE_LANGUAGE_MAPPING')
        for kind in kinds:
            name=owner(node)
            key=(kind,name)
            rec=refs.setdefault(key,{'kind':kind,'scope':name,'hits':0,'line':node.lineno})
            rec['hits']+=1
            rec['line']=min(rec['line'],node.lineno)
    limits={}
    for node in tree.body:
        if not isinstance(node,(ast.Assign,ast.AnnAssign)):continue
        targets=node.targets if isinstance(node,ast.Assign) else [node.target]
        val=node.value
        if not(isinstance(val,ast.Constant) and type(val.value) in (int,float)):continue
        for target in targets:
            if isinstance(target,ast.Name):
                identifier=target.id.upper()
                if any(x in identifier for x in ('TIMEOUT','BUDGET','DEADLINE','MAX_REQUEUE',
                                                  'MAX_DAILY','MAX_NEW_PER_RUN',
                                                  'MAX_PER_PLAYLIST','MAX_ATTEMPTS')):
                    limits[target.id]=val.value
    return {'status':'OK','priority_refs':sorted(refs.values(),key=lambda x:(x['kind'],x['scope'],x['line'])),
            'limits':limits}


def modules(root,learn):
    inventory={}
    for label,directory in (('production',root),('learning',learn)):
        if directory.is_symlink() or not directory.is_dir():
            inventory[label]={'status':'DIRECTORY_UNAVAILABLE'}
            continue
        found={}
        for path in sorted(directory.glob('*.py')):
            if not path.name.startswith(TARGETS) or path.name.startswith('test_'):
                continue
            result=static_module(path)
            if result.get('priority_refs') or result.get('limits') or result.get('status')!='OK':
                found[path.name]=result
        inventory[label]=found
    return inventory


def report(root=APP,learn=LEARNING):
    found=modules(root,learn)
    lang=[]
    source=[]
    for area,paths in found.items():
        if not isinstance(paths,dict):continue
        for filename,info in paths.items():
            for record in info.get('priority_refs',[]):
                item={'area':area,'file':filename,**record}
                if record['kind']=='LANGUAGE_PRIORITY':
                    lang.append(item)
                else:
                    source.append(item)
    return {'mode':'READ_ONLY_EPI_SCENE_SOURCE_CONFLICT_PRECHECK',
            'as_of_utc':datetime.now(timezone.utc).isoformat(),
            'language_priority_references':lang,
            'language_mapping_references':source,
            'numeric_limits':{area+'/'+filename:info['limits']
                              for area,paths in found.items() if isinstance(paths,dict)
                              for filename,info in paths.items() if info.get('limits')},
            'unavailable':{area+'/'+filename:info['status']
                           for area,paths in found.items() if isinstance(paths,dict)
                           for filename,info in paths.items()
                           if info.get('status')!='OK'},
            'summary':{
                'internal_language_priority_locations':len(lang),
                'language_source_mapping_locations':len(source)},
            'caveats':[
                'Static references may be unused; no runtime import proof.',
                'Language matching metadata can remain useful without language-based scheduling.',
                'No source code or SQL contents are exported.',
                'The current provider catalogue must be reconciled separately before stale jobs can be archived.',
                'This probe does not modify configuration or determine whether an automatic release is safe.']}


def brief(data):
    """Screen-sized summary for a phone SSH session; detailed JSON remains available."""
    lines=['EPISCENE CODE CHECK (NUR LESEN)',
           'SPRACH-PRIORITAET Fundstellen: '+str(data['summary']['internal_language_priority_locations'])]
    for item in data['language_priority_references'][:22]:
        lines.append('  '+item['area']+'/'+item['file']+':'+str(item['line'])+
                     ' '+item['scope']+' ('+str(item['hits'])+')')
    if len(data['language_priority_references'])>22:
        lines.append('  weitere Fundstellen: '+str(len(data['language_priority_references'])-22))
    lines.append('QUELLSPRACHE-/MAPPING Fundstellen: '+
                 str(data['summary']['language_source_mapping_locations']))
    for item in data['language_mapping_references'][:10]:
        lines.append('  '+item['area']+'/'+item['file']+':'+str(item['line'])+' '+item['scope'])
    for key,limits in data['numeric_limits'].items():
        compact=','.join(str(name)+'='+str(val) for name,val in sorted(limits.items()))
        lines.append('LIMITS '+key+': '+compact)
    for key,status in data['unavailable'].items():
        lines.append('UNAVAILABLE '+key+': '+status)
    lines.append('Keine Aenderung an Dateien, Freigaben, Diensten oder Playlist-Inhalten.')
    return '\n'.join(lines)


if __name__=='__main__':
    data=report()
    if '--brief' in sys.argv[1:]:
        print(brief(data))
    else:
        print(json.dumps(data,ensure_ascii=False,indent=2))
