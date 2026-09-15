from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, request

BASE_DIR = Path(os.environ.get("EPIMEDIAHUB_DATA_DIR", "/var/lib/epimediahub"))
DB_PATH = BASE_DIR / "provisioning.db"
PUBLIC_BASE_URL = os.environ.get("EPIMEDIAHUB_PUBLIC_URL", "https://setup.example.invalid").rstrip("/")
ADMIN_TOKEN = os.environ.get("EPIMEDIAHUB_ADMIN_TOKEN", "")
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

app = Flask(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def db() -> sqlite3.Connection:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db() -> None:
    with db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                config_json TEXT NOT NULL DEFAULT '{}',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS activations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                code_hash TEXT NOT NULL UNIQUE,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                redeemed_at TEXT,
                device_id TEXT,
                platform TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                device_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                session_token_hash TEXT NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(customer_id, device_id)
            );
            """
        )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_code(value: str) -> str:
    return "".join(c for c in value.upper() if c.isalnum())


def display_code(raw: str) -> str:
    return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def make_code(length: int = 12) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def require_admin() -> None:
    supplied = request.headers.get("Authorization", "")
    expected = f"Bearer {ADMIN_TOKEN}"
    if not ADMIN_TOKEN or not secrets.compare_digest(supplied, expected):
        from flask import abort
        abort(401)


@app.get("/health")
def health():
    return jsonify(status="ok", service="epimediahub-provisioning")


@app.post("/v1/admin/customers")
def create_customer():
    require_admin()
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    config = body.get("config", {})
    if not name or not isinstance(config, dict):
        return jsonify(error="invalid_customer"), 400
    with db() as con:
        cur = con.execute(
            "INSERT INTO customers(name, config_json, created_at) VALUES (?, ?, ?)",
            (name, json.dumps(config, separators=(",", ":")), iso(utcnow())),
        )
        customer_id = cur.lastrowid
    return jsonify(id=customer_id, name=name), 201


@app.post("/v1/admin/customers/<int:customer_id>/activation")
def create_activation(customer_id: int):
    require_admin()
    body = request.get_json(silent=True) or {}
    ttl_minutes = max(5, min(int(body.get("ttl_minutes", 60)), 1440))
    raw_code = make_code()
    token = secrets.token_urlsafe(32)
    expires = utcnow() + timedelta(minutes=ttl_minutes)
    with db() as con:
        customer = con.execute("SELECT id FROM customers WHERE id=? AND enabled=1", (customer_id,)).fetchone()
        if customer is None:
            return jsonify(error="customer_not_found"), 404
        con.execute(
            "INSERT INTO activations(customer_id, code_hash, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (customer_id, digest(raw_code), digest(token), iso(expires), iso(utcnow())),
        )
    url = f"{PUBLIC_BASE_URL}/connect/{token}"
    return jsonify(code=display_code(raw_code), activation_url=url, qr_payload=url, expires_at=iso(expires)), 201


@app.post("/v1/setup/redeem")
def redeem():
    body = request.get_json(silent=True) or {}
    code = normalize_code(str(body.get("code", "")))
    device_id = str(body.get("device_id", "")).strip()
    platform = str(body.get("platform", "android")).strip() or "android"
    if not code or not device_id:
        return jsonify(error="invalid_request"), 400

    now = utcnow()
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            """SELECT a.*, c.config_json, c.enabled AS customer_enabled
               FROM activations a JOIN customers c ON c.id=a.customer_id
               WHERE a.code_hash=?""",
            (digest(code),),
        ).fetchone()
        if row is None or not row["customer_enabled"]:
            return jsonify(error="invalid_code"), 404
        if row["redeemed_at"] is not None:
            return jsonify(error="already_used"), 409
        expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        if expires <= now:
            return jsonify(error="expired"), 410

        session_token = secrets.token_urlsafe(48)
        con.execute(
            "UPDATE activations SET redeemed_at=?, device_id=?, platform=? WHERE id=? AND redeemed_at IS NULL",
            (iso(now), device_id, platform, row["id"]),
        )
        con.execute(
            """INSERT INTO devices(customer_id, device_id, platform, session_token_hash, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(customer_id, device_id) DO UPDATE SET
                 platform=excluded.platform, session_token_hash=excluded.session_token_hash, enabled=1""",
            (row["customer_id"], device_id, platform, digest(session_token), iso(now)),
        )
        config = json.loads(row["config_json"])
    return jsonify(session_token=session_token, customer_id=row["customer_id"], config=config)


@app.post("/v1/admin/devices/<int:device_id>/revoke")
def revoke_device(device_id: int):
    require_admin()
    with db() as con:
        cur = con.execute("UPDATE devices SET enabled=0 WHERE id=?", (device_id,))
    if cur.rowcount == 0:
        return jsonify(error="device_not_found"), 404
    return jsonify(status="revoked")


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8787")))
