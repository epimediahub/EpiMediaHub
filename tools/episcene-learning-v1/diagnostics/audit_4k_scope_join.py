#!/usr/bin/env python3
"""EpiScene 4K read-only category->series->episode eligibility coverage check.

The mixed provider has no per-episode language codes. This check determines how
many existing EpiScene jobs can be mapped to unambiguous German-labelled Xtream
series, before any enforcement change is permitted. It does not modify files,
SQLite rows, devices, provider catalogue or machine marker decisions.

Never prints provider endpoints, credentials, category names, title, IDs or URLs.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import sqlite3
import sys
import re

_DE=re.compile(r'(?i)(?:^|[^a-z0-9])(?:de|deu|deutsch(?:e)?|german)(?:$|[^a-z0-9])')
_OTHER=re.compile(r'(?i)(?:^|[^a-z0-9])(?:it|ita|ital(?:iano|iana|ian)?|tr|turk(?:ish|ce)?|en|english|fr|french|ar|arab(?:ic)?|es|spanish|gr|greek)(?:$|[^a-z0-9])')


def category_label(value):
    if not isinstance(value,str):
        return 'unknown'
    german=bool(_DE.search(value))
    other=bool(_OTHER.search(value))
    return 'unambiguous_de_label' if german and not other else 'mixed_language_label' if german else 'not_explicitly_de'

ROOT=Path('/opt/epimediahub/provisioning')
DB=Path('/var/lib/epimediahub/provisioning.db')
PLAYLIST=8
MAX_SERIES=240000
BATCH_SIZE=350


def safe_series_ids(categories, series):
    if not isinstance(categories,list) or not isinstance(series,list):
        raise ValueError('unexpected provider response')
    if len(series)>MAX_SERIES or len(categories)>30000:
        raise ValueError('unexpected provider catalogue size')
    categories_by_id={}
    for row in categories:
        if not isinstance(row,dict) or row.get('category_id') is None:
            continue
        ident=str(row['category_id'])
        label=category_label(row.get('category_name',''))
        # Duplicate/unstable category definitions fail closed.
        if ident in categories_by_id and categories_by_id[ident]!=label:
            categories_by_id[ident]='ambiguous_duplicate'
        else:
            categories_by_id[ident]=label
    by_series_id={}
    conflicts=set()
    duplicate_count=0
    for row in series:
        if not isinstance(row,dict):
            continue
        ident=row.get('series_id')
        if ident is None:
            continue
        ident=str(ident)
        if not ident.isdecimal() or len(ident)>20:
            continue
        cats=row.get('category_id')
        if isinstance(cats,(list,tuple)):
            labels={categories_by_id.get(str(x),'unknown') for x in cats}
            chosen=next(iter(labels)) if len(labels)==1 else 'mixed_categories'
        else:
            chosen=categories_by_id.get(str(cats),'unknown')
        if ident in by_series_id:
            duplicate_count+=1
            if by_series_id[ident]!=chosen:
                conflicts.add(ident)
        by_series_id[ident]=chosen
    eligible={key for key,val in by_series_id.items()
              if val=='unambiguous_de_label' and key not in conflicts}
    return eligible,{
        'provider_series_rows':len(series),
        'distinct_series_ids':len(by_series_id),
        'eligible_series_ids':len(eligible),
        'duplicate_series_rows':duplicate_count,
        'conflicting_series_ids':len(conflicts),
        'categories_seen':len(categories)
    }


def local_coverage(db, eligible):
    tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required={'skip_catalogue_episodes','skip_assets','skip_jobs'}
    if required-tables:
        raise ValueError('missing expected local episode/job tables')
    fields={row[1] for row in db.execute('PRAGMA table_info(skip_catalogue_episodes)')}
    if not {'playlist_id','series_id','asset_key'}<=fields:
        raise ValueError('catalogue episode mapping schema mismatch')
    covered=set()
    matched_rows=0
    # Read-only chunked IN predicates. No temp tables or DB writes.
    ids=sorted(eligible)
    for n in range(0,len(ids),BATCH_SIZE):
        slice_=ids[n:n+BATCH_SIZE]
        sql=('SELECT DISTINCT e.asset_key FROM skip_catalogue_episodes e '
             'JOIN skip_assets a ON a.asset_key=e.asset_key '
             'WHERE e.playlist_id=? AND a.playlist_id=? AND e.series_id IN ('+
             ','.join('?' for _ in slice_)+')')
        matches=db.execute(sql,(PLAYLIST,PLAYLIST,*slice_))
        for (key,) in matches:
            covered.add(key)
            matched_rows+=1
    all_jobs=Counter()
    allowed_jobs=Counter()
    for asset,status in db.execute("""
       SELECT a.asset_key,j.status
       FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
       WHERE a.playlist_id=? AND a.media_type='episode'
    """,(PLAYLIST,)):
        all_jobs[status]+=1
        if asset in covered:
            allowed_jobs[status]+=1
    denominator=db.execute('SELECT COUNT(DISTINCT asset_key) FROM skip_catalogue_episodes WHERE playlist_id=?',
                           (PLAYLIST,)).fetchone()[0]
    return {
      'catalogue_episode_assets':denominator,
      'catalogue_assets_matching_de_category':len(covered),
      'mapping_row_matches':matched_rows,
      'jobs_by_status':dict(sorted(all_jobs.items())),
      'mapped_german_category_jobs_by_status':dict(sorted(allowed_jobs.items())),
      'not_mapped_jobs_by_status':dict(sorted((all_jobs-allowed_jobs).items()))
    }


def run_report(categories,series,db):
    series_ids,provider=safe_series_ids(categories,series)
    local=local_coverage(db,series_ids)
    return {'mode':'READ_ONLY_4K_ELIGIBILITY_JOIN',
            'playlist_id':PLAYLIST,
            'provider':provider,
            'local':local,
            'limitations':[
              'German-labelled provider category is metadata, not verified German audio.',
              'An unmapped or multi-category series is not eligible.',
              'No source inclusion/exclusion decision has been deployed.',
              'Result is a point-in-time snapshot of a temporary provider access.'
            ]}


def main():
    if DB.is_symlink() or not DB.is_file() or ROOT.is_symlink() or not ROOT.is_dir():
        print('STOP: expected EpiScene paths unavailable')
        return 2
    sys.path.insert(0,str(ROOT))
    try:
        from skip_automation import provider_api
        with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=30) as db:
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            playlist=db.execute('SELECT * FROM skip_analysis_playlists WHERE id=? AND archived=0',(PLAYLIST,)).fetchone()
            if playlist is None:
                print('STOP: independent 4K analysis playlist unavailable')
                return 2
            playlist=dict(playlist)
            categories=provider_api(playlist,'get_series_categories',lambda:False)
            series=provider_api(playlist,'get_series',lambda:False,_limit=24000000)
            summary=run_report(categories,series,db)
    except (OSError,TypeError,ValueError,KeyError,sqlite3.Error) as error:
        print('CHECK STOP: '+type(error).__name__+
              '; no changes performed. Provider or local catalogue mapping may be unavailable.')
        return 2
    print('EPISCENE 4K JOIN-KONTROLLE / NUR LESEN')
    for name,items in summary.items():
        if isinstance(items,dict):
            print(name+':')
            for k,v in items.items():
                print('  '+k+': '+str(v))
    print('Keine DB-Schreibzugriffe, keine Freigaben, keine Zugangsdaten ausgegeben.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
