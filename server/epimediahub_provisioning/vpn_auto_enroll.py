"""Self-service WireGuard enrolment after an explicit manual 7-day admin grant.

No private keys, profile QR codes, or unauthenticated allocations. Existing VPN
peers and manual grants remain untouched. An approved handset supplies its own
public key via the current device session; the Finland agent still has to ACK
the exact desired generation before READY can be returned.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import re
import sqlite3
from datetime import timedelta

from flask import abort, flash, jsonify, redirect, request, session

from app import app, db, digest
import vpn_dashboard as vpn

MAX_JSON_BYTES = 4096
HOST_PATTERN = re.compile(r"(?:[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?):[0-9]{2,5}")


def migrate(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS vpn_trial_authorizations(
            device_row_id INTEGER PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
            device_key_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            granted_at TEXT NOT NULL
        )
    """)


def _client():
    token = request.headers.get("Authorization", "")
    if not token.startswith("Bearer ") or len(token) > 256:
        abort(401)
    raw = token[7:]
    if len(raw) < 32 or len(raw) > 192:
        abort(401)
    with db() as con:
        row = con.execute("""
            SELECT d.id,d.device_id,d.customer_id,d.enabled,d.platform,
                   c.enabled customer_enabled,c.reseller_id,r.enabled reseller_enabled
              FROM devices d JOIN customers c ON c.id=d.customer_id
              LEFT JOIN resellers r ON r.id=c.reseller_id
             WHERE d.session_token_hash=?
        """, (digest(raw),)).fetchone()
        if row is None or not row["enabled"] or not row["customer_enabled"] or (
            row["reseller_id"] is not None and not row["reseller_enabled"]
        ):
            abort(403)
        if "android" not in row["platform"].lower() and "fire" not in row["platform"].lower():
            abort(403)
        return dict(row)


def _network():
    subnet = ipaddress.ip_network(os.environ.get("EPIMEDIAHUB_VPN_SUBNET", "10.92.0.0/24"),
                                   strict=True)
    if subnet.version != 4 or subnet.num_addresses > 4096 or subnet.prefixlen > 29:
        raise RuntimeError("VPN address pool must be IPv4 and 8..4096 addresses")
    return subnet


def _public_settings():
    """Only WireGuard's PUBLIC key/endpoint. No private key leaves the gateway."""
    key = os.environ.get("EPIMEDIAHUB_VPN_SERVER_PUBLIC_KEY", "").strip()
    endpoint = os.environ.get("EPIMEDIAHUB_VPN_ENDPOINT", "").strip()
    vpn.public_key(key)
    if not HOST_PATTERN.fullmatch(endpoint):
        raise RuntimeError("Missing or invalid public VPN gateway endpoint")
    return key, endpoint


def _address(con):
    network = _network()
    assigned = {row[0] for row in con.execute("SELECT client_address FROM vpn_devices")}
    # Never reuse any address from retired peers; agent safety comes first.
    for host in network.hosts():
        if int(host) <= int(network.network_address) + 1:
            continue  # .1 is the WireGuard gateway.
        candidate = str(host) + "/32"
        if candidate not in assigned:
            return candidate
    raise RuntimeError("VPN address pool exhausted")


def _authorization(con, device):
    device_hash = hashlib.sha256(device["device_id"].encode("utf-8")).hexdigest()
    row = con.execute("""
        SELECT a.expires_at
          FROM vpn_trial_authorizations a
         WHERE a.device_row_id=? AND a.device_key_hash=?
           AND EXISTS (SELECT 1 FROM vpn_trials t
                        WHERE t.device_key_hash=a.device_key_hash AND t.expires_at=a.expires_at)
    """, (device["id"], device_hash)).fetchone()
    return row["expires_at"] if row else None


def _entry(con, device):
    return con.execute("""
        SELECT v.* FROM vpn_devices v
        WHERE v.device_row_id=? AND v.bound_customer_id=? AND
              v.owner_reseller_id IS ?
    """, (device["id"], device["customer_id"], device["reseller_id"])).fetchone()


