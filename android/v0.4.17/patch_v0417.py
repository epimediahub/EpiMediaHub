#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"
gradle = root / "app/build.gradle.kts"

s = gradle.read_text()
if 'versionCode = 56' not in s or 'versionName = "0.4.16"' not in s:
    raise SystemExit("v0.4.16 version anchors missing")
gradle.write_text(
    s.replace('versionCode = 56', 'versionCode = 57', 1)
     .replace('versionName = "0.4.16"', 'versionName = "0.4.17"', 1)
)
for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.4.16", "0.4.17"))

# Public HTTPS provisioning endpoint exposed through the restricted Raspberry
# gateway + Tailscale Funnel. The admin UI itself remains Tailnet-only.
gate = java / "ProvisioningGateActivity.kt"
g = gate.read_text()
old_server = 'private const val DEFAULT_SERVER = "http://100.96.157.82:8787"'
new_server = 'private const val DEFAULT_SERVER = "https://epimedia.tail58077d.ts.net"'
if old_server not in g:
    raise SystemExit("v0.4.16 provisioning server anchor missing")
g = g.replace(old_server, new_server, 1)
gate.write_text(g)

# Fire TV / Android requires per-app permission before a sideloaded app can
# launch the package installer. Declare REQUEST_INSTALL_PACKAGES and route the
# user to the exact system permission page instead of silently stopping after
# download/hash verification.
manifest = root / "app/src/main/AndroidManifest.xml"
m = manifest.read_text()
perm = '<uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />'
if perm not in m:
    app_anchor = '<application'
    if app_anchor not in m:
        raise SystemExit("AndroidManifest application anchor missing")
    m = m.replace(app_anchor, perm + '\n    ' + app_anchor, 1)
manifest.write_text(m)

manager = java / "data/UpdateManager.kt"
u = manager.read_text()
imports_anchor = 'import android.content.Intent\n'
extra_imports = (
    'import android.net.Uri\n'
    'import android.os.Build\n'
    'import android.provider.Settings\n'
    'import android.widget.Toast\n'
)
if 'import android.provider.Settings' not in u:
    if imports_anchor not in u:
        raise SystemExit("UpdateManager import anchor missing")
    u = u.replace(imports_anchor, imports_anchor + extra_imports, 1)

old = '''    fun installApk(context: Context, apk: File) {\n        val uri = FileProvider.getUriForFile(\n            context,\n            "${context.packageName}.fileprovider",\n            apk\n        )\n        val intent = Intent(Intent.ACTION_VIEW).apply {\n            setDataAndType(uri, "application/vnd.android.package-archive")\n            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)\n            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)\n        }\n        context.startActivity(intent)\n    }'''
new = '''    fun installApk(context: Context, apk: File) {\n        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&\n            !context.packageManager.canRequestPackageInstalls()) {\n            Toast.makeText(\n                context,\n                "Bitte EpiMediaHub das Installieren unbekannter Apps erlauben und danach Update erneut starten.",\n                Toast.LENGTH_LONG\n            ).show()\n            val packageUri = Uri.parse("package:${context.packageName}")\n            val settingsIntent = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, packageUri).apply {\n                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)\n            }\n            runCatching { context.startActivity(settingsIntent) }\n                .onFailure {\n                    context.startActivity(\n                        Intent(Settings.ACTION_SECURITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)\n                    )\n                }\n            return\n        }\n\n        val uri = FileProvider.getUriForFile(\n            context,\n            "${context.packageName}.fileprovider",\n            apk\n        )\n        val intent = Intent(Intent.ACTION_VIEW).apply {\n            setDataAndType(uri, "application/vnd.android.package-archive")\n            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)\n            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)\n        }\n        context.startActivity(intent)\n    }'''
if old not in u:
    raise SystemExit("UpdateManager installApk anchor missing")
u = u.replace(old, new, 1)
manager.write_text(u)

print("Android v0.4.17 public provisioning + Fire TV updater permission patch applied")
