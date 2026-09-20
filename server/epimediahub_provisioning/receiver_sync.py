from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

bp = Blueprint("receiver_sync", __name__)


def _iso_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def _public_config(raw: str):
    try:
        config = json.loads(raw or "{}")
    except json.JSONDecodeError:
        config = {}
    if not isinstance(config, dict):
        config = {}
    return {k: v for k, v in config.items() if not str(k).startswith("_")}


def migrate(con):
    """Idempotent schema migration for Android/receiver configuration sync."""
    customer_cols = {r[1] for r in con.execute("PRAGMA table_info(customers)")}
    device_cols = {r[1] for r in con.execute("PRAGMA table_info(devices)")}
    if "config_version" not in customer_cols:
        con.execute("ALTER TABLE customers ADD COLUMN config_version INTEGER NOT NULL DEFAULT 1")
    for name, ddl in (
        ("config_version", "INTEGER NOT NULL DEFAULT 1"),
        ("last_seen_at", "TEXT"),
        ("applied_config_version", "INTEGER NOT NULL DEFAULT 0"),
        ("last_sync_at", "TEXT"),
        ("last_sync_status", "TEXT"),
        ("last_sync_error", "TEXT"),
        ("sync_bootstrap_hash", "TEXT"),
        ("display_name", "TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in device_cols:
            con.execute(f"ALTER TABLE devices ADD COLUMN {name} {ddl}")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS device_playlists(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            config_json TEXT NOT NULL DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 1,
            legacy_customer_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(device_id, legacy_customer_id)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS device_playlist_migrations(
            device_id INTEGER PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
            migrated_at TEXT NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_config_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            config_version INTEGER NOT NULL,
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(customer_id, config_version)
        )
        """
    )
    rows = con.execute(
        """
        SELECT d.id device_row_id,d.customer_id,c.name,c.config_json
        FROM devices d JOIN customers c ON c.id=d.customer_id
        WHERE NOT EXISTS(
            SELECT 1 FROM device_playlist_migrations m WHERE m.device_id=d.id
        )
        """
    ).fetchall()
    for row in rows:
        config = _public_config(row["config_json"])
        if config.get("_system_role") == "unassigned":
            con.execute(
                "INSERT OR IGNORE INTO device_playlist_migrations(device_id,migrated_at) VALUES(?,?)",
                (row["device_row_id"], _iso_now()),
            )
            continue
        if not (config.get("playlist_url") or config.get("xtream_server")):
            con.execute(
                "INSERT OR IGNORE INTO device_playlist_migrations(device_id,migrated_at) VALUES(?,?)",
                (row["device_row_id"], _iso_now()),
            )
            continue
        now = _iso_now()
        con.execute(
            """
            INSERT OR IGNORE INTO device_playlists(
                device_id,name,config_json,legacy_customer_id,created_at,updated_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                row["device_row_id"],
                str(config.get("playlist_name") or row["name"] or "Playlist").strip(),
                json.dumps(config, separators=(",", ":")),
                row["customer_id"],
                now,
                now,
            ),
        )
        con.execute(
            "INSERT OR IGNORE INTO device_playlist_migrations(device_id,migrated_at) VALUES(?,?)",
            (row["device_row_id"], now),
        )


def ensure_device_playlist_from_customer(con, device_row_id: int, customer_id: int):
    """Seed a newly registered device with the customer's legacy playlist."""
    if con.execute(
        "SELECT device_id FROM device_playlist_migrations WHERE device_id=?", (device_row_id,)
    ).fetchone():
        return
    row = con.execute(
        "SELECT name,config_json FROM customers WHERE id=?", (customer_id,)
    ).fetchone()
    if not row:
        return
    config = _public_config(row["config_json"])
    if config.get("_system_role") == "unassigned" or not (
        config.get("playlist_url") or config.get("xtream_server")
    ):
        con.execute(
            "INSERT OR IGNORE INTO device_playlist_migrations(device_id,migrated_at) VALUES(?,?)",
            (device_row_id, _iso_now()),
        )
        return
    now = _iso_now()
    con.execute(
        """
        INSERT OR IGNORE INTO device_playlists(
            device_id,name,config_json,legacy_customer_id,created_at,updated_at
        ) VALUES(?,?,?,?,?,?)
        """,
        (
            device_row_id,
            str(config.get("playlist_name") or row["name"] or "Playlist").strip(),
            json.dumps(config, separators=(",", ":")),
            customer_id,
            now,
            now,
        ),
    )
    con.execute(
        "INSERT OR IGNORE INTO device_playlist_migrations(device_id,migrated_at) VALUES(?,?)",
        (device_row_id, now),
    )


def build_device_config(con, device_row_id: int):
    """Build multi-playlist sync data while keeping old Android builds compatible."""
    rows = con.execute(
        "SELECT * FROM device_playlists WHERE device_id=? AND enabled=1 ORDER BY id",
        (device_row_id,),
    ).fetchall()
    playlists = []
    for row in rows:
        config = _public_config(row["config_json"])
        config["id"] = f"managed-dashboard-{row['id']}"
        config["playlist_name"] = row["name"]
        playlists.append(config)
    payload = dict(playlists[0]) if playlists else {}
    payload["playlists"] = playlists
    payload["active_playlist_id"] = playlists[0]["id"] if playlists else ""
    return payload


def bump_device_config(con, device_row_id: int):
    con.execute(
        """
        UPDATE devices
        SET config_version=config_version+1,applied_config_version=0,
            last_sync_status='pending',last_sync_error=NULL
        WHERE id=?
        """,
        (device_row_id,),
    )


def save_customer_config(con, customer_id: int, config: dict):
    """Store a new config version and retain the previous config for rollback."""
    row = con.execute(
        "SELECT config_json,config_version FROM customers WHERE id=?", (customer_id,)
    ).fetchone()
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


def rollback_customer_config(con, customer_id: int):
    current = con.execute(
        "SELECT config_version FROM customers WHERE id=?", (customer_id,)
    ).fetchone()
    if not current:
        return None
    previous = con.execute(
        "SELECT config_json FROM customer_config_history WHERE customer_id=? AND config_version<? ORDER BY config_version DESC LIMIT 1",
        (customer_id, int(current["config_version"])),
    ).fetchone()
    if not previous:
        return None
    try:
        config = json.loads(previous["config_json"] or "{}")
    except json.JSONDecodeError:
        config = {}
    return save_customer_config(con, customer_id, config if isinstance(config, dict) else {})


def create_sync_bootstrap(con, device_row_id: int):
    """Create a one-time token that upgrades a legacy receiver to session-token auth."""
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
    """Register the single authenticated /v1/device/* API used by Android v0.5.1."""

    def authenticate_device(con):
        token = _bearer()
        if not token:
            return None
        return con.execute(
            "SELECT d.*,c.enabled customer_enabled FROM devices d JOIN customers c ON c.id=d.customer_id WHERE d.session_token_hash=? LIMIT 1",
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
                "SELECT d.*,c.enabled customer_enabled FROM devices d JOIN customers c ON c.id=d.customer_id WHERE d.device_id=? AND d.sync_bootstrap_hash=?",
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
                config_version=int(row["config_version"] or 1),
                config=build_device_config(con, int(row["id"])),
            )

    @bp.get("/v1/device/config")
    def device_config():
        with db() as con:
            migrate(con)
            row = authenticate_device(con)
            if not row or not row["enabled"] or not row["customer_enabled"]:
                return jsonify(error="device_not_authorized"), 401
            current = int(row["config_version"] or 1)
            try:
                known = int(request.args.get("version", "0"))
            except (TypeError, ValueError):
                known = 0
            changed = known != current
            now = _iso_now()
            if known == current and current > 0:
                con.execute(
                    "UPDATE devices SET last_seen_at=?,applied_config_version=?,last_sync_status=CASE WHEN last_sync_status='error' THEN last_sync_status ELSE 'ok' END WHERE id=?",
                    (now, current, row["id"]),
                )
            else:
                con.execute("UPDATE devices SET last_seen_at=? WHERE id=?", (now, row["id"]))
            return jsonify(
                customer_id=row["customer_id"],
                config_version=current,
                applied_config_version=int(row["applied_config_version"] or 0),
                changed=changed,
                config=build_device_config(con, int(row["id"])),
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
                return jsonify(error="device_not_authorized"), 401
            now = _iso_now()
            current = int(row["config_version"] or 1)
            applied = int(row["applied_config_version"] or 0)
            if status == "ok" and version == current:
                applied = version
            elif status == "ok" and version != current:
                status = "stale"
                error = f"reported config v{version}, current is v{current}"
            con.execute(
                "UPDATE devices SET last_seen_at=?,last_sync_at=?,last_sync_status=?,last_sync_error=?,applied_config_version=? WHERE id=?",
                (now, now, status, error, applied, row["id"]),
            )
        return jsonify(status="recorded", applied_config_version=applied)

    app.register_blueprint(bp)