def _state(con, device):
    from_vpn = _entry(con, device)
    expiry = _authorization(con, device)
    if from_vpn is None:
        if expiry is None:
            return dict(status="NO_VPN_LICENSE", enabled=False)
        if vpn.instant(expiry) <= vpn.now():
            return dict(status="EXPIRED", enabled=False, expires_at=expiry)
        return dict(status="PENDING_ENROLL", enabled=False, expires_at=expiry)

    expiry = from_vpn["expires_at"]
    if not expiry or vpn.instant(expiry) <= vpn.now():
        return dict(status="EXPIRED", enabled=False, expires_at=expiry)
    if from_vpn["status"] != "ACTIVE":
        return dict(status="SUSPENDED", enabled=False, expires_at=expiry)
    joined = con.execute(vpn.JOINED + " WHERE v.id=?", (from_vpn["id"],)).fetchone()
    if not joined or not vpn.desired(joined)["enabled"]:
        return dict(status="SUSPENDED", enabled=False, expires_at=expiry)
    wanted = vpn.desired(joined)
    ready = bool(vpn.fresh(con) and from_vpn["applied_at"]
                 and from_vpn["applied_generation"] == wanted["generation"]
                 and from_vpn["applied_enabled"] == 1
                 and vpn.now() - vpn.instant(from_vpn["applied_at"]) < timedelta(seconds=vpn.LEASE_SECONDS))
    result = dict(status="READY" if ready else "PENDING_AGENT",
                  enabled=ready, expires_at=expiry)
    if ready:
        try:
            key, endpoint = _public_settings()
        except (ValueError, RuntimeError):
            return dict(status="PENDING_AGENT", enabled=False, expires_at=expiry)
        result.update(client_address=from_vpn["client_address"], server_public_key=key,
                      endpoint=endpoint, dns=["1.1.1.1"])
    return result


def _response(con, device):
    body = dict(device_id=device["device_id"], **_state(con, device))
    response = jsonify(body)
    response.headers["Cache-Control"] = "no-store, private"
    return response


@app.post("/admin/vpn/trial7-auto/<int:device_row_id>")
def grant_trial_auto(device_row_id):
    if not session.get("admin"):
        abort(403)
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        migrate(con)
        row = con.execute("""
            SELECT d.id,d.device_id,d.customer_id,d.platform,d.enabled,
                   c.enabled customer_enabled,c.reseller_id,r.enabled reseller_enabled
              FROM devices d JOIN customers c ON c.id=d.customer_id
              LEFT JOIN resellers r ON r.id=c.reseller_id
             WHERE d.id=?
        """, (device_row_id,)).fetchone()
        if not row:
            abort(404)
        device = dict(row)
        if not device["enabled"] or not device["customer_enabled"] or (
            device["reseller_id"] is not None and not device["reseller_enabled"]
        ):
            abort(409)
        if "android" not in device["platform"].lower() and "fire" not in device["platform"].lower():
            abort(409)
        if con.execute("SELECT 1 FROM vpn_devices WHERE device_row_id=?", (device_row_id,)).fetchone():
            abort(409, "VPN device is already enrolled")
        if con.execute("SELECT COUNT(*) FROM devices WHERE device_id=?",
                       (device["device_id"],)).fetchone()[0] != 1:
            abort(409, "Duplicate device ID")
        key_hash = hashlib.sha256(device["device_id"].encode("utf-8")).hexdigest()
        if con.execute("SELECT 1 FROM vpn_trials WHERE device_key_hash=?", (key_hash,)).fetchone():
            flash("Die einmalige 7-Tage-VPN-Testphase wurde bereits vergeben.", "warning")
            return redirect("/admin#device-" + str(device_row_id), code=303)
        if not vpn.fresh(con):
            flash("Finnland-Agent nicht bestätigt. Keine Testphase verbraucht.", "warning")
            return redirect("/admin#device-" + str(device_row_id), code=303)
        now = vpn.now()
        expires = vpn.stamp(now + timedelta(days=7))
        con.execute("INSERT INTO vpn_trials(device_key_hash,granted_at,expires_at) VALUES(?,?,?)",
                    (key_hash, vpn.stamp(now), expires))
        con.execute("""INSERT INTO vpn_trial_authorizations(
                        device_row_id,device_key_hash,expires_at,granted_at)
                       VALUES(?,?,?,?)""",
                    (device_row_id, key_hash, expires, vpn.stamp(now)))
        con.execute("INSERT INTO vpn_audit(actor,action,detail_json,created_at) VALUES(?,?,?,?)",
                    ("admin", "trial7_auto", '{"device_row_id":%d}' % device_row_id,
                     vpn.stamp(now)))
    flash("7-Tage-VPN-Test freigegeben. Das Gerät meldet sich in der App automatisch an.", "success")
    return redirect("/admin#device-" + str(device_row_id), code=303)


