#!/usr/bin/env python3
"""Read-only Xtream source-category coverage audit for 4K ANALYSE (id 8).

Uses EpiScene's existing authenticated provider API; no credentials printed.
Reports ONLY counts and recognized category patterns, never titles or URLs.
Does not update DB, reset retries, approve markers or change configuration.
"""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
import re
import sqlite3
import sys

PROD=Path('/opt/epimediahub/provisioning')
DB=Path('/var/lib/epimediahub/provisioning.db')
POSITIVE=re.compile(r'(?i)(?:^|[^a-z0-9])(?:de|deu|deutsch(?:e)?|german)(?:$|[^a-z0-9])')
OTHER=re.compile(r'(?i)(?:^|[^a-z0-9])(?:it|ita|ital(?:iano|iana|ian)?|tr|turk(?:ish|ce)?|en|english|fr|french|ar|arab(?:ic)?|es|spanish|gr|greek)(?:$|[^a-z0-9])')


def category_label(value):
    if not isinstance(value,str):
        return 'unknown'
    de=bool(POSITIVE.search(value))
    other=bool(OTHER.search(value))
    if de and not other:
        return 'unambiguous_de_label'
    if de and other:
        return 'mixed_language_label'
    return 'not_explicitly_de'


def safe_action_names(path):
    """Resolve only allowlisted Xtream API actions from original source AST."""
    if path.is_symlink() or not path.is_file():
        return None
    tree=ast.parse(path.read_text(encoding='utf-8'))
    f=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='provider_listing'),None)
    if f is None:
        return None
    names=[]
    for node in ast.walk(f):
        if not isinstance(node,ast.Call):
            continue
        callee=node.func
        name=callee.id if isinstance(callee,ast.Name) else callee.attr if isinstance(callee,ast.Attribute) else ''
        if name=='provider_api' and len(node.args)>=2 and isinstance(node.args[1],ast.Constant):
            action=node.args[1].value
            if isinstance(action,str):
                names.append(action)
    accepted={'get_series','get_series_categories'}
    return names if len(names)==2 and set(names)==accepted else None


def inspect(categories,series):
    if not isinstance(categories,list) or not isinstance(series,list):
        raise ValueError('Invalid provider response type')
    # Refuse oversized or ambiguous metadata rather than classify by guess.
    if len(categories)>30000 or len(series)>240000:
        raise ValueError('Unexpected provider catalogue size')
    cat_map={}
    dup=set()
    for row in categories:
        if not isinstance(row,dict):
            continue
        ident=row.get('category_id')
        if ident is None:
            continue
        key=str(ident)
        label=category_label(row.get('category_name',''))
        if key in cat_map and cat_map[key]!=label:
            dup.add(key)
        cat_map[key]=label
    for key in dup:
        cat_map[key]='ambiguous_duplicate'
    cnt=Counter()
    ambiguous=Counter()
    for row in series:
        if not isinstance(row,dict):
            continue
        cat=row.get('category_id')
        if isinstance(cat,(list,tuple)):
            labels={cat_map.get(str(x),'unknown_id') for x in cat}
            mark=next(iter(labels)) if len(labels)==1 else 'multiple_categories_review'
        else:
            mark=cat_map.get(str(cat),'missing_or_unknown_id')
        cnt[mark]+=1
    return {
        'category_groups':dict(sorted(Counter(cat_map.values()).items())),
        'series_by_category_evidence':dict(sorted(cnt.items())),
        'category_rows_received':len(categories),
        'series_rows_received':len(series),
        'ambiguous_duplicate_category_ids':len(dup)
    }


def main():
    # No source content, credentials, provider URLs or entry names ever printed.
    if DB.is_symlink() or not DB.is_file() or PROD.is_symlink():
        print('STOP: production DB/source unavailable')
        return 2
    actions=safe_action_names(PROD/'skip_catalogue.py')
    if actions is None:
        print('STOP: provider calls not recognized; no API request made')
        return 2
    sys.path.insert(0,str(PROD))
    try:
        from skip_automation import provider_api
        with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=15) as db:
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            playlist=db.execute('SELECT * FROM skip_analysis_playlists WHERE id=8 AND archived=0').fetchone()
            if playlist is None:
                print('STOP: 4K ANALYSE id=8 not enabled in independent inventory')
                return 2
            playlist=dict(playlist)
        categories=provider_api(playlist,'get_series_categories',lambda:False)
        series=provider_api(playlist,'get_series',lambda:False,_limit=24000000)
        result=inspect(categories,series)
    except Exception as error:
        print('STOP: provider read/classification could not complete ('+type(error).__name__+')')
        return 2
    print('EPISCENE 4K-KATEGORIEN / NUR LESEN')
    for key,value in result.items():
        print(key+': '+str(value))
    print('Wichtig: DE-Kategorien noch NICHT automatisch freigegeben.')
    print('Keine DB-Aenderung, keine Marker-Aktion, keine Geheimnisse ausgegeben.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
