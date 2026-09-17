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
