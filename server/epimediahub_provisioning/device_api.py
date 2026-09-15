from __future__ import annotations

import json
from flask import jsonify, request

from app import app, db, digest, iso, utcnow


def _has_column(con, table: str, column: str) -> bool:
    return column in {row[1] for row in con.execute(f"PRAGMA table_info({table})")}


def ensure_sync_schema() -> None:
    with db() as con:
        if not _has_column(con, "customers", "config_version"):
            con.execute("ALTER TABLE customers ADD COLUMN config_version INTEGER NOT NULL DEFAULT 1")
        for name, sql_type in (
            ("last_seen_at", "TEXT"),
            ("last_sync_at", "TEXT"),
            ("last_sync_status", "TEXT"),
            ("last_sync_error", "TEXT"),
            ("applied_config_version", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if not _has_column(con, "devices", name):
                con.execute(f"ALTER TABLE devices ADD COLUMN {name} {sql_type}")
        con.execute(
            """
            CREATE TRIGGER IF NOT EXISTS customer_config_version_bump
            AFTER UPDATE OF config_json ON customers
            WHEN OLD.config_json IS NOT NEW.config_json
            BEGIN
              UPDATE customers
              SET config_version = config_version + 1
              WHERE id = NEW.id;
            END
            """
        )


def _authorized_device(con):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    row = con.execute(
        """
        SELECT d.*, c.config_json, c.config_version, c.enabled customer_enabled
        FROM devices d
        JOIN customers c ON c.id = d.customer_id
        WHERE d.session_token_hash = ?
        LIMIT 1
        """,
        (digest(token),),
    ).fetchone()
    if row is None or not row["enabled"] or not row["customer_enabled"]:
        return None
    con.execute("UPDATE devices SET last_seen_at=? WHERE id=?", (iso(utcnow()), row["id"]))
    return row


@app.get("/v1/device/config")
def device_config():
    with db() as con:
        row = _authorized_device(con)
        if row is None:
            return jsonify(error="device_not_authorized"), 401
        try:
            config = json.loads(row["config_json"] or "{}")
        except json.JSONDecodeError:
            config = {}
        version = int(row["config_version"] or 1)
        applied = int(row["applied_config_version"] or 0)
        return jsonify(config_version=version, changed=applied != version, config=config)


@app.post("/v1/device/sync-result")
def device_sync_result():
    body = request.get_json(silent=True) or {}
    try:
        reported_version = int(body.get("config_version", 0))
    except (TypeError, ValueError):
        return jsonify(error="invalid_config_version"), 400
    status = str(body.get("status", "")).strip().lower()[:32] or "unknown"
    error = str(body.get("error", "")).strip()[:500]

    with db() as con:
        row = _authorized_device(con)
        if row is None:
            return jsonify(error="device_not_authorized"), 401
        applied = int(row["applied_config_version"] or 0)
        if status == "ok" and reported_version > 0:
            applied = reported_version
        con.execute(
            "UPDATE devices SET last_sync_at=?,last_sync_status=?,last_sync_error=?,applied_config_version=? WHERE id=?",
            (iso(utcnow()), status, error, applied, row["id"]),
        )
    return jsonify(status="recorded", applied_config_version=applied)


ensure_sync_schema()
