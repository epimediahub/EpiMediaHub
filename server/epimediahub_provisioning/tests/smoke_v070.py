#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.environ["EPIMEDIAHUB_DATA_DIR"] = tempfile.mkdtemp(prefix="epimediahub-v070-")
os.environ["EPIMEDIAHUB_PUBLIC_URL"] = "https://setup.epimediahub.com"
os.environ["EPIMEDIAHUB_ADMIN_TOKEN"] = "test-admin-token"
os.environ["EPIMEDIAHUB_ADMIN_PASSWORD"] = "test-admin-password"
os.environ["EPIMEDIAHUB_SECRET_KEY"] = "test-secret-key"
os.environ["EPIMEDIAHUB_SECURE_COOKIES"] = "0"
sys.path.insert(0, str(root))

from app import db
from wsgi import app

client = app.test_client()
assert client.get("/health").get_json()["api_version"] == "0.7.0"
assert client.post("/admin/login", data={"password": "test-admin-password"}).status_code == 302

created = client.post(
    "/v1/admin/customers",
    headers={"Authorization": "Bearer test-admin-token"},
    json={
        "name": "Familie Test",
        "config": {
            "playlist_type": "M3U",
            "playlist_name": "Bestand",
            "playlist_url": "https://example.invalid/old.m3u",
        },
    },
)
customer_id = created.get_json()["id"]
activation = client.post(
    f"/v1/admin/customers/{customer_id}/activation",
    headers={"Authorization": "Bearer test-admin-token"},
    json={"ttl_minutes": 60},
).get_json()
redeem = client.post(
    "/v1/setup/redeem",
    json={"code": activation["code"], "device_id": "wohnzimmer-tv", "platform": "android"},
)
assert redeem.status_code == 200
token = redeem.get_json()["session_token"]
with db() as con:
    device = con.execute("SELECT * FROM devices WHERE device_id='wohnzimmer-tv'").fetchone()
    device_id = int(device["id"])
    migrated = con.execute("SELECT * FROM device_playlists WHERE device_id=?", (device_id,)).fetchall()
    assert len(migrated) == 1 and migrated[0]["name"] == "Bestand"

added = client.post(
    f"/admin/v070/devices/{device_id}/playlists",
    data={
        "playlist_name": "Sport",
        "playlist_type": "XTREAM",
        "xtream_server": "https://stream.example.invalid",
        "xtream_username": "user",
        "xtream_password": "secret",
        "xtream_output": "ts",
    },
)
assert added.status_code == 302

config = client.get(
    "/v1/device/config?version=0", headers={"Authorization": f"Bearer {token}"}
).get_json()
assert config["changed"] is True
assert [item["playlist_name"] for item in config["config"]["playlists"]] == ["Bestand", "Sport"]
assert config["config"]["playlist_name"] == "Bestand"  # compatibility for old clients

# Deleting the final playlist must not resurrect the legacy customer config.
with db() as con:
    ids = [row[0] for row in con.execute("SELECT id FROM device_playlists WHERE device_id=?", (device_id,))]
for playlist_id in ids:
    assert client.post(f"/admin/v070/playlists/{playlist_id}/delete").status_code == 302
client.get("/admin")  # runs the migration again
with db() as con:
    assert con.execute("SELECT COUNT(*) FROM device_playlists WHERE device_id=?", (device_id,)).fetchone()[0] == 0
assert client.post(
    f"/admin/v070/devices/{device_id}/playlists",
    data={"playlist_name": "Sport", "playlist_type": "XTREAM", "xtream_server": "https://stream.example.invalid", "xtream_username": "user", "xtream_password": "secret"},
).status_code == 302

with db() as con:
    old_id = con.execute(
        "SELECT id FROM device_playlists WHERE device_id=? AND name='Sport'", (device_id,)
    ).fetchone()[0]
assert client.post(f"/admin/v070/playlists/{old_id}/delete").status_code == 302
assert client.post(
    f"/admin/v070/devices/{device_id}/playlists",
    data={
        "playlist_name": "Bestand neu",
        "playlist_type": "M3U",
        "playlist_url": "https://example.invalid/new.m3u",
    },
).status_code == 302

config = client.get(
    "/v1/device/config?version=0", headers={"Authorization": f"Bearer {token}"}
).get_json()["config"]
assert [item["playlist_name"] for item in config["playlists"]] == ["Bestand neu"]

dashboard = client.get("/admin")
assert dashboard.status_code == 200
for text in (b"Familie Test", b"wohnzimmer-tv", b"Sport", b"Playlist hinzuf"):
    assert text in dashboard.data

print("Raspberry v0.7.0 customer-device-playlist hierarchy smoke test OK")
