#!/usr/bin/env python3
from __future__ import annotations

import os
import runpy
from pathlib import Path

os.environ["EPIMEDIAHUB_EXPECTED_API_VERSION"] = "0.6.0"
scope = runpy.run_path(str(Path(__file__).with_name("smoke_v052.py")), run_name="__main__")

dashboard = scope["client"].get("/admin")
assert dashboard.status_code == 200
assert b"Willkommen zur\xc3\xbcck." in dashboard.data
assert b"Direkt erledigen" in dashboard.data
assert b"Letzte Aktivierungen" in dashboard.data
assert b"API 0.6.0" in dashboard.data


app = scope["app"]
client = scope["client"]
db = scope["db"]

rules = [r.rule for r in app.url_map.iter_rules()]
assert "/admin/devices/<int:device_id>/rename" in rules
assert "/admin/devices/<int:device_id>/delete" in rules

with db() as con:
    customer_id = con.execute("SELECT id FROM customers ORDER BY id LIMIT 1").fetchone()[0]
    before_customers = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    cur = con.execute(
        "INSERT INTO devices(customer_id,device_id,platform,session_token_hash,created_at) VALUES(?,?,?,?,?)",
        (customer_id, "smoke-device-manage", "android", "smoke-device-manage-hash", "2026-09-20T20:00:00Z"),
    )
    device_row_id = cur.lastrowid

renamed = client.post(
    f"/admin/devices/{device_row_id}/rename",
    data={"display_name": "Wohnzimmer TV"},
)
assert renamed.status_code == 302
with db() as con:
    row = con.execute(
        "SELECT device_id,display_name FROM devices WHERE id=?", (device_row_id,)
    ).fetchone()
    assert row["device_id"] == "smoke-device-manage"
    assert row["display_name"] == "Wohnzimmer TV"

dashboard = client.get("/admin")
assert b"Wohnzimmer TV" in dashboard.data
assert b"smoke-device-manage" in dashboard.data
assert b"Umbenennen" in dashboard.data
assert b"L\xc3\xb6schen" in dashboard.data

deleted = client.post(
    f"/admin/devices/{device_row_id}/delete",
    data={"confirm_delete": "1"},
)
assert deleted.status_code == 302
with db() as con:
    assert con.execute("SELECT COUNT(*) FROM devices WHERE id=?", (device_row_id,)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == before_customers
