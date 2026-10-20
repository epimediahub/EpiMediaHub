"""Narrow, audited native Admin metadata edits.

Only customer/reseller *display names* are editable here. Device assignment,
playlist credentials, reseller passwords, customer configuration, VPN
and license data are deliberately outside this module.

The existing web/dashboard business actions remain the authority for any
write with provisioning-side effects. Native renames touch no config_json,
credentials, devices, entitlement state or playlist contents.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import uuid

NAME=re.compile(r"^[^\x00-\x1f\x7f<>]{1,140}$")
TABLES={
    "customers":"customers",
    "resellers":"resellers",
}
MAX_BLOB=140

class EditUnavailable(RuntimeError):
    pass

def _canonical(value):
    if not isinstance(value,str):
        raise ValueError("name required")
    result=value.strip()
    if not NAME.fullmatch(result) or not result or len(result.encode("utf-8"))>MAX_BLOB*4:
        raise ValueError("invalid display name")
    return result

def _uuid(value):
    try:
        if not isinstance(value,str) or len(value)>50 or str(uuid.UUID(value))!=value:
            raise ValueError("invalid request id")
        return value
    except (TypeError,ValueError,AttributeError):
        raise ValueError("invalid request id")

def _database(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise EditUnavailable("database missing")
    conn=sqlite3.connect(path.resolve(),timeout=6)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

def rename(path,kind,entity_id,expected_name,new_name,request_id):
    if kind not in TABLES:
        raise ValueError("unknown account type")
    if not isinstance(entity_id,int) or not 0<entity_id<2**63:
        raise ValueError("invalid account")
    expected=_canonical(expected_name)
    new=_canonical(new_name)
    key=_uuid(request_id)
    con=_database(path)
    try:
        con.execute("BEGIN IMMEDIATE")
        table=TABLES[kind]
        columns={row["name"] for row in con.execute('PRAGMA table_info("'+table+'")')}
        if not {"id","name"}<=columns:
            raise EditUnavailable("unsupported account schema")
        con.execute("""
            CREATE TABLE IF NOT EXISTS native_admin_edit_events (
                request_id TEXT PRIMARY KEY,
                account_type TEXT NOT NULL,
                account_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                changed_at TEXT NOT NULL
            )
        """)
        prior=con.execute("""
            SELECT account_type,account_id,event_type
            FROM native_admin_edit_events WHERE request_id=?
        """,(key,)).fetchone()
        if prior:
            if (prior["account_type"],prior["account_id"],prior["event_type"])!=(
                kind,entity_id,"rename"):
                raise EditUnavailable("request id already used for another action")
            con.commit()
            return {"applied":False,"replayed":True},200
        row=con.execute("SELECT name FROM "+table+" WHERE id=?",(entity_id,)).fetchone()
        if row is None:
            con.rollback()
            return {"applied":False,"error":"not_found"},404
        if row["name"]!=expected:
            con.rollback()
            return {"applied":False,"error":"changed_since_opened"},409
        if new==expected:
            con.rollback()
            return {"applied":False,"error":"unchanged"},409
        changed=con.execute("UPDATE "+table+" SET name=? WHERE id=? AND name=?",
                            (new,entity_id,expected)).rowcount
        if changed!=1:
            raise EditUnavailable("concurrent account edit")
        con.execute("""INSERT INTO native_admin_edit_events
            (request_id,account_type,account_id,event_type,changed_at)
            VALUES (?,?,?,?,?)""",(key,kind,entity_id,"rename",
                datetime.now(timezone.utc).isoformat()))
        con.commit()
        return {"applied":True,"name":new},200
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
