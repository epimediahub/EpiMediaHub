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
