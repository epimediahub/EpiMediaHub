#!/usr/bin/env python3
"""EpiMediaHub one-shot Tailscale device provisioner.

Runs on the trusted Raspberry Pi LAN interface. It keeps the Tailscale OAuth
client secret off Android devices and returns only a short-lived, one-use,
pre-authorized tagged auth key after the EpiMediaHub remote-maintenance PIN is
verified.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN_HOST = os.environ.get("EPI_PROVISION_HOST", "192.168.0.207")
LISTEN_PORT = int(os.environ.get("EPI_PROVISION_PORT", "8787"))
TAILNET = os.environ.get("TS_TAILNET", "-")
TAG = os.environ.get("TS_DEVICE_TAG", "tag:epimediahub-family")
OAUTH_ID = os.environ.get("TS_OAUTH_CLIENT_ID", "")
OAUTH_SECRET = os.environ.get("TS_OAUTH_CLIENT_SECRET", "")
# v0.4.6+ fixed Fernwartungs-PIN digest. Plaintext is never stored here.
REMOTE_PIN_HASH = os.environ.get(
    "EPI_REMOTE_PIN_HASH",
    "7a866153fcd1a9ed6c44f051287622547d959709cd49731684a70dbfac852c58",
).lower()
KEY_EXPIRY_SECONDS = int(os.environ.get("TS_AUTHKEY_EXPIRY_SECONDS", "300"))
LAN_CIDR = ipaddress.ip_network(os.environ.get("EPI_PROVISION_LAN", "192.168.0.0/24"), strict=False)

_attempts: dict[str, deque[float]] = defaultdict(deque)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _allowed_client(addr: str) -> bool:
    try:
        return ipaddress.ip_address(addr) in LAN_CIDR
    except ValueError:
        return False


def _rate_ok(addr: str) -> bool:
    now = time.monotonic()
    q = _attempts[addr]
    while q and now - q[0] > 600:
        q.popleft()
    if len(q) >= 5:
        return False
    q.append(now)
    return True


def _oauth_token() -> str:
    if not OAUTH_ID or not OAUTH_SECRET:
        raise RuntimeError("TS_OAUTH_CLIENT_ID/TS_OAUTH_CLIENT_SECRET are not configured")
    body = urllib.parse.urlencode(
        {
            "client_id": OAUTH_ID,
            "client_secret": OAUTH_SECRET,
            "grant_type": "client_credentials",
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.tailscale.com/api/v2/oauth/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "EpiMediaHub-Provisioner/1"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        payload = json.load(response)
    token = str(payload.get("access_token") or "")
    if not token:
        raise RuntimeError("Tailscale OAuth response contained no access_token")
    return token


def _create_auth_key(token: str) -> str:
    payload = {
        "capabilities": {
            "devices": {
                "create": {
                    "reusable": False,
                    "ephemeral": False,
                    "preauthorized": True,
                    "tags": [TAG],
                }
            }
        },
        "expirySeconds": KEY_EXPIRY_SECONDS,
    }
    url = f"https://api.tailscale.com/api/v2/tailnet/{urllib.parse.quote(TAILNET, safe='-')}/keys"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "EpiMediaHub-Provisioner/1",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        result = json.load(response)
    key = str(result.get("key") or "")
    if not key.startswith("tskey-"):
        raise RuntimeError("Tailscale API returned no usable auth key")
    return key


class Handler(BaseHTTPRequestHandler):
    server_version = "EpiMediaHubProvisioner/1"

    def _json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path != "/health":
            self._json(404, {"ok": False, "error": "not_found"})
            return
        if not _allowed_client(self.client_address[0]):
            self._json(403, {"ok": False, "error": "lan_only"})
            return
        self._json(200, {"ok": True, "service": "epimediahub-provisioner", "tag": TAG})

    def do_POST(self) -> None:
        if self.path != "/v1/enroll":
            self._json(404, {"ok": False, "error": "not_found"})
            return
        peer = self.client_address[0]
        if not _allowed_client(peer):
            self._json(403, {"ok": False, "error": "lan_only"})
            return
        if not _rate_ok(peer):
            self._json(429, {"ok": False, "error": "too_many_attempts"})
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 8192)
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._json(400, {"ok": False, "error": "invalid_json"})
            return
        pin = str(data.get("pin") or "")
        if len(pin) != 4 or not pin.isdigit() or _sha256(pin) != REMOTE_PIN_HASH:
            self._json(403, {"ok": False, "error": "bad_remote_pin"})
            return
        device = str(data.get("deviceName") or "android")[:80]
        try:
            token = _oauth_token()
            auth_key = _create_auth_key(token)
        except urllib.error.HTTPError as exc:
            detail = exc.read(1024).decode("utf-8", "replace")
            print(f"Tailscale API HTTP {exc.code}: {detail}", flush=True)
            self._json(502, {"ok": False, "error": "tailscale_api_error"})
            return
        except Exception as exc:
            print(f"Provisioning error: {exc}", flush=True)
            self._json(503, {"ok": False, "error": "provisioning_unavailable"})
            return
        print(f"Issued one-shot Tailscale key for {device} from {peer}", flush=True)
        self._json(
            200,
            {
                "ok": True,
                "authKey": auth_key,
                "controlUrl": "https://controlplane.tailscale.com",
                "tag": TAG,
                "expiresIn": KEY_EXPIRY_SECONDS,
            },
        )

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.client_address[0]} - {fmt % args}", flush=True)


def main() -> None:
    print(f"EpiMediaHub provisioner listening on {LISTEN_HOST}:{LISTEN_PORT}; LAN={LAN_CIDR}; tag={TAG}", flush=True)
    ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
