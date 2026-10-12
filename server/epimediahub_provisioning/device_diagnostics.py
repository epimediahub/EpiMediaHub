"""Optional, authenticated device error counters with bounded retention and no raw logs.

Client MUST explicitly opt-in for every report. Raw stack traces, URLs,
stream credentials, location/IP, filenames and free-text messages are rejected.
The admin view shows aggregate categories only, not which household failed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from flask import jsonify, request
from app import app, db, digest, iso, utcnow

COMPONENTS = frozenset({"STARTUP", "PLAYER", "EPG", "VPN", "UPDATER", "NAVIGATION", "OTHER"})
CODES = frozenset({"CRASH", "NETWORK_TIMEOUT", "PLAYBACK_FAILED", "DECODER", "NO_AUDIO",
                    "HTTP_ERROR", "SYNC_FAILED", "PERMISSION", "UNKNOWN"})
ALLOWED = frozenset({"consent", "component", "code", "app_version"})
MAX_REPORTS_PER_DAY = 25
KEEP_DAYS = 30


def migrate():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS device_error_events(
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 device_row_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                 component TEXT NOT NULL,
                 code TEXT NOT NULL,
                 app_version TEXT NOT NULL,
                 reported_at TEXT NOT NULL)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_device_error_time ON device_error_events(reported_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_device_error_device_time ON device_error_events(device_row_id,reported_at)")


def aggregate(con):
    since = iso(utcnow() - timedelta(days=7))
    return [dict(r) for r in con.execute("""SELECT component,code,COUNT(*) reports
           FROM device_error_events WHERE reported_at >= ?
           GROUP BY component,code ORDER BY reports DESC,component,code LIMIT 25""", (since,))]


@app.post("/v1/device/error-report")
def device_error_report():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != ALLOWED or body.get("consent") is not True:
        return jsonify(error="explicit_consent_and_allowed_fields_required"), 400
    component, code, version = (body.get(k) for k in ("component", "code", "app_version"))
    if not isinstance(component, str) or component not in COMPONENTS or not isinstance(code, str) or code not in CODES:
        return jsonify(error="unknown_error_category"), 400
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", version):
        return jsonify(error="invalid_app_version"), 400
    bearer = request.headers.get("Authorization", "")
    if not bearer.startswith("Bearer ") or len(bearer) < 32 or len(bearer) > 256:
        return jsonify(error="authentication_required"), 401
    token = bearer[7:].strip()
    if not token:
        return jsonify(error="authentication_required"), 401
    now = utcnow()
    with db() as con:
        row = con.execute("""SELECT d.id FROM devices d JOIN customers c ON c.id=d.customer_id
              WHERE d.session_token_hash=? AND d.enabled=1 AND c.enabled=1 LIMIT 1""",
              (digest(token),)).fetchone()
        if row is None:
            return jsonify(error="not_authorized"), 401
        con.execute("BEGIN IMMEDIATE")
        con.execute("DELETE FROM device_error_events WHERE reported_at < ?", (iso(now - timedelta(days=KEEP_DAYS)),))
        today = con.execute("""SELECT COUNT(*) FROM device_error_events
            WHERE device_row_id=? AND reported_at>=?""",
            (row["id"], iso(now - timedelta(hours=24)))).fetchone()[0]
        if today >= MAX_REPORTS_PER_DAY:
            return jsonify(error="rate_limited"), 429
        con.execute("""INSERT INTO device_error_events(device_row_id,component,code,app_version,reported_at)
             VALUES(?,?,?,?,?)""", (row["id"], component, code, version, iso(now)))
    response = jsonify(accepted=True)
    response.headers["Cache-Control"] = "no-store"
    return response, 201


migrate()
