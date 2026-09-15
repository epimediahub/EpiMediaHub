from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

bp = Blueprint("receiver_sync", __name__)


def _iso_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def migrate(con):
    """Idempotent schema migration for remote receiver configuration sync."""
    customer_cols = {r[1] for r in con.execute("PRAGMA table_info(customers)")}
    device_cols = {r[1] for r in con.execute("PRAGMA table_info(devices)")}
    if "config_version" not in customer_cols:
        con.execute("ALTER TABLE customers ADD COLUMN config_version INTEGER NOT NULL DEFAULT 1")
    for name, ddl in (
        ("last_seen_at", "TEXT"),
        ("applied_config_version", "INTEGER NOT NULL DEFAULT 0"),
        ("last_sync_at", "TEXT"),
        ("last_sync_status", "TEXT"),
        ("last_sync_error", "TEXT"),
        ("sync_bootstrap_hash", "TEXT"),
    ):
        if name not in device_cols:
            con.execute("ALTER TABLE devices ADD COLUMN %s %s" % (name, ddl))
    con.execute("""
        CREATE TABLE IF NOT EXISTS customer_config_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            config_version INTEGER NOT NULL,
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(customer_id, config_version)
        )
    """)


def save_customer_config(con, customer_id, config):
    """Store a new config version and retain the previous version for rollback."""
    row = con.execute("SELECT config_json,config_version FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not row:
        return None
    old_json = row["config_json"] or "{}"
    old_version = int(row["config_version"] or 1)
    con.execute(
        "INSERT OR IGNORE INTO customer_config_history(customer_id,config_version,config_json,created_at) VALUES(?,?,?,?)",
        (customer_id, old_version, old_json, _iso_now()),
    )
    new_version = old_version + 1
    con.execute(
        "UPDATE customers SET config_json=?,config_version=? WHERE id=?",
        (json.dumps(config, separators=(",", ":")), new_version, customer_id),
    )
    con.execute(
        "UPDATE devices SET last_sync_status='pending',last_sync_error=NULL WHERE customer_id=? AND enabled=1",
        (customer_id,),
    )
    return new_version


def rollback_customer_config(con, customer_id):
    current = con.execute("SELECT config_version FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not current:
        return None
    previous = con.execute(
        "SELECT config_json FROM customer_config_history WHERE customer_id=? AND config_version<? ORDER BY config_version DESC LIMIT 1",
        (customer_id, int(current["config_version"])),
    ).fetchone()
    if not previous:
        return None
    return save_customer_config(con, customer_id, json.loads(previous["config_json"] or "{}"))


def create_sync_bootstrap(con, device_row_id):
    """Create a one-time token that upgrades an existing receiver to normal session-token auth."""
    token = secrets.token_urlsafe(32)
    cur = con.execute(
        "UPDATE devices SET sync_bootstrap_hash=? WHERE id=? AND enabled=1",
        (_digest(token), device_row_id),
    )
    return token if cur.rowcount else None


def _bearer():
    value = request.headers.get("Authorization", "")
    return value[7:].strip() if value.startswith("Bearer ") else ""


def register(app, db):
    """Register authenticated device sync endpoints on the provisioning app."""
    def authenticate_device(con):
        token = _bearer()
        if not token:
            return None
        return con.execute(
            "SELECT d.*,c.config_json,c.config_version,c.enabled customer_enabled FROM devices d JOIN customers c ON c.id=d.customer_id WHERE d.session_token_hash=?",
            (_digest(token),),
        ).fetchone()

    @bp.post("/v1/device/bootstrap")
    def bootstrap_device():
        body = request.get_json(silent=True) or {}
        device_id = str(body.get("device_id", "")).strip()
        bootstrap_token = str(body.get("bootstrap_token", "")).strip()
        platform = str(body.get("platform", "enigma2")).strip() or "enigma2"
        if not device_id or not bootstrap_token:
            return jsonify(error="invalid_request"), 400
        with db() as con:
            migrate(con)
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT d.*,c.config_json,c.config_version,c.enabled customer_enabled FROM devices d JOIN customers c ON c.id=d.customer_id WHERE d.device_id=? AND d.sync_bootstrap_hash=?",
                (device_id, _digest(bootstrap_token)),
            ).fetchone()
            if not row or not row["enabled"] or not row["customer_enabled"]:
                return jsonify(error="invalid_bootstrap"), 401
            session_token = secrets.token_urlsafe(48)
            now = _iso_now()
            con.execute(
                "UPDATE devices SET platform=?,session_token_hash=?,sync_bootstrap_hash=NULL,last_seen_at=?,last_sync_status='pending',last_sync_error=NULL WHERE id=?",
                (platform, _digest(session_token), now, row["id"]),
            )
            return jsonify(
                session_token=session_token,
                customer_id=row["customer_id"],
                config_version=int(row["config_version"]),
                config=json.loads(row["config_json"] or "{}"),
            )

    @bp.get("/v1/device/config")
    def device_config():
        with db() as con:
            migrate(con)
            row = authenticate_device(con)
            if not row or not row["enabled"] or not row["customer_enabled"]:
                return jsonify(error="unauthorized_device"), 401
            now = _iso_now()
            con.execute("UPDATE devices SET last_seen_at=? WHERE id=?", (now, row["id"]))
            return jsonify(
                customer_id=row["customer_id"],
                config_version=int(row["config_version"]),
                applied_config_version=int(row["applied_config_version"] or 0),
                changed=int(row["applied_config_version"] or 0) < int(row["config_version"]),
                config=json.loads(row["config_json"] or "{}"),
            )

    @bp.post("/v1/device/sync-result")
    def sync_result():
        body = request.get_json(silent=True) or {}
        try:
            version = int(body.get("config_version"))
        except (TypeError, ValueError):
            return jsonify(error="invalid_config_version"), 400
        status = str(body.get("status", "")).strip().lower()
        if status not in ("ok", "error"):
            return jsonify(error="invalid_status"), 400
        error = str(body.get("error", ""))[:1000] if status == "error" else ""
        with db() as con:
            migrate(con)
            row = authenticate_device(con)
            if not row or not row["enabled"] or not row["customer_enabled"]:
                return jsonify(error="unauthorized_device"), 401
            now = _iso_now()
            applied = version if status == "ok" else int(row["applied_config_version"] or 0)
            con.execute(
                "UPDATE devices SET last_seen_at=?,last_sync_at=?,last_sync_status=?,last_sync_error=?,applied_config_version=? WHERE id=?",
                (now, now, status, error, applied, row["id"]),
            )
        return jsonify(status="recorded", applied_config_version=applied)

    app.register_blueprint(bp)
