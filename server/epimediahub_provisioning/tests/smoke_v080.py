#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.environ["EPIMEDIAHUB_DATA_DIR"] = tempfile.mkdtemp(prefix="epimediahub-v080-")
os.environ["EPIMEDIAHUB_PUBLIC_URL"] = "https://setup.epimediahub.com"
os.environ["EPIMEDIAHUB_ADMIN_TOKEN"] = "test-admin-token"
os.environ["EPIMEDIAHUB_ADMIN_PASSWORD"] = "test-admin-password"
os.environ["EPIMEDIAHUB_SECRET_KEY"] = "test-secret-key"
os.environ["EPIMEDIAHUB_SECURE_COOKIES"] = "0"
sys.path.insert(0, str(root))

from app import db
from wsgi import app

admin = app.test_client()
r1 = app.test_client()
r2 = app.test_client()
anon = app.test_client()

assert admin.get("/health").get_json()["api_version"] == "0.8.0"
assert admin.post("/admin/login", data={"password": "test-admin-password"}).status_code == 302

for data in (
    {
        "name": "Reseller Nord",
        "username": "nord",
        "password": "Passwort-123",
        "customer_limit": "10",
        "device_limit": "20",
        "branding_name": "Nord Media",
    },
    {
        "name": "Reseller Süd",
        "username": "sued",
        "password": "Passwort-456",
        "customer_limit": "5",
        "device_limit": "10",
        "branding_name": "",
    },
):
    response = admin.post("/admin/v080/resellers", data=data)
    assert response.status_code == 302, response.data

with db() as con:
    resellers = con.execute("SELECT id,username FROM resellers ORDER BY id").fetchall()
    assert len(resellers) == 2
    r1_id = int(resellers[0]["id"])
    r2_id = int(resellers[1]["id"])

assert r1.post("/reseller/login", data={"username": "nord", "password": "Passwort-123"}).status_code == 302
assert r2.post("/reseller/login", data={"username": "sued", "password": "Passwort-456"}).status_code == 302

assert r1.post("/reseller/customers", data={"name": "Kunde Nord"}).status_code == 302
assert r2.post("/reseller/customers", data={"name": "Kunde Süd"}).status_code == 302

with db() as con:
    nord = con.execute("SELECT id,reseller_id FROM customers WHERE name='Kunde Nord'").fetchone()
    sued = con.execute("SELECT id,reseller_id FROM customers WHERE name='Kunde Süd'").fetchone()
    assert int(nord["reseller_id"]) == r1_id
    assert int(sued["reseller_id"]) == r2_id
    nord_id = int(nord["id"])
    sued_id = int(sued["id"])

assert r1.post(
    f"/reseller/customers/{nord_id}/playlists",
    data={
        "playlist_name": "Nord IPTV",
        "playlist_type": "M3U",
        "playlist_url": "https://example.invalid/nord.m3u",
    },
).status_code == 302

# Tenant isolation: reseller Nord must not edit Süd customer.
assert r1.post(
    f"/reseller/customers/{sued_id}/rename",
    data={"name": "DARF NICHT"},
).status_code == 404

dash1 = r1.get("/reseller")
assert dash1.status_code == 200, dash1.data
assert b"Kunde Nord" in dash1.data
assert b"Nord IPTV" in dash1.data
assert b"Kunde SÃ¼d" not in dash1.data
assert b"Nord Media" in dash1.data
assert b"epimediahub-logo.svg" in dash1.data

dash2 = r2.get("/reseller")
assert dash2.status_code == 200
assert b"Kunde SÃ¼d" in dash2.data
assert b"Kunde Nord" not in dash2.data

pair = anon.post(
    "/v1/pair/start",
    json={"device_id": "nord-fire-tv", "device_name": "Wohnzimmer TV", "platform": "android"},
)
assert pair.status_code == 201, pair.data
pair_data = pair.get_json()

claim = r1.post(
    "/reseller/pairings/claim",
    data={"code": pair_data["code"], "customer_id": nord_id},
)
assert claim.status_code == 302

connected = anon.post("/v1/pair/status", json={"pairing_secret": pair_data["pairing_secret"]})
assert connected.status_code == 200, connected.data
payload = connected.get_json()
assert int(payload["customer_id"]) == nord_id
assert payload["config"]["playlists"][0]["playlist_name"] == "Nord IPTV"

with db() as con:
    device = con.execute(
        "SELECT d.id,c.reseller_id FROM devices d JOIN customers c ON c.id=d.customer_id WHERE d.device_id='nord-fire-tv'"
    ).fetchone()
    assert device is not None
    assert int(device["reseller_id"]) == r1_id
    device_id = int(device["id"])

assert r1.post(f"/reseller/devices/{device_id}/rename", data={"name": "Nord Wohnzimmer"}).status_code == 302
assert r2.post(f"/reseller/devices/{device_id}/rename", data={"name": "Fremd"}).status_code == 404

# Admin can see and manage all tenants.
admin_dashboard = admin.get("/admin")
assert admin_dashboard.status_code == 200, admin_dashboard.data
for expected in (b"Reseller Nord", b"Reseller SÃ¼d", b"Kunde Nord", b"Kunde SÃ¼d", b"Reseller-Zuordnung", b"epimediahub-logo.svg"):
    assert expected in admin_dashboard.data, expected

# Move Süd customer to Nord using admin; reseller Nord should then see it.
moved = admin.post(f"/admin/v080/customers/{sued_id}/reseller", data={"reseller_id": str(r1_id)})
assert moved.status_code == 302
assert b"Kunde SÃ¼d" in r1.get("/reseller").data
assert b"Kunde SÃ¼d" not in r2.get("/reseller").data

# Disable Nord and verify current reseller session is rejected.
assert admin.post(f"/admin/v080/resellers/{r1_id}/toggle").status_code == 302
blocked = r1.get("/reseller")
assert blocked.status_code == 302
assert "/reseller/login" in blocked.headers["Location"]

with db() as con:
    audit_count = con.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert audit_count >= 8
    assert con.execute("SELECT COUNT(*) FROM resellers").fetchone()[0] == 2
    assert "reseller_id" in {row[1] for row in con.execute("PRAGMA table_info(customers)")}

print("Raspberry v0.8.0 reseller isolation, dashboard, branding and audit smoke test OK")
