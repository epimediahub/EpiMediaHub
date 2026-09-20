#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.environ["EPIMEDIAHUB_DATA_DIR"] = tempfile.mkdtemp(prefix="epimediahub-v073-")
os.environ["EPIMEDIAHUB_PUBLIC_URL"] = "https://setup.epimediahub.com"
os.environ["EPIMEDIAHUB_ADMIN_TOKEN"] = "test-admin-token"
os.environ["EPIMEDIAHUB_ADMIN_PASSWORD"] = "test-admin-password"
os.environ["EPIMEDIAHUB_SECRET_KEY"] = "test-secret-key"
os.environ["EPIMEDIAHUB_SECURE_COOKIES"] = "0"
sys.path.insert(0, str(root))

from app import db
from wsgi import app

client = app.test_client()
admin_headers = {"Authorization": "Bearer test-admin-token"}

assert client.get("/health").get_json()["api_version"] == "0.7.4"
assert client.post("/admin/login", data={"password": "test-admin-password"}).status_code == 302

target = client.post(
    "/v1/admin/customers",
    headers=admin_headers,
    json={
        "name": "Zu löschen",
        "config": {
            "playlist_type": "M3U",
            "playlist_name": "Rai Test",
            "playlist_url": "https://example.invalid/rai.m3u",
        },
    },
)
assert target.status_code == 201
target_id = int(target.get_json()["id"])

survivor = client.post(
    "/v1/admin/customers",
    headers=admin_headers,
    json={"name": "Bleibt erhalten", "config": {}},
)
assert survivor.status_code == 201
survivor_id = int(survivor.get_json()["id"])

pairing = client.post(
    "/v1/pair/start",
    json={
        "device_id": "android-installation-uuid",
        "device_name": "Fire TV Wohnzimmer",
        "platform": "android",
    },
)
assert pairing.status_code == 201
pairing_data = pairing.get_json()
assert len(pairing_data["code"].replace("-", "")) == 8
pairing_secret = pairing_data["pairing_secret"]

pending = client.post("/v1/pair/status", json={"pairing_secret": pairing_secret})
assert pending.status_code == 202
assert pending.get_json()["status"] == "pending"

claim = client.post(
    "/admin/v073/pairings/claim",
    data={"code": pairing_data["code"], "customer_id": target_id},
)
assert claim.status_code == 302

connected = client.post("/v1/pair/status", json={"pairing_secret": pairing_secret})
assert connected.status_code == 200
connected_data = connected.get_json()
assert connected_data["status"] == "connected"
assert int(connected_data["customer_id"]) == target_id
assert connected_data["config"]["playlists"][0]["playlist_name"] == "Rai Test"

with db() as con:
    target_device = con.execute(
        "SELECT id,display_name FROM devices WHERE customer_id=? AND device_id=?",
        (target_id, "android-installation-uuid"),
    ).fetchone()
    assert target_device is not None
    target_device_id = int(target_device["id"])
    assert target_device["display_name"] == "Fire TV Wohnzimmer"

renamed = client.post(
    f"/admin/v074/devices/{target_device_id}/rename",
    data={"name": "Wohnzimmer Fire TV"},
)
assert renamed.status_code == 302
with db() as con:
    assert con.execute("SELECT display_name FROM devices WHERE id=?", (target_device_id,)).fetchone()[0] == "Wohnzimmer Fire TV"

session_token = connected_data["session_token"]
device_config = client.get(
    "/v1/device/config?version=0",
    headers={"Authorization": f"Bearer {session_token}"},
)
assert device_config.status_code == 200
assert device_config.get_json()["config"]["playlists"][0]["playlist_name"] == "Rai Test"

activation = client.post(
    f"/v1/admin/customers/{target_id}/activation",
    headers=admin_headers,
    json={"ttl_minutes": 60},
)
assert activation.status_code == 201

