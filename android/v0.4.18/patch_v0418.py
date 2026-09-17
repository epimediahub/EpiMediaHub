#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"
gradle = root / "app/build.gradle.kts"

s = gradle.read_text()
if 'versionCode = 57' not in s or 'versionName = "0.4.17"' not in s:
    raise SystemExit("v0.4.17 version anchors missing")
gradle.write_text(
    s.replace('versionCode = 57', 'versionCode = 58', 1)
     .replace('versionName = "0.4.17"', 'versionName = "0.4.18"', 1)
)

for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.4.17", "0.4.18"))

# Replace the failed Tailscale Funnel public provisioning endpoint with the
# owned EpiMediaHub domain. Tailscale remains available independently for
# private receiver/maintenance networking; provisioning is normal HTTPS.
gate = java / "ProvisioningGateActivity.kt"
g = gate.read_text()
old_server = 'private const val DEFAULT_SERVER = "https://epimedia.tail58077d.ts.net"'
new_server = 'private const val DEFAULT_SERVER = "https://setup.epimediahub.com"'
if old_server not in g:
    raise SystemExit("v0.4.17 Funnel provisioning server anchor missing")
g = g.replace(old_server, new_server, 1)
g = g.replace("Tailscale Funnel", "EpiMediaHub HTTPS")
gate.write_text(g)

# Defensive check: the obsolete public Funnel hostname must not survive in the
# reconstructed app source after this patch.
for p in java.rglob("*.kt"):
    if "epimedia.tail58077d.ts.net" in p.read_text():
        raise SystemExit(f"obsolete Funnel hostname remains in {p}")

print("Android v0.4.18 epimediahub.com provisioning patch applied")
