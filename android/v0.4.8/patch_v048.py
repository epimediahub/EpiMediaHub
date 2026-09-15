#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def require_once(text: str, needle: str, label: str):
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")


# Keep the remote-maintenance state fresh while its screen is open. This lets a
# dropped/expired Tailscale session recover automatically or surface NeedsLogin
# immediately instead of leaving a stale green state on screen.
web = java / "ui/V047WebAdmin.kt"
s = web.read_text()
anchor = '''    LaunchedEffect(Unit) {\n        if (!u.webAdminRunning) vm.startWebAdmin()\n        if (u.remoteMaintenanceUnlocked) RemoteTailscaleManager.ensureConnected()\n        while (true) {\n            delay(2000L)\n            vm.refreshWebAdminAccess()\n        }\n    }\n'''
require_once(s, anchor, "v0.4.7 web-admin polling")
replacement = anchor + '''\n    LaunchedEffect(u.remoteMaintenanceUnlocked) {\n        if (u.remoteMaintenanceUnlocked) {\n            while (true) {\n                RemoteTailscaleManager.ensureConnected()\n                delay(10_000L)\n            }\n        }\n    }\n'''
s = s.replace(anchor, replacement, 1)
web.write_text(s)

# Visible version labels and HTTP user agents.
home = java / "ui/V044Home.kt"
s = home.read_text().replace('0.4.7', '0.4.8')
home.write_text(s)

screens = java / "ui/Screens.kt"
s = screens.read_text().replace('Android v0.4.7', 'Android v0.4.8')
screens.write_text(s)

med = java / "data/MediathekClient.kt"
s = med.read_text().replace('EpiMediaHub-Android/0.4.7', 'EpiMediaHub-Android/0.4.8').replace('EpiMediaHub/0.4.7', 'EpiMediaHub/0.4.8')
med.write_text(s)

print("Android v0.4.8 Tailscale recovery/status polling patch applied")
