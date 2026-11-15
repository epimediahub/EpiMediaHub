#!/usr/bin/env python3
"""Import already connected Raspberry/Tailscale receivers without changing their connection.

Usage:
  python3 import_existing_receivers.py --input /path/to/existing_devices.json

Accepted JSON: a list, or {"devices": [...]}. Each item may contain
name/hostname, device_id/id, tailscale_ip/ip, platform and customer_name.
Unknown customer ownership is intentionally left unassigned.
"""
from __future__ import annotations
import argparse, json, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from app import DB_PATH, init_db

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def cols(con, table): return {r[1] for r in con.execute(f'PRAGMA table_info({table})')}
def ensure_schema(con):
    c=cols(con,'devices')
    for name,typ in [('display_name','TEXT'),('tailscale_ip','TEXT'),('legacy_import','INTEGER NOT NULL DEFAULT 0')]:
        if name not in c: con.execute(f'ALTER TABLE devices ADD COLUMN {name} {typ}')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--dry-run',action='store_true'); args=ap.parse_args()
    data=json.loads(Path(args.input).read_text()); items=data.get('devices',[]) if isinstance(data,dict) else data
    if not isinstance(items,list): raise SystemExit('Input must be a JSON list or {"devices": [...]}')
    init_db(); con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row; ensure_schema(con)
    imported=skipped=0
    for item in items:
        did=str(item.get('device_id') or item.get('id') or item.get('hostname') or item.get('name') or '').strip()
        if not did: skipped+=1; continue
        name=str(item.get('name') or item.get('hostname') or did).strip(); ip=str(item.get('tailscale_ip') or item.get('ip') or '').strip(); platform=str(item.get('platform') or 'enigma2').strip()
        customer_name=str(item.get('customer_name') or '').strip(); customer_id=None
        if customer_name:
            row=con.execute('SELECT id FROM customers WHERE lower(name)=lower(?)',(customer_name,)).fetchone(); customer_id=row['id'] if row else None
        if args.dry_run:
            print(f'WOULD IMPORT {name} ({did}) ip={ip or "-"} customer={customer_name or "unassigned"}'); imported+=1; continue
        # Legacy devices are intentionally not given an app session token. Existing Tailscale connectivity stays untouched.
        # Unassigned devices use a dedicated migration customer so they remain visible without guessing ownership.
        if customer_id is None:
            row=con.execute("SELECT id FROM customers WHERE name='Nicht zugeordnet' LIMIT 1").fetchone()
            if row: customer_id=row['id']
            else: customer_id=con.execute("INSERT INTO customers(name,config_json,enabled,created_at) VALUES('Nicht zugeordnet','{}',1,?)",(now(),)).lastrowid
        token_marker='legacy:'+did
        existing=con.execute('SELECT id FROM devices WHERE customer_id=? AND device_id=?',(customer_id,did)).fetchone()
        if existing:
            con.execute('UPDATE devices SET platform=?,enabled=1,display_name=?,tailscale_ip=?,legacy_import=1 WHERE id=?',(platform,name,ip,existing['id']))
        else:
            con.execute('INSERT INTO devices(customer_id,device_id,platform,session_token_hash,enabled,created_at,display_name,tailscale_ip,legacy_import) VALUES(?,?,?,?,1,?,?,?,1)',(customer_id,did,platform,token_marker,now(),name,ip))
        imported+=1
    if args.dry_run: con.rollback()
    else: con.commit()
    con.close(); print(json.dumps({'imported':imported,'skipped':skipped,'dry_run':args.dry_run}))
if __name__=='__main__': main()
