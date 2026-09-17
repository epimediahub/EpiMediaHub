#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.environ.setdefault("EPIMEDIAHUB_DATA_DIR", tempfile.mkdtemp(prefix="epimediahub-v052-"))
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
assert "/admin/customers/bulk" in rules
assert "/admin/customers/bulk-delete" in rules
assert "/admin/customers/<int:customer_id>/delete" in rules

client = app.test_client()
health = client.get("/health")
assert health.status_code == 200
assert health.get_json()["api_version"] == "0.5.2"

login = client.post("/admin/login", data={"password": "test-admin-password"})
assert login.status_code == 302

dashboard = client.get("/admin")
assert dashboard.status_code == 200
assert b"Playlist-Verwaltung" in dashboard.data
assert b"Mehrfachimport" in dashboard.data

bulk = client.post(
    "/admin/customers/bulk",
    data={
        "bulk_playlists": "\n".join(
            [
                "Kunde A | Wohnzimmer | https://example.invalid/a.m3u",
                "Kunde B | https://example.invalid/b.m3u",
                "Kunde C | XTREAM | https://xtream.example.invalid | demo | secret | ts | Hauptliste",
                "ungueltige zeile",
            ]
        )
    },
)
assert bulk.status_code == 302
with db() as con:
    rows = con.execute("SELECT id,name,config_json FROM customers ORDER BY id").fetchall()
assert len(rows) == 3, rows
assert rows[0]["name"] == "Kunde A"
assert "Hauptliste" in rows[2]["config_json"]

bulk_duplicate = client.post(
    "/admin/customers/bulk",
    data={"bulk_playlists": "Kunde A | Wohnzimmer | https://example.invalid/a.m3u"},
)
assert bulk_duplicate.status_code == 302
with db() as con:
    assert con.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 3

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
assert changed.get_json()["changed"] is True
assert changed.get_json()["config_version"] == 2

reported = client.post(
    "/v1/device/sync-result",
    headers=device_headers,
    json={"config_version": 2, "status": "ok", "error": ""},
)
assert reported.status_code == 200, reported.data

single_delete = client.post(
    f"/admin/customers/{customer_id}/delete",
    data={"confirm_delete": "1"},
)
assert single_delete.status_code == 302
with db() as con:
    assert con.execute("SELECT COUNT(*) FROM customers WHERE id=?", (customer_id,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM devices WHERE customer_id=?", (customer_id,)).fetchone()[0] == 0

with db() as con:
    remaining_ids = [str(r[0]) for r in con.execute("SELECT id FROM customers ORDER BY id LIMIT 2").fetchall()]
bulk_delete = client.post(
    "/admin/customers/bulk-delete",
    data={"confirm_delete": "1", "customer_ids": remaining_ids},
)
assert bulk_delete.status_code == 302
with db() as con:
    remaining = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
assert remaining == 1, remaining

print("Raspberry v0.5.2 dashboard smoke test OK")