dashboard = client.get("/admin")
assert dashboard.status_code == 200
for text in (
    b"Ger\xc3\xa4t per Code verbinden",
    b"Kunde l\xc3\xb6schen",
    b"Ger\xc3\xa4t umbenennen",
    b"Ger\xc3\xa4t l\xc3\xb6schen",
    b"Wohnzimmer Fire TV",
    b"ABCD-EFGH",
):
    assert text in dashboard.data

wrong_confirmation = client.post(
    f"/admin/v073/customers/{target_id}/delete",
    data={"confirm": "DELETE:999999"},
)
assert wrong_confirmation.status_code == 400

deleted = client.post(
    f"/admin/v073/customers/{target_id}/delete",
    data={"confirm": f"DELETE:{target_id}"},
)
assert deleted.status_code == 302

with db() as con:
    assert con.execute("SELECT 1 FROM customers WHERE id=?", (target_id,)).fetchone() is None
    assert con.execute("SELECT 1 FROM customers WHERE id=?", (survivor_id,)).fetchone() is not None
    assert con.execute("SELECT COUNT(*) FROM devices WHERE customer_id=?", (target_id,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM activations WHERE customer_id=?", (target_id,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM pairings WHERE customer_id=?", (target_id,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM device_playlists").fetchone()[0] == 0

revoked = client.get(
    "/v1/device/config?version=0",
    headers={"Authorization": f"Bearer {session_token}"},
)
assert revoked.status_code == 401

pairing2 = client.post(
    "/v1/pair/start",
    json={
        "device_id": "android-delete-me",
        "device_name": "Schlafzimmer TV",
        "platform": "android",
    },
)
assert pairing2.status_code == 201
pairing2_data = pairing2.get_json()
claim2 = client.post(
    "/admin/v073/pairings/claim",
    data={"code": pairing2_data["code"], "customer_id": survivor_id},
)
assert claim2.status_code == 302
connected2 = client.post("/v1/pair/status", json={"pairing_secret": pairing2_data["pairing_secret"]})
assert connected2.status_code == 200
session_token2 = connected2.get_json()["session_token"]

with db() as con:
    delete_device = con.execute(
        "SELECT id,display_name FROM devices WHERE customer_id=? AND device_id=?",
        (survivor_id, "android-delete-me"),
    ).fetchone()
    assert delete_device is not None
    delete_device_id = int(delete_device["id"])
    assert delete_device["display_name"] == "Schlafzimmer TV"

assert client.post(
    f"/admin/v074/devices/{delete_device_id}/rename",
    data={"name": "Testgerät löschen"},
).status_code == 302

added_playlist = client.post(
    f"/admin/v070/devices/{delete_device_id}/playlists",
    data={
        "playlist_type": "M3U",
        "playlist_name": "Delete Test",
        "playlist_url": "https://example.invalid/delete.m3u",
    },
)
assert added_playlist.status_code == 302

wrong_device_confirmation = client.post(
    f"/admin/v074/devices/{delete_device_id}/delete",
    data={"confirm": "DELETE_DEVICE:999999"},
)
assert wrong_device_confirmation.status_code == 400

deleted_device = client.post(
    f"/admin/v074/devices/{delete_device_id}/delete",
    data={"confirm": f"DELETE_DEVICE:{delete_device_id}"},
)
assert deleted_device.status_code == 302

with db() as con:
    assert con.execute("SELECT 1 FROM customers WHERE id=?", (survivor_id,)).fetchone() is not None
    assert con.execute("SELECT 1 FROM devices WHERE id=?", (delete_device_id,)).fetchone() is None
    assert con.execute("SELECT COUNT(*) FROM device_playlists WHERE device_id=?", (delete_device_id,)).fetchone()[0] == 0
    assert con.execute(
        "SELECT COUNT(*) FROM pairings WHERE customer_id=? AND device_id=?",
        (survivor_id, "android-delete-me"),
    ).fetchone()[0] == 0

deleted_device_auth = client.get(
    "/v1/device/config?version=0",
    headers={"Authorization": f"Bearer {session_token2}"},
)
assert deleted_device_auth.status_code == 401

print("Raspberry v0.7.4 device rename/delete and pairing dashboard smoke test OK")
