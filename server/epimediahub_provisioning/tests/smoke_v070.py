#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.environ["EPIMEDIAHUB_DATA_DIR"] = tempfile.mkdtemp(prefix="epimediahub-v076-")
os.environ["EPIMEDIAHUB_PUBLIC_URL"] = "https://setup.epimediahub.com"
os.environ["EPIMEDIAHUB_ADMIN_TOKEN"] = "test-admin-token"
os.environ["EPIMEDIAHUB_ADMIN_PASSWORD"] = "test-admin-password"
os.environ["EPIMEDIAHUB_SECRET_KEY"] = "test-secret-key"
os.environ["EPIMEDIAHUB_SECURE_COOKIES"] = "0"
sys.path.insert(0, str(root))

from app import db
from wsgi import app

client = app.test_client()
assert client.get("/health").get_json()["api_version"] == "0.7.6"
assert client.post("/admin/login", data={"password": "test-admin-password"}).status_code == 302

headers = {"Authorization": "Bearer test-admin-token"}
created = client.post(
    "/v1/admin/customers",
    headers=headers,
    json={
        "name": "Familie Test",
        "config": {
            "playlist_type": "M3U",
            "playlist_name": "Bestand",
            "playlist_url": "https://example.invalid/old.m3u",
        },
    },
)
assert created.status_code == 201, created.data
customer_id = created.get_json()["id"]


def connect_device(device_id: str):
    activation = client.post(
        f"/v1/admin/customers/{customer_id}/activation",
        headers=headers,
        json={"ttl_minutes": 60},
    ).get_json()
    redeem = client.post(
        "/v1/setup/redeem",
        json={"code": activation["code"], "device_id": device_id, "platform": "android"},
    )
    assert redeem.status_code == 200, redeem.data
    return redeem.get_json()["session_token"]


token_tv = connect_device("wohnzimmer-tv")
token_mobile = connect_device("daniel-handy")

with db() as con:
    devices = con.execute(
        "SELECT id,device_id FROM devices WHERE customer_id=? ORDER BY id",
        (customer_id,),
    ).fetchall()
    assert len(devices) == 2
    tv_row_id = next(int(row["id"]) for row in devices if row["device_id"] == "wohnzimmer-tv")
    mobile_row_id = next(int(row["id"]) for row in devices if row["device_id"] == "daniel-handy")
    migrated = con.execute(
        "SELECT name FROM customer_playlists WHERE customer_id=? ORDER BY id",
        (customer_id,),
    ).fetchall()
    assert [row["name"] for row in migrated] == ["Bestand"], migrated

added = client.post(
    f"/admin/v076/customers/{customer_id}/playlists",
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

def names_for(token: str):
    result = client.get(
        "/v1/device/config?version=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert result.status_code == 200, result.data
    return [item["playlist_name"] for item in result.get_json()["config"]["playlists"]]

assert names_for(token_tv) == ["Bestand", "Sport"]
assert names_for(token_mobile) == ["Bestand", "Sport"]

renamed = client.post(
    f"/admin/v074/devices/{mobile_row_id}/rename",
    data={"name": "Daniels Handy"},
)
assert renamed.status_code == 302
with db() as con:
    row = con.execute(
        "SELECT device_id,display_name FROM devices WHERE id=?",
        (mobile_row_id,),
    ).fetchone()
    assert row["device_id"] == "daniel-handy"
    assert row["display_name"] == "Daniels Handy"

deleted = client.post(
    f"/admin/v074/devices/{tv_row_id}/delete",
    data={"confirm": f"DELETE_DEVICE:{tv_row_id}"},
)
assert deleted.status_code == 302
with db() as con:
    assert con.execute("SELECT COUNT(*) FROM devices WHERE id=?", (tv_row_id,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM devices WHERE id=?", (mobile_row_id,)).fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM customers WHERE id=?", (customer_id,)).fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM customer_playlists WHERE customer_id=?", (customer_id,)).fetchone()[0] == 2

assert names_for(token_mobile) == ["Bestand", "Sport"]

dashboard = client.get("/admin")
assert dashboard.status_code == 200
for expected in (
    b"Familie Test",
    b"Daniels Handy",
    b"Bestand",
    b"Sport",
    b"Playlist hinzuf",
    b"Ger\xc3\xa4t umbenennen",
    b"Ger\xc3\xa4t l\xc3\xb6schen",
):
    assert expected in dashboard.data, expected

print("Raspberry v0.7.6 customer-playlist-device inheritance smoke test OK")
