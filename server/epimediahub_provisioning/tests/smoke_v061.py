#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.environ.setdefault("EPIMEDIAHUB_DATA_DIR", tempfile.mkdtemp(prefix="epimediahub-v061-"))
os.environ.setdefault("EPIMEDIAHUB_PUBLIC_URL", "https://setup.epimediahub.com")
os.environ.setdefault("EPIMEDIAHUB_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("EPIMEDIAHUB_ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("EPIMEDIAHUB_SECRET_KEY", "test-secret-key")
os.environ.setdefault("EPIMEDIAHUB_SECURE_COOKIES", "0")

import sys

sys.path.insert(0, str(root))

from app import db
from dashboard_v061 import UNASSIGNED_CUSTOMER_NAME
from wsgi import app

client = app.test_client()
assert client.get("/health").get_json()["api_version"] == "0.6.1"
assert client.post("/admin/login", data={"password": "test-admin-password"}).status_code == 302

# Create the original playlist and register a device against it.
created = client.post(
    "/v1/admin/customers",
    headers={"Authorization": "Bearer test-admin-token"},
    json={
        "name": "Alter Kunde",
        "config": {
            "playlist_type": "M3U",
            "playlist_name": "Alte Playlist",
            "playlist_url": "https://example.invalid/old.m3u",
        },
    },
)
assert created.status_code == 201
old_customer_id = created.get_json()["id"]
activation = client.post(
    f"/v1/admin/customers/{old_customer_id}/activation",
    headers={"Authorization": "Bearer test-admin-token"},
    json={"ttl_minutes": 60},
).get_json()
redeem = client.post(
    "/v1/setup/redeem",
    json={"code": activation["code"], "device_id": "wohnzimmer-fire-tv", "platform": "android"},
)
assert redeem.status_code == 200
session_token = redeem.get_json()["session_token"]
with db() as con:
    device_id = con.execute(
        "SELECT id FROM devices WHERE device_id='wohnzimmer-fire-tv'"
    ).fetchone()[0]

# The add form can assign the existing device directly to the replacement playlist.
replacement = client.post(
    "/admin/customers",
    data={
        "name": "Neuer Kunde",
        "playlist_name": "Neue Playlist",
        "playlist_type": "M3U",
        "playlist_url": "https://example.invalid/new.m3u",
        "device_ids": str(device_id),
    },
)
assert replacement.status_code == 302
with db() as con:
    new_customer_id = con.execute(
        "SELECT id FROM customers WHERE name='Neuer Kunde'"
    ).fetchone()[0]
    device = con.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    assert device["customer_id"] == new_customer_id
    assert device["last_sync_status"] == "pending"
    assert device["applied_config_version"] == 0

config = client.get(
    "/v1/device/config?version=999",
    headers={"Authorization": f"Bearer {session_token}"},
)
assert config.status_code == 200
assert config.get_json()["config"]["playlist_url"] == "https://example.invalid/new.m3u"

dashboard = client.get("/admin")
assert dashboard.status_code == 200
assert b"Auf Ger\xc3\xa4te \xc3\xbcbertragen" in dashboard.data
assert b"Ger\xc3\xa4tezuweisung" in dashboard.data
assert b"Zugewiesene Playlist" in dashboard.data
assert UNASSIGNED_CUSTOMER_NAME.encode() not in dashboard.data

# Removing the checkmark unassigns but does not delete the device or its token.
updated = client.post(
    f"/admin/customers/{new_customer_id}/update",
    data={
        "name": "Neuer Kunde",
        "playlist_name": "Neue Playlist",
        "playlist_type": "M3U",
        "playlist_url": "https://example.invalid/new.m3u",
    },
)
assert updated.status_code == 302
with db() as con:
    device = con.execute(
        "SELECT d.*,c.name customer_name FROM devices d JOIN customers c ON c.id=d.customer_id WHERE d.id=?",
        (device_id,),
    ).fetchone()
    assert device is not None
    assert device["customer_name"] == UNASSIGNED_CUSTOMER_NAME

# Reassigning and then deleting the playlist must keep the device available.
client.post(
    f"/admin/customers/{new_customer_id}/update",
    data={
        "name": "Neuer Kunde",
        "playlist_name": "Neue Playlist",
        "playlist_type": "M3U",
        "playlist_url": "https://example.invalid/new.m3u",
        "device_ids": str(device_id),
    },
)
deleted = client.post(
    f"/admin/customers/{new_customer_id}/delete", data={"confirm_delete": "1"}
)
assert deleted.status_code == 302
with db() as con:
    assert con.execute("SELECT COUNT(*) FROM devices WHERE id=?", (device_id,)).fetchone()[0] == 1
    device = con.execute(
        "SELECT d.*,c.name customer_name FROM devices d JOIN customers c ON c.id=d.customer_id WHERE d.id=?",
        (device_id,),
    ).fetchone()
    assert device["customer_name"] == UNASSIGNED_CUSTOMER_NAME

print("Raspberry v0.6.1 device assignment smoke test OK")