@app.context_processor
def vpn_auto_quick_actions():
    """Only admin: whether an unbound device already consumed its one trial."""
    if request.endpoint != "dashboard" or not session.get("admin"):
        return {}
    with db() as con:
        used = {row["device_key_hash"] for row in
                con.execute("SELECT device_key_hash FROM vpn_trials")}
        rows = con.execute("SELECT id,device_id FROM devices").fetchall()
    return {"vpn_auto_states": {
        row["id"]: {"trial_used": hashlib.sha256(row["device_id"].encode("utf-8")).hexdigest() in used}
        for row in rows
    }}


@app.get("/v1/device/vpn/status")
def device_vpn_status():
    device = _client()
    with db() as con:
        return _response(con, device)


@app.post("/v1/device/vpn/enroll")
def device_vpn_enroll():
    device = _client()
    if request.content_length is not None and request.content_length > MAX_JSON_BYTES:
        abort(413)
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"device_id", "public_key"}:
        abort(400)
    if body["device_id"] != device["device_id"]:
        abort(403)
    try:
        key = vpn.public_key(body["public_key"])
    except (ValueError, TypeError):
        abort(400)
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        migrate(con)
        if con.execute("SELECT COUNT(*) FROM devices WHERE device_id=?",
                       (device["device_id"],)).fetchone()[0] != 1:
            abort(409)
        entry = _entry(con, device)
        if entry:
            if not hmac.compare_digest(entry["public_key"], key):
                abort(409)
            return _response(con, device)
        expiry = _authorization(con, device)
        if expiry is None:
            abort(403)
        if vpn.instant(expiry) <= vpn.now():
            abort(410)
        if not vpn.fresh(con):
            return jsonify(device_id=device["device_id"],
                           status="PENDING_AGENT", enabled=False,
                           expires_at=expiry), 200
        try:
            address = _address(con)
        except RuntimeError:
            abort(503)
        try:
            con.execute("""INSERT INTO vpn_devices(
                        device_row_id,bound_customer_id,owner_reseller_id,public_key,
                        client_address,status,expires_at,created_at)
                        VALUES(?,?,?,?,?,'ACTIVE',?,?)""",
                        (device["id"], device["customer_id"], device["reseller_id"],
                         key, address, expiry, vpn.stamp()))
        except sqlite3.IntegrityError:
            abort(409)
        con.execute("INSERT INTO vpn_audit(actor,action,detail_json,created_at) VALUES(?,?,?,?)",
                    ("device", "auto_enroll", '{"device_row_id":%d}' % device["id"],
                     vpn.stamp()))
        return _response(con, device)


@app.after_request
def vpn_device_no_cache(response):
    if request.path.startswith("/v1/device/vpn/"):
        response.headers["Cache-Control"] = "no-store, private"
    return response


with db() as _con:
    migrate(_con)
