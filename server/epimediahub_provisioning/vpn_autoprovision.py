"""Device-authenticated, zero-ADB VPN provisioning for EpiMediaHub.

Private WireGuard keys NEVER reach this server. App creates keypair on Android,
backend stores the public key and allocates a unique IPv4 tunnel address.
Device session token is the existing customer pairing/session credential.
"""
from __future__ import annotations
import hashlib
import hmac
import ipaddress
import os
import re
import sqlite3
from datetime import timedelta

from flask import abort, jsonify, request
from vpn_dashboard import now, stamp, instant, public_key, desired, JOINED, fresh

def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS vpn_pending_grants (
        device_row_id INTEGER PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
        days INTEGER NOT NULL CHECK(days >= 1 AND days <= 3660),
        source TEXT NOT NULL CHECK(source IN ('admin','reseller')),
        reseller_id INTEGER REFERENCES resellers(id),
        created_at TEXT NOT NULL
    )""")
    con.execute("""CREATE INDEX IF NOT EXISTS idx_vpn_pending_source
                    ON vpn_pending_grants(source, reseller_id)""")

def ensure_pending(con, device_row_id, days, source, reseller_id=None):
    migrate(con)
    previous = con.execute("SELECT * FROM vpn_pending_grants WHERE device_row_id=?", (device_row_id,)).fetchone()
    total = min(3660, days + (int(previous["days"]) if previous else 0))
    con.execute("""INSERT INTO vpn_pending_grants(device_row_id,days,source,reseller_id,created_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(device_row_id)
                   DO UPDATE SET days=excluded.days, source=excluded.source,
                   reseller_id=excluded.reseller_id""",
                (device_row_id, total, source, reseller_id, stamp()))

def _device(con):
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        abort(401)
    token = authorization[7:]
    if len(token) < 32 or len(token) > 512 or any(ch.isspace() for ch in token):
        abort(401)
    hash_value = hashlib.sha256(token.encode()).hexdigest()
    row = con.execute("""SELECT d.*,c.enabled customer_enabled,
                                c.reseller_id current_reseller_id,
                                r.enabled reseller_enabled
                         FROM devices d JOIN customers c ON c.id=d.customer_id
                         LEFT JOIN resellers r ON r.id=c.reseller_id
                         WHERE d.session_token_hash=? LIMIT 1""", (hash_value,)).fetchone()
    if not row or not row["enabled"] or not row["customer_enabled"] or (
        row["current_reseller_id"] is not None and not row["reseller_enabled"]
    ):
        abort(401)
    return row

def _address(con):
    net = ipaddress.ip_network(os.environ.get("EPIMEDIAHUB_VPN_SUBNET", "10.92.0.0/24"), strict=True)
    if net.version != 4 or net.num_addresses > 65536:
        raise ValueError("VPN IPv4 subnet configuration unavailable")
    used = {ipaddress.ip_interface(x[0]).ip for x in
            con.execute("SELECT client_address FROM vpn_devices")}
    for host in net.hosts():
        # Reserve WireGuard server address and low reserved pool.
        if int(host) <= int(net.network_address) + 1 or host in used:
            continue
        return str(host) + "/32"
    raise RuntimeError("VPN address pool exhausted")

def _licensed(con, entry):
    if not entry:
        return False
    current = con.execute(JOINED + " WHERE v.id=?", (entry["id"],)).fetchone()
    return current is not None and desired(current)["enabled"]

def _status(con, device):
    entry = con.execute("SELECT * FROM vpn_devices WHERE device_row_id=?", (device["id"],)).fetchone()
    if not entry:
        queue = con.execute("SELECT days FROM vpn_pending_grants WHERE device_row_id=?", (device["id"],)).fetchone()
        return dict(device_id=device["device_id"], status="AWAITING_DEVICE_KEY" if queue else "NO_VPN_LICENSE",
                    enabled=False, assigned=False)
    alive = bool(entry["expires_at"] and instant(entry["expires_at"]) > now())
    active = _licensed(con, entry)
    confirmed = bool(active and fresh(con) and entry["applied_enabled"] == 1 and
                     entry["applied_generation"] ==
                        desired(con.execute(JOINED+" WHERE v.id=?", (entry["id"],)).fetchone())["generation"])
    status = "READY" if confirmed else "WAITING_FOR_SERVER" if active else (
        "EXPIRED" if entry["expires_at"] and not alive else "SUSPENDED" if alive else "NO_VPN_LICENSE")
    result = dict(device_id=device["device_id"], status=status, assigned=True,
                  enabled=confirmed, revision=entry["revision"], expires_at=entry["expires_at"])
    if confirmed:
        server_key = public_key(os.environ.get("EPIMEDIAHUB_VPN_SERVER_PUBLIC_KEY", ""))
        endpoint = os.environ.get("EPIMEDIAHUB_VPN_ENDPOINT", "37.27.42.215:51820")
        if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}:[0-9]{2,5}", endpoint):
            raise ValueError("Invalid server endpoint")
        result.update(client_address=entry["client_address"], server_public_key=server_key,
                      endpoint=endpoint, dns=["1.1.1.1"], allowed_ips=["0.0.0.0/0", "::/0"])
    return result

def install(app, db):
    if app.extensions.get("epimediahub_vpn_auto"):
        return
    with db() as con:
        migrate(con)
    app.extensions["epimediahub_vpn_auto"] = True

    @app.get("/v1/device/identity")
    def vpn_device_identity():
        with db() as con:
            d = _device(con)
            answer = jsonify(device_id=d["device_id"], device_row_id=d["id"])
        answer.headers["Cache-Control"] = "no-store"
        return answer

    @app.get("/v1/device/vpn/status")
    def vpn_device_status():
        with db() as con:
            d = _device(con)
            state = _status(con, d)
        response = jsonify(state)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/v1/device/vpn/enroll")
    def vpn_enroll():
        if request.content_length and request.content_length > 4096:
            abort(413)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="invalid_json"), 400
        try:
            key = public_key(data.get("public_key", ""))
        except (TypeError, ValueError):
            return jsonify(error="invalid_public_key"), 400
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            d = _device(con)
            if str(data.get("device_id", "")) != d["device_id"]:
                abort(403)
            # Fail closed: no self-service key rotation. Admin transfer/rekey
            # must revoke the old peer first, or two devices could share a license.
            entry = con.execute("SELECT * FROM vpn_devices WHERE device_row_id=?", (d["id"],)).fetchone()
            if entry and not hmac.compare_digest(entry["public_key"], key):
                return jsonify(error="device_key_already_bound"), 409
            if not entry:
                occupied = con.execute("SELECT 1 FROM vpn_devices WHERE public_key=?", (key,)).fetchone()
                if occupied:
                    return jsonify(error="public_key_already_assigned"), 409
                address = _address(con)
                queued = con.execute("SELECT * FROM vpn_pending_grants WHERE device_row_id=?", (d["id"],)).fetchone()
                days = int(queued["days"]) if queued else 0
                con.execute("""INSERT INTO vpn_devices
                        (device_row_id,bound_customer_id,owner_reseller_id,public_key,client_address,
                         status,expires_at,revision,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?)""",
                        (d["id"],d["customer_id"],d["current_reseller_id"],key,address,
                         "ACTIVE" if days else "SUSPENDED",
                         stamp(now()+timedelta(days=days)) if days else None,1,stamp()))
                if queued:
                    con.execute("DELETE FROM vpn_pending_grants WHERE device_row_id=?", (d["id"],))
                    con.execute("""INSERT INTO vpn_audit(actor,action,detail_json,created_at)
                                   VALUES(?,?,?,?)""",
                                ("system","auto_apply_pending",
                                 '{"device_row_id":%d}' % d["id"],stamp()))
            status = _status(con, d)
        result = jsonify(status)
        result.headers["Cache-Control"] = "no-store"
        return result
