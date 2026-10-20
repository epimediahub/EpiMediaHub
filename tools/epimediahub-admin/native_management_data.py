"""Read-only, privacy-minimized native Admin management API data.

The contract is validated against the production schema inventory supplied on
2026-10-20. Only authenticated *administrator* endpoints should call these
helpers. They cannot change customer, reseller, license, playlist or VPN state.

No config_json, IPTV URLs, VPN keys, credentials, device identifiers or tokens
are selected. Counts for licensing/VPN intentionally stay null until their
business-specific 'active' semantics have been verified.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3

PAGE_SIZE=100
REQUIRED={
    "customers":{"id","name","enabled","reseller_id"},
    "devices":{"id","customer_id","enabled","display_name","platform"},
    "customer_playlists":{"id","customer_id","name","enabled"},
    "resellers":{"id","name","enabled","customer_limit","device_limit","branding_name"},
}

class SchemaUnavailable(RuntimeError):
    pass

def _validate(con):
    for name,required in REQUIRED.items():
        columns={row[1] for row in con.execute('PRAGMA table_info("'+name+'")')}
        if not required<=columns:
            raise SchemaUnavailable("missing required native management schema")

def _safe_name(value, max_len=150):
    return str(value or "").strip()[:max_len]

def _database(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise SchemaUnavailable("database unavailable")
    con=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",
                        uri=True,timeout=5)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con

def _run(path,fn):
    con=_database(path)
    try:
        con.execute("BEGIN")
        _validate(con)
        value=fn(con)
        con.rollback()
        return value
    finally:
        con.close()

def overview(path):
    def load(con):
        return {
            "customers":int(con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]),
            "resellers":int(con.execute("SELECT COUNT(*) FROM resellers").fetchone()[0]),
            "active_licenses":None,
            "active_vpns":None,
            "metric_scope":"total_customers_and_resellers; entitlements_unverified"
        }
    return _run(path,load)

def _search(term):
    if not isinstance(term,str) or len(term)>80:
        raise ValueError("search query invalid")
    return "%"+term.replace("~","~~").replace("%","~%").replace("_","~_")+"%"


def customers(path,query=""):
    pattern=_search(query)
    def load(con):
        rows=con.execute("""
            SELECT c.id,c.name,c.enabled,
                COALESCE(p.n,0) playlist_count,
                COALESCE(d.n,0) device_count
            FROM customers c
            LEFT JOIN (
                SELECT customer_id,COUNT(*) n
                FROM customer_playlists GROUP BY customer_id
            ) p ON p.customer_id=c.id
            LEFT JOIN (
                SELECT customer_id,COUNT(*) n
                FROM devices GROUP BY customer_id
            ) d ON d.customer_id=c.id
            WHERE c.name LIKE ? ESCAPE '~'
            ORDER BY c.id DESC LIMIT ?
        """,(pattern,PAGE_SIZE+1)).fetchall()
        return {
            "customers":[{
                "id":str(row["id"]),
                "name":_safe_name(row["name"]),
                "subtitle":("Aktiv" if row["enabled"] else "Deaktiviert")+
                    " · "+str(row["device_count"])+" Geräte",
                "playlist_count":int(row["playlist_count"]),
                "expires_at_epoch":None
            } for row in rows[:PAGE_SIZE]],
            "has_more":len(rows)>PAGE_SIZE,
            "scope":"customer_names_and_aggregate_counts_only"
        }
    return _run(path,load)

def resellers(path,query=""):
    pattern=_search(query)
    def load(con):
        rows=con.execute("""
            SELECT r.id,r.name,r.enabled,
                COALESCE(c.n,0) customers_count
            FROM resellers r
            LEFT JOIN (
                SELECT reseller_id,COUNT(*) n
                FROM customers WHERE reseller_id IS NOT NULL GROUP BY reseller_id
            ) c ON c.reseller_id=r.id
            WHERE r.name LIKE ? ESCAPE '~'
            ORDER BY r.id DESC LIMIT ?
        """,(pattern,PAGE_SIZE+1)).fetchall()
        return {
            "resellers":[{
                "id":str(row["id"]),
                "name":_safe_name(row["name"]),
                "subtitle":("Aktiv" if row["enabled"] else "Deaktiviert")+
                    " · "+str(row["customers_count"])+" Kunden",
                "playlist_count":None,
                "expires_at_epoch":None
            } for row in rows[:PAGE_SIZE]],
            "has_more":len(rows)>PAGE_SIZE,
            "scope":"reseller_names_and_aggregate_counts_only"
        }
    return _run(path,load)

def customer_detail(path, customer_id):
    if not isinstance(customer_id,int) or not 0<customer_id<2**63:
        raise ValueError("invalid customer id")
    def load(con):
        row=con.execute("""
            SELECT id,name,enabled,reseller_id FROM customers WHERE id=?
        """,(customer_id,)).fetchone()
        if row is None:
            return None
        playlists=con.execute("""
            SELECT id,name,enabled FROM customer_playlists
            WHERE customer_id=? ORDER BY id DESC LIMIT ?
        """,(customer_id,PAGE_SIZE+1)).fetchall()
        devices=con.execute("""
            SELECT id,display_name,platform,enabled FROM devices
            WHERE customer_id=? ORDER BY id DESC LIMIT ?
        """,(customer_id,PAGE_SIZE+1)).fetchall()
        return {
            "id":str(row["id"]),
            "name":_safe_name(row["name"]),
            "enabled":bool(row["enabled"]),
            "reseller_id":str(row["reseller_id"]) if row["reseller_id"] is not None else None,
            "playlists":[{
                "id":str(p["id"]),"name":_safe_name(p["name"]),"enabled":bool(p["enabled"])
            } for p in playlists[:PAGE_SIZE]],
            "devices":[{
                "id":str(d["id"]),
                "name":_safe_name(d["display_name"] or d["platform"] or "Gerät"),
                "platform":_safe_name(d["platform"],40),
                "enabled":bool(d["enabled"])
            } for d in devices[:PAGE_SIZE]],
            "more_playlists":len(playlists)>PAGE_SIZE,
            "more_devices":len(devices)>PAGE_SIZE
        }
    return _run(path,load)

def reseller_detail(path,reseller_id):
    if not isinstance(reseller_id,int) or not 0<reseller_id<2**63:
        raise ValueError("invalid reseller id")
    def load(con):
        row=con.execute("""
            SELECT id,name,enabled,branding_name,customer_limit,device_limit
            FROM resellers WHERE id=?
        """,(reseller_id,)).fetchone()
        if row is None:
            return None
        customers=con.execute("""
            SELECT id,name,enabled FROM customers
            WHERE reseller_id=? ORDER BY id DESC LIMIT ?
        """,(reseller_id,PAGE_SIZE+1)).fetchall()
        return {
            "id":str(row["id"]),
            "name":_safe_name(row["name"]),
            "enabled":bool(row["enabled"]),
            "branding_name":_safe_name(row["branding_name"]),
            "customer_limit":row["customer_limit"],
            "device_limit":row["device_limit"],
            "customers":[{
                "id":str(c["id"]),"name":_safe_name(c["name"]),
                "enabled":bool(c["enabled"])
            } for c in customers[:PAGE_SIZE]],
            "more_customers":len(customers)>PAGE_SIZE
        }
    return _run(path,load)

def device_diagnostics(path, device_row_id):
    """Safe one-device summary; never return stream, identity or log message."""
    if not isinstance(device_row_id,int) or not 0<device_row_id<2**63:
        raise ValueError("invalid device id")
    def load(con):
        device_columns={row[1] for row in con.execute("PRAGMA table_info(devices)")}
        required={"id","customer_id","display_name","platform","enabled",
            "last_seen_at","last_sync_at","last_sync_status","config_version",
            "applied_config_version"}
        if not required<=device_columns:
            raise SchemaUnavailable("device status columns unavailable")
        row=con.execute("""
            SELECT id,display_name,platform,enabled,last_seen_at,last_sync_at,
                   last_sync_status,config_version,applied_config_version
            FROM devices WHERE id=?
        """,(device_row_id,)).fetchone()
        if row is None:
            return None
        # Do not return last_sync_error or device_id; they may contain
        # provider details or unique device identifiers.
        allowed_status={"ok","success","failed","error","pending",
                        "skipped","not_started","synced","offline"}
        raw=(row["last_sync_status"] or "").strip().lower()
        status=raw if raw in allowed_status else "unknown"
        error_columns={col[1] for col in con.execute(
            "PRAGMA table_info(device_error_events)")}
        recent=[]
        if {"id","device_row_id","component","code","app_version",
                "reported_at"}<=error_columns:
            errors=con.execute("""
                SELECT component,code,app_version,reported_at
                FROM device_error_events WHERE device_row_id=?
                ORDER BY reported_at DESC LIMIT 15
            """,(device_row_id,)).fetchall()
            import re
            allowed=re.compile(r"^[a-zA-Z0-9_.:-]{1,55}$")
            for item in errors:
                recent.append({
                    "component":str(item["component"]) if
                        item["component"] and allowed.fullmatch(str(item["component"])) else "unknown",
                    "code":str(item["code"]) if
                        item["code"] and allowed.fullmatch(str(item["code"])) else "unknown",
                    "app_version":_safe_name(item["app_version"],35),
                    "reported_at":_safe_name(item["reported_at"],45)
                })
        return {
            "id":str(row["id"]),
            "name":_safe_name(row["display_name"] or row["platform"] or "Gerät"),
            "enabled":bool(row["enabled"]),
            "platform":_safe_name(row["platform"],40),
            "last_seen_at":_safe_name(row["last_seen_at"],45),
            "last_sync_at":_safe_name(row["last_sync_at"],45),
            "last_sync_status":status,
            "config_version":row["config_version"],
            "applied_config_version":row["applied_config_version"],
            "recent_errors":recent
        }
    return _run(path,load)
