#!/usr/bin/env python3
"""Guarded schema fix for existing, reviewed EpiScene customer-marker ZIP.

The previous installer restarted provisioning and expected it to initialize
skip_customer_* tables. Here the create-only schema migration is explicit,
atomic and precedes its existing, SHA-pinned backup/restart/rollback logic.

--check: fully read only
--apply: CREATE TABLE / INDEX only, then invoke the existing installer
--verify: verify installed hashes, schema and both running services
No customer/provider streams or analysis-worker restart.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys

BUNDLE=Path('/root/episcene-scoped-fix')
LEGACY_HASH='5cef021b7fc0bbe82910f4b189a1f22736c40ff2deca41faff03495165deef4e'
DB=Path('/var/lib/epimediahub/provisioning.db')
TABLES={
    'skip_customer_asset_claims': {
        'customer_id','playlist_id','asset_key','account_key','source_key','media_type',
        'season','episode','duration_ms','stream_id','extension'},
    'skip_customer_marker_provenance': {
        'record_id','customer_id','playlist_id','account_key','asset_key','source_key',
        'media_type','season','episode','duration_ms'},
}
INDEX='idx_skip_customer_provenance_account'
DDL=(
    '''CREATE TABLE IF NOT EXISTS skip_customer_asset_claims(
      customer_id INTEGER NOT NULL, playlist_id INTEGER NOT NULL,
      asset_key TEXT NOT NULL, account_key TEXT NOT NULL,
      source_key TEXT NOT NULL, media_type TEXT NOT NULL,
      season INTEGER NOT NULL, episode INTEGER NOT NULL,
      duration_ms INTEGER NOT NULL, stream_id TEXT NOT NULL,
      extension TEXT NOT NULL,
      PRIMARY KEY(customer_id,playlist_id,asset_key))''',
    '''CREATE TABLE IF NOT EXISTS skip_customer_marker_provenance(
      record_id INTEGER PRIMARY KEY REFERENCES skip_records(id) ON DELETE CASCADE,
      customer_id INTEGER NOT NULL, playlist_id INTEGER NOT NULL,
      account_key TEXT NOT NULL, asset_key TEXT NOT NULL,
      source_key TEXT NOT NULL, media_type TEXT NOT NULL,
      season INTEGER NOT NULL, episode INTEGER NOT NULL,
      duration_ms INTEGER NOT NULL)''',
    '''CREATE INDEX IF NOT EXISTS idx_skip_customer_provenance_account
      ON skip_customer_marker_provenance(customer_id,playlist_id,account_key,asset_key)''',
)

class Stop(Exception): pass

def original_installer(bundle=BUNDLE):
    path=bundle/'install_customer_scope.py'
    if bundle.is_symlink() or not bundle.is_dir() or path.is_symlink() or not path.is_file():
        raise Stop('ORIGINAL_BUNDLE_UNAVAILABLE')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=LEGACY_HASH:
        raise Stop('ORIGINAL_INSTALLER_HASH_MISMATCH')
    spec=importlib.util.spec_from_file_location('episcene_installer_verified',path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def schema_status(con):
    tables={}
    for name,required in TABLES.items():
        found={x[1] for x in con.execute('PRAGMA table_info('+name+')')}
        if found and found!=required:
            raise Stop('SCOPED_TABLE_CONFLICT')
        tables[name]=bool(found)
    index=con.execute('''SELECT tbl_name FROM sqlite_master
                         WHERE type='index' AND name=?''',(INDEX,)).fetchone()
    if index and index[0]!='skip_customer_marker_provenance':
        raise Stop('SCOPED_INDEX_CONFLICT')
    if index:
        names=[x[2] for x in con.execute('PRAGMA index_info('+INDEX+')')]
        if names!=['customer_id','playlist_id','account_key','asset_key']:
            raise Stop('SCOPED_INDEX_CONFLICT')
    return dict(tables,index_ready=bool(index))

def inspect(database=DB):
    if database.is_symlink() or not database.is_file() or database.parent.is_symlink():
        raise Stop('DATABASE_PATH_UNTRUSTED')
    try:
        with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',
                             uri=True,timeout=10) as db:
            db.execute('PRAGMA query_only=ON')
            required={r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND "
                "name IN ('skip_records','skip_assets','devices','customer_playlists')")}
            if required!={'skip_records','skip_assets','devices','customer_playlists'}:
                raise Stop('ORIGINAL_PRODUCTION_SCHEMA_UNEXPECTED')
            return schema_status(db)
    except sqlite3.Error as exc:
        raise Stop('SQLITE_READ_FAILED') from exc

def migrate(database=DB):
    # Only three CREATE statements, never UPDATE/DELETE of original data.
    try:
        with sqlite3.connect(database,timeout=15,isolation_level=None) as db:
            db.execute('PRAGMA busy_timeout=15000')
            db.execute('BEGIN IMMEDIATE')
            try:
                previous=schema_status(db)
                for sql in DDL:
                    db.execute(sql)
                after=schema_status(db)
                if not all(after.values()):
                    raise Stop('MIGRATION_SCHEMA_NOT_READY')
                db.execute('COMMIT')
                return dict(schema_created=not all(previous.values()),schema_ready=True)
            except BaseException:
                db.execute('ROLLBACK')
                raise
    except sqlite3.Error as exc:
        raise Stop('MIGRATION_TRANSACTION_FAILED') from exc

def run(mode,bundle=BUNDLE,database=DB):
    if os.geteuid()!=0:
        raise Stop('ROOT_REQUIRED')
    old=original_installer(bundle)
    if mode=='verify':
        for filename in old.NAMES:
            if old.digest(old.PROVISION/filename)!=old.EXPECTED_NEW[filename]:
                raise Stop('INSTALLED_SOURCE_NOT_PATCHED')
        if not old.active(old.API_SERVICE) or not old.active(old.ANALYSIS_SERVICE):
            raise Stop('SERVICE_NOT_RUNNING')
        if not all(inspect(database).values()):
            raise Stop('NEW_SCHEMA_NOT_READY')
        return {'mode':'EPISCENE_CUSTOMER_SCOPE_SCHEMA_V2','verified':True,
                'new_tables_ready':True,'api_active':True,
                'analysis_worker_active':True,'worker_restarted_by_tool':False}
    # The old SHA-256-based preflight MUST pass before any SQL is committed.
    try:
        preflight=old.run(apply=False,bundle=bundle)
    except old.Stop as exc:
        raise Stop('ORIGINAL_PREFLIGHT_'+str(exc)) from exc
    if not isinstance(preflight,dict) or preflight.get('preflight')!='PASS':
        raise Stop('ORIGINAL_PREFLIGHT_FAILED')
    before=inspect(database)
    if mode=='check':
        return {'mode':'EPISCENE_CUSTOMER_SCOPE_SCHEMA_V2','preflight':'PASS',
                'database_tables_before':before,'changes_made':0,
                'worker_restarted_by_tool':False}
    if mode!='apply':
        raise Stop('UNKNOWN_MODE')
    migrated=migrate(database)
    try:
        installed=old.run(apply=True,bundle=bundle)
    except old.Stop as exc:
        raise Stop('ORIGINAL_INSTALLER_STOP_'+str(exc)) from exc
    if not installed.get('applied'):
        # Old installer already performed the source-file rollback.
        return {'mode':'EPISCENE_CUSTOMER_SCOPE_SCHEMA_V2','applied':False,
                'reason':installed.get('reason','INSTALLER_FAILED'),
                'rollback_restored':installed.get('rollback_restored',False),
                'schema_tables_preserved':True,'analysis_worker_restarted':False}
    state=inspect(database)
    return {'mode':'EPISCENE_CUSTOMER_SCOPE_SCHEMA_V2','applied':True,
            'new_tables_ready':all(state.values()),
            'new_schema_created':migrated['schema_created'],
            'analysis_worker_still_active':installed.get('analysis_worker_still_active',False),
            'analysis_worker_restarted':False,
            'backup_exists':installed.get('backup_exists',False),
            'api_restarted':installed.get('api_restarted',False)}

def main():
    parser=argparse.ArgumentParser()
    opt=parser.add_mutually_exclusive_group(required=True)
    opt.add_argument('--check',action='store_true')
    opt.add_argument('--apply',action='store_true')
    opt.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    mode='check' if args.check else 'apply' if args.apply else 'verify'
    try:
        result=run(mode)
    except (Stop,sqlite3.Error,OSError,ValueError,SyntaxError,UnicodeError) as exc:
        result={'mode':'EPISCENE_CUSTOMER_SCOPE_SCHEMA_V2',
                'status':'STOP_NO_FURTHER_CHANGES',
                'reason':str(exc) if isinstance(exc,Stop) else 'CHECK_UNAVAILABLE'}
        print(json.dumps(result,sort_keys=True,indent=2))
        return 2
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0 if (mode!='apply' or result.get('applied',False)) else 2

if __name__=='__main__':
    sys.exit(main())
