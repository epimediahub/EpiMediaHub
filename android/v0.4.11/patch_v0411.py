#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def require_once(text: str, needle: str, label: str):
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")

# Version metadata.
gradle = root / "app/build.gradle.kts"
s = gradle.read_text()
require_once(s, 'versionCode = 50', 'v0.4.10 versionCode')
require_once(s, 'versionName = "0.4.10"', 'v0.4.10 versionName')
s = s.replace('versionCode = 50', 'versionCode = 51', 1)
s = s.replace('versionName = "0.4.10"', 'versionName = "0.4.11"', 1)
gradle.write_text(s)

for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.4.10", "0.4.11"))

# Websetup/Fernwartung UX recovery: if an older install is already marked
# unlocked but the embedded Tailscale backend still needs authentication, make
# the PIN action impossible to miss. On PIN_REQUIRED the dialog opens
# automatically once, and a prominent button remains visible in the status area.
web = java / "ui/V047WebAdmin.kt"
s = web.read_text()

anchor = '''    LaunchedEffect(u.remoteMaintenanceUnlocked) {\n        if (u.remoteMaintenanceUnlocked) {\n            while (true) {\n                RemoteTailscaleManager.ensureConnected()\n                delay(10_000L)\n            }\n        }\n    }\n'''
require_once(s, anchor, 'remote polling effect')
replacement = anchor + '''\n    // A migrated installation may already be marked as remote-maintenance\n    // unlocked while native Tailscale has never been authenticated. Surface\n    // the only required action immediately instead of leaving it below the\n    // fold on short TV layouts.\n    LaunchedEffect(u.remoteMaintenanceUnlocked, ts.phase) {\n        if (u.remoteMaintenanceUnlocked && ts.phase == RemoteTailscaleManager.Phase.PIN_REQUIRED) {\n            showRemoteUnlock = true\n        }\n    }\n'''
s = s.replace(anchor, replacement, 1)

old = '''                                if (ts.phase == RemoteTailscaleManager.Phase.AUTH_REQUIRED && ts.authUrl.isNotBlank()) {\n                                    Spacer(Modifier.height(6.dp))\n                                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {\n                                        ParityQrCode(ts.authUrl)\n                                        Column(Modifier.weight(1f)) {\n                                            Text("TAILSCALE ANMELDUNG", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Black)\n                                            SelectionContainer { Text(ts.authUrl, color = Color.White, fontSize = 11.sp, lineHeight = 14.sp) }\n                                            Text("QR-Code scannen und das Gerät im gleichen Tailscale-Tailnet wie den Raspberry freigeben.", color = Color.White.copy(.74f), fontSize = 10.sp, lineHeight = 13.sp)\n                                        }\n                                    }\n                                } else if (effectiveRemoteUrl.isNotBlank()) {'''
require_once(s, old, 'tailscale auth status branch')
new = '''                                if (ts.phase == RemoteTailscaleManager.Phase.PIN_REQUIRED) {\n                                    Spacer(Modifier.height(6.dp))\n                                    Button(\n                                        onClick = { showRemoteUnlock = true },\n                                        colors = ButtonDefaults.buttonColors(containerColor = accent),\n                                        shape = RoundedCornerShape(12.dp)\n                                    ) {\n                                        Icon(Icons.Default.VpnKey, null, tint = Color.Black, modifier = Modifier.size(18.dp))\n                                        Spacer(Modifier.width(7.dp))\n                                        Text("Tailscale anmelden", color = Color.Black, fontWeight = FontWeight.Black)\n                                    }\n                                } else if (ts.phase == RemoteTailscaleManager.Phase.AUTH_REQUIRED && ts.authUrl.isNotBlank()) {\n                                    Spacer(Modifier.height(6.dp))\n                                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {\n                                        ParityQrCode(ts.authUrl)\n                                        Column(Modifier.weight(1f)) {\n                                            Text("TAILSCALE ANMELDUNG", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Black)\n                                            SelectionContainer { Text(ts.authUrl, color = Color.White, fontSize = 11.sp, lineHeight = 14.sp) }\n                                            Text("QR-Code scannen und das Gerät im gleichen Tailscale-Tailnet wie den Raspberry freigeben.", color = Color.White.copy(.74f), fontSize = 10.sp, lineHeight = 13.sp)\n                                        }\n                                    }\n                                } else if (effectiveRemoteUrl.isNotBlank()) {'''
s = s.replace(old, new, 1)

# Avoid rendering a second, lower retry button for PIN_REQUIRED. ERROR keeps its
# retry action, while PIN_REQUIRED is handled by the visible button above.
old_retry = '''                                } else if (ts.phase == RemoteTailscaleManager.Phase.ERROR || ts.phase == RemoteTailscaleManager.Phase.PIN_REQUIRED) {\n                                    if (ts.lastError.isNotBlank()) Text("Status: ${ts.lastError}", color = MaterialTheme.colorScheme.error, fontSize = 10.sp)\n                                    Spacer(Modifier.height(4.dp))\n                                    OutlinedButton(onClick = { showRemoteUnlock = true }, shape = RoundedCornerShape(12.dp)) {\n                                        Icon(Icons.Default.Refresh, null, modifier = Modifier.size(17.dp))\n                                        Spacer(Modifier.width(6.dp))\n                                        Text("Einrichtung erneut starten")\n                                    }\n                                } else {'''
require_once(s, old_retry, 'lower retry branch')
new_retry = '''                                } else if (ts.phase == RemoteTailscaleManager.Phase.ERROR) {\n                                    if (ts.lastError.isNotBlank()) Text("Status: ${ts.lastError}", color = MaterialTheme.colorScheme.error, fontSize = 10.sp)\n                                    Spacer(Modifier.height(4.dp))\n                                    OutlinedButton(onClick = { showRemoteUnlock = true }, shape = RoundedCornerShape(12.dp)) {\n                                        Icon(Icons.Default.Refresh, null, modifier = Modifier.size(17.dp))\n                                        Spacer(Modifier.width(6.dp))\n                                        Text("Einrichtung erneut starten")\n                                    }\n                                } else {'''
s = s.replace(old_retry, new_retry, 1)

web.write_text(s)
print("Android v0.4.11 visible native-Tailscale login action patch applied")
