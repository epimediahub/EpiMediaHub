"""Opt-in GalaBox VPN at-rest encryption key escrow, without stored client VPN private keys.

This route is NOT used by the Fire TV AndroidKeyStore flow. Device-authorized
GalaBox clients fetch per-device, per-purpose AES-GCM *wrapping keys* only over
the existing authenticated HTTPS API and only while an approved VPN entitlement
is valid. Android stores ciphertext, never these wrapping keys. A master key
must be provisioned securely out-of-band and backed up; losing it prevents
decrypting previously enrolled GalaBox identities.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import stat
from pathlib import Path

from flask import abort, jsonify, request

from app import app, db
import vpn_auto_enroll as auto
import vpn_dashboard as vpn

MASTER_NAME = "galabox-vpn-vault-master.bin"
PURPOSES = frozenset({"identity", "profile"})


def _master():
    path = Path(os.environ.get("EPIMEDIAHUB_DATA_DIR", "/var/lib/epimediahub")) / MASTER_NAME
    try:
        # No symlinks and no implicit key regeneration. It must be backed up.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            meta = os.fstat(fd)
            if not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o077:
                raise ValueError("GalaBox master-key file permissions must be 0600")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                key = stream.read(33)
            if len(key) != 32:
                raise ValueError("GalaBox master key must be exactly 32 bytes")
            return key
        finally:
            os.close(fd)
    except (OSError, ValueError):
        abort(503, "GalaBox secure wrapping service is not configured")


def derive(master: bytes, device_id: str, purpose: str) -> bytes:
    """Distinct subkeys for each device and storage purpose; no VPN private key."""
    if len(master) != 32 or purpose not in PURPOSES:
        raise ValueError("Invalid vault derivation arguments")
    key_id = hashlib.sha256(device_id.encode("utf-8")).digest()
    data = b"EpiMediaHub/GalaBox/at-rest/v1/" + purpose.encode("ascii") + b"/" + key_id
    return hmac.new(master, data, hashlib.sha256).digest()


@app.post("/v1/device/vpn/galabox-vault-key")
def galabox_vault_key():
    device = auto._client()
    if request.content_length is not None and request.content_length > 400:
        abort(413)
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"device_id", "purpose"}:
        abort(400)
    if body["device_id"] != device["device_id"] or body["purpose"] not in PURPOSES:
        abort(403)
    # This endpoint is not part of and cannot replace existing Fire TV routes.
    # Require an explicitly approved, non-expired and properly owned VPN entry
    # or pending manual VPN-year / trial grant; never auto-issue new licenses.
    with db() as con:
        bound = auto._entry(con, device)
        expiry = bound["expires_at"] if bound else auto._authorization(con, device)
        if not expiry or vpn.instant(expiry) <= vpn.now():
            abort(403)
        if bound and bound["status"] != "ACTIVE":
            abort(403)
    master = _master()
    key = derive(master, device["device_id"], body["purpose"])
    response = jsonify(v=1, purpose=body["purpose"], device_id=device["device_id"],
                       key=base64.b64encode(key).decode("ascii"))
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
