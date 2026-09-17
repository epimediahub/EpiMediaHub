#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.environ.setdefault("EPIMEDIAHUB_DATA_DIR", tempfile.mkdtemp(prefix="epimediahub-v051-"))
os.environ.setdefault("EPIMEDIAHUB_PUBLIC_URL", "https://setup.epimediahub.com")
os.environ.setdefault("EPIMEDIAHUB_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("EPIMEDIAHUB_ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("EPIMEDIAHUB_SECRET_KEY", "test-secret-key")
os.environ.setdefault("EPIMEDIAHUB_SECURE_COOKIES", "0")

import sys
sys.path.insert(0, str(root))

from wsgi import app
from app import db
from receiver_sync import save_customer_config

rules = [r.rule for r in app.url_map.iter_rules()]
assert rules.count("/v1/device/config") == 1, rules
assert rules.count("/v1/device/sync-result") == 1, rules
assert rules.count("/v1/device/bootstrap") == 1, rules

client = app.test_client()
health = client.get("/health")
assert health.status_code == 200
assert health.get_json()["api_version"] == "0.5.1"

admin_headers = {"Authorization": "Bearer test-admin-token"}
created = client.post(
    "/v1/admin/customers",
    headers=admin_headers,
    json={
        "name": "Smoke Kunde",
        "config": {
            "playlist_type": "M3U",
            "playlist_name": "Smoke M3U",
            "playlist_url": "https://example.invalid/list.m3u",
        },
    },
)
assert created.status_code == 201, created.data
customer_id = created.get_json()["id"]

activation = client.post(
    f"/v1/admin/customers/{customer_id}/activation",
    headers=admin_headers,
    json={"ttl_minutes": 60},
)
assert activation.status_code == 201, activation.data
activation_body = activation.get_json()
assert activation_body["activation_url"].startswith("https://setup.epimediahub.com/connect/")
connect_path = activation_body["activation_url"].split("setup.epimediahub.com", 1)[1]
assert client.get(connect_path).status_code == 200

redeem = client.post(
    "/v1/setup/redeem",
    json={"code": activation_body["code"], "device_id": "smoke-android", "platform": "android"},
)
assert redeem.status_code == 200, redeem.data
body = redeem.get_json()
assert body["config_version"] == 1
assert body["config"]["playlist_type"] == "M3U"
token = body["session_token"]
device_headers = {"Authorization": f"Bearer {token}"}

same = client.get("/v1/device/config?version=1", headers=device_headers)
assert same.status_code == 200
assert same.get_json()["changed"] is False

with db() as con:
    version = save_customer_config(
        con,
        customer_id,
        {
            "playlist_type": "XTREAM",
            "playlist_name": "Smoke Xtream",
            "playlist_url": "",
            "xtream_server": "https://xtream.example.invalid",
            "xtream_username": "demo",
            "xtream_password": "secret",
            "xtream_output": "ts",
        },
    )
assert version == 2

changed = client.get("/v1/device/config?version=1", headers=device_headers)
assert changed.status_code == 200
changed_body = changed.get_json()
assert changed_body["changed"] is True
assert changed_body["config_version"] == 2
assert changed_body["config"]["playlist_type"] == "XTREAM"

reported = client.post(
    "/v1/device/sync-result",
    headers=device_headers,
    json={"config_version": 2, "status": "ok", "error": ""},
)
assert reported.status_code == 200, reported.data
assert reported.get_json()["applied_config_version"] == 2

current = client.get("/v1/device/config?version=2", headers=device_headers)
assert current.status_code == 200
assert current.get_json()["changed"] is False

print("Raspberry v0.5.1 smoke test OK")
