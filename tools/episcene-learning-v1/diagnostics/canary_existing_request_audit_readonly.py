#!/usr/bin/env python3
"""Audit the existing scheduler request for the German EpiScene audio canary.

Strictly READ-ONLY. Prints no series names, asset keys, provider credentials,
URL or customer information. Never imports production modules or modifies jobs.
"""
import sqlite3
import time
from pathlib import Path

DB = Path('/var/lib/epimediahub/provisioning.db')
LEDGER = 'episcene_audio_cache_canary_v1'
PID = 8
KNOWN_REASONS = {'playback','reference','manual_learning','audio_cache_recovery'}

def cols(con,table):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
        raise RuntimeError('Expected table missing: '+table)
    return {r[1] for r in con.execute('PRAGMA table_info('+table+')')}

def main():
    if DB.is_symlink() or not DB.is_file():
        raise RuntimeError('Production DB not found or symlink')
    con=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True,timeout=25)
    try:
        con.row_factory=sqlite3.Row
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')
        required={
            LEDGER:{'asset_key','playlist_id'},
            'skip_assets':{'asset_key','playlist_id','source_key'},
            'skip_jobs':{'asset_key','status'},
            'skip_schedule_requests':{
                'playlist_id','source_key','reason','expires_at','requested_at',
                'reference_asset','season','episode'
            },
        }
        for table,fields in required.items():
            if not fields<=cols(con,table):
                raise RuntimeError('Unexpected schema: '+table)
        rows=con.execute("""
            SELECT a.source_key, l.asset_key,
                   j.status AS canary_status
              FROM episcene_audio_cache_canary_v1 l
              JOIN skip_assets a ON a.asset_key=l.asset_key
              LEFT JOIN skip_jobs j ON j.asset_key=l.asset_key
             WHERE l.playlist_id=? AND a.playlist_id=?
        """,(PID,PID)).fetchall()
        print('EPISCENE CANARY EXISTING REQUEST AUDIT / NUR LESEN')
        print('Analysis source: 4K ANALYSE')
        print('Recorded canaries:',len(rows))
        if len(rows)!=1:
            print('STOP: expected exactly one German canary')
            return
        row=rows[0]
        print('Canary job status:',row['canary_status'] or 'unknown')
        requests=con.execute("""
            SELECT reason,expires_at,requested_at,reference_asset,season,episode
              FROM skip_schedule_requests
             WHERE playlist_id=? AND source_key=?
        """,(PID,row['source_key'])).fetchall()
        print('Existing same-series requests:',len(requests))
        if not requests:
            print('No same-series request remains; a prior row may have expired or been cleaned.')
            return
        now=int(time.time())
        for req in requests:
            reason=req['reason']
            print('  request_reason:',reason if reason in KNOWN_REASONS else 'OTHER')
            try:
                expires=int(req['expires_at'])
                remaining=expires-now
                print('  request_state:', 'ACTIVE' if remaining>0 else 'EXPIRED')
                print('  remaining_minutes:',max(0,remaining//60))
            except (ValueError,TypeError,OverflowError):
                print('  request_state: UNKNOWN_EXPIRY_FORMAT')
            print('  reference_is_exact_canary:',
                  bool(req['reference_asset']) and req['reference_asset']==row['asset_key'])
            if req['reference_asset']:
                ref=con.execute("SELECT status FROM skip_jobs WHERE asset_key=?",
                                (req['reference_asset'],)).fetchone()
                print('  reference_job_state:',ref['status'] if ref else 'not_registered')
            else:
                print('  reference_job_state: none')
            available=con.execute("""
                SELECT COUNT(*) FROM skip_jobs j
                JOIN skip_assets a ON a.asset_key=j.asset_key
                WHERE a.playlist_id=? AND a.source_key=?
                  AND j.status='queued' AND j.attempts<3
            """,(PID,row['source_key'])).fetchone()[0]
            print('  queued_jobs_in_requested_series:',available)
        print('NO CHANGES: no request overwritten, no queue changes, no worker restart.')
    finally:
        con.close()

if __name__ == '__main__':
    try:
        main()
    except (RuntimeError,sqlite3.Error) as exc:
        print('AUDIT_STOP:',type(exc).__name__,str(exc))
        raise SystemExit(1)
