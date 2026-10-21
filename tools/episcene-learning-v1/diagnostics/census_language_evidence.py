#!/usr/bin/env python3
"""Read-only language evidence census for the mixed 4K EpiScene analysis source.

No player/provider credentials, customer data, titles, asset keys or URLs emitted.
The census helps distinguish genuinely German-labelled queued work from
unknown- and foreign-language work before changing dispatch gates.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json
import sqlite3

DB=Path('/var/lib/epimediahub/provisioning.db')
DE={'de','deu','ger','de-de','de-at','de-ch'}
IT={'it','ita','italian','it-it'}


def parse_codes(raw):
    if raw is None:
        return set(), 'missing'
    try:
        payload=json.loads(raw) if isinstance(raw,str) else raw
    except (json.JSONDecodeError,TypeError,ValueError):
        return set(),'malformed'
    if isinstance(payload,str):
        payload=[payload]
    if not isinstance(payload,list):
        return set(),'malformed'
    out=set()
    for item in payload:
        if isinstance(item,str):
            out.add(item.strip().lower().replace('_','-'))
    return out,'valid' if out else 'missing'


def classify(playlist_id,raw):
    values,quality=parse_codes(raw)
    if quality!='valid':
        return quality
    if playlist_id==8:
        if values & DE and values- DE:
            return 'german_and_other_codes_review'
        if values & DE:
            return 'explicit_de'
        return 'non_de'
    if playlist_id==10:
        return 'explicit_it' if values & IT else 'other_or_unclear'
    return 'not_in_scope'


def census(db):
    required={'skip_jobs','skip_assets','skip_asset_languages'}
    found={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing=required-found
    if missing:
        raise RuntimeError('Missing language data tables: '+','.join(sorted(missing)))
    counts=defaultdict(Counter)
    for pid,state,code in db.execute("""
        SELECT a.playlist_id,j.status,k.codes FROM skip_jobs j
        JOIN skip_assets a USING(asset_key)
        LEFT JOIN skip_asset_languages k USING(asset_key)
        WHERE a.playlist_id IN (8,10) AND a.media_type='episode'
    """):
        counts[(pid,state)][classify(pid,code)]+=1
    result={}
    for (pid,state),items in sorted(counts.items()):
        result.setdefault(str(pid),{})[state]=dict(sorted(items.items()))
    return result


def main():
    if DB.is_symlink() or not DB.is_file():
        raise RuntimeError('Unexpected source SQLite database')
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=20) as con:
        con.execute('PRAGMA query_only=ON')
        summary=census(con)
    print('EPISCENE SPRACHNACHWEIS / NUR LESEN')
    print(json.dumps(summary,indent=2,sort_keys=True))
    print('Warnung: 4K unknown / malformed is NOT German approval.')
    print('No database writes or provider requests performed.')


if __name__=='__main__':
    main()
