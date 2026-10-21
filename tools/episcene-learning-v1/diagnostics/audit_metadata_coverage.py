#!/usr/bin/env python3
"""EpiScene: read-only, anonymized source-metadata coverage probe.

Distinguish missing `skip_asset_languages.codes` from category/language
evidence stored at *series* level, without exposing playlist credentials,
media titles, provider URLs, asset keys, or raw JSON values.
"""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path
import sqlite3

DB=Path('/var/lib/epimediahub/provisioning.db')
TARGETS=('skip_asset_languages','skip_series_languages','skip_catalogue_series',
         'skip_catalogue_episodes','skip_catalogue_languages','skip_language_priority')


def table_exists(db,name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None


def cols(db,name):
    return {r[1] for r in db.execute('PRAGMA table_info('+name+')')}


def scalar(db,query,params=()):
    return db.execute(query,params).fetchone()[0]


def report(db):
    info={'mode':'READ_ONLY_METADATA_COVERAGE','table_inventory':{},
          'by_playlist':{},'catalogue_payload_keys':{},'warnings':[]}
    info['table_inventory']={t:table_exists(db,t) for t in TARGETS}
    for pid in (8,10):
        p={'series_language_codes':None,'asset_language_codes':None,
           'catalogue_series':None,'catalogue_episodes':None,
           'catalogue_priority_distribution':None}
        if table_exists(db,'skip_catalogue_series'):
            cc=cols(db,'skip_catalogue_series')
            if 'playlist_id' in cc:
                p['catalogue_series']=scalar(db,'SELECT COUNT(*) FROM skip_catalogue_series WHERE playlist_id=?',(pid,))
                if 'payload_json' in cc:
                    hist=Counter();sample=0
                    for (raw,) in db.execute('SELECT payload_json FROM skip_catalogue_series WHERE playlist_id=? ORDER BY rowid LIMIT 1000',(pid,)):
                        try:
                            value=json.loads(raw or '{}')
                        except (TypeError,ValueError):continue
                        if isinstance(value,dict):
                            sample+=1
                            for key in value:
                                if any(x in key.lower() for x in ('lang','category','group','bouquet','audio')):
                                    hist[key]+=1
                    info['catalogue_payload_keys'][str(pid)]={'sampled':sample,'matching_keys':dict(sorted(hist.items()))}
        if table_exists(db,'skip_catalogue_episodes'):
            c=cols(db,'skip_catalogue_episodes')
            if 'playlist_id' in c:
                p['catalogue_episodes']=scalar(db,'SELECT COUNT(*) FROM skip_catalogue_episodes WHERE playlist_id=?',(pid,))
        if table_exists(db,'skip_series_languages'):
            c=cols(db,'skip_series_languages')
            if {'playlist_id','codes'}<=c:
                p['series_language_codes']={
                    'all':scalar(db,'SELECT COUNT(*) FROM skip_series_languages WHERE playlist_id=?',(pid,)),
                    'populated':scalar(db,"SELECT COUNT(*) FROM skip_series_languages WHERE playlist_id=? AND codes IS NOT NULL AND codes NOT IN ('','[]','null')",(pid,))
                }
        if table_exists(db,'skip_asset_languages') and table_exists(db,'skip_assets'):
            a=cols(db,'skip_asset_languages')
            b=cols(db,'skip_assets')
            if {'asset_key','codes'}<=a and {'asset_key','playlist_id'}<=b:
                p['asset_language_codes']={
                    'all':scalar(db,'SELECT COUNT(*) FROM skip_asset_languages l JOIN skip_assets a USING(asset_key) WHERE a.playlist_id=?',(pid,)),
                    'populated':scalar(db,"SELECT COUNT(*) FROM skip_asset_languages l JOIN skip_assets a USING(asset_key) WHERE a.playlist_id=? AND l.codes IS NOT NULL AND l.codes NOT IN ('','[]','null')",(pid,))
                }
        if table_exists(db,'skip_language_priority') and table_exists(db,'skip_assets'):
            c=cols(db,'skip_language_priority')
            if {'asset_key','priority'}<=c:
                p['catalogue_priority_distribution']={str(rank):qty for rank,qty in db.execute(
                    'SELECT l.priority,COUNT(*) FROM skip_language_priority l JOIN skip_assets a USING(asset_key) WHERE a.playlist_id=? GROUP BY l.priority',(pid,))}
        info['by_playlist'][str(pid)]=p
    info['warnings']=[
        'Priority 0 is not verified German: old policy grouped preferred languages.',
        'JSON key names or table presence do not establish correct DE classification.',
        'No catalogue/provider requests or database writes were executed.'
    ]
    return info


def main():
    if DB.is_symlink() or not DB.is_file():
        raise SystemExit('ERROR: Unexpected SQLite path')
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=20) as con:
        con.execute('PRAGMA query_only=ON')
        data=report(con)
    print('EPISCENE METADATEN-CHECK (NUR LESEN)')
    print(json.dumps(data,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
