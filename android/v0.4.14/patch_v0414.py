#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"

gradle = root / "app/build.gradle.kts"
s = gradle.read_text()
if 'versionCode = 53' not in s or 'versionName = "0.4.13"' not in s:
    raise SystemExit("v0.4.13 version anchors missing")
gradle.write_text(s.replace('versionCode = 53','versionCode = 54',1).replace('versionName = "0.4.13"','versionName = "0.4.14"',1))
for rel in ["ui/V044Home.kt","ui/Screens.kt","data/MediathekClient.kt"]:
    p=java/rel
    if p.exists(): p.write_text(p.read_text().replace("0.4.13","0.4.14"))

# Run provisioning sync whenever the Android process starts. A ContentProvider is
# intentionally used as a tiny app-start hook so this also works on Fire TV
# without depending on a particular Compose screen being opened first.
(java/"data/ProvisioningInitProvider.kt").write_text(r'''package de.epimediahub.app.data

import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.net.Uri
import kotlin.concurrent.thread

class ProvisioningInitProvider : ContentProvider() {
    override fun onCreate(): Boolean {
        val app = context?.applicationContext ?: return true
        thread(name = "epimediahub-device-sync", isDaemon = true) {
            if (SetupCodeProvisioning.sessionToken(app) != null) {
                SetupCodeProvisioning.sync(app)
            }
        }
        return true
    }
    override fun query(uri: Uri, projection: Array<out String>?, selection: String?, selectionArgs: Array<out String>?, sortOrder: String?): Cursor? = null
    override fun getType(uri: Uri): String? = null
    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int = 0
    override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<out String>?): Int = 0
}
''')

manifest = root / "app/src/main/AndroidManifest.xml"
ms = manifest.read_text()
provider = '''        <provider\n            android:name="de.epimediahub.app.data.ProvisioningInitProvider"\n            android:authorities="${applicationId}.provisioning-init"\n            android:exported="false"\n            android:initOrder="100" />\n'''
if '${applicationId}.provisioning-init' not in ms:
    if '</application>' not in ms: raise SystemExit('AndroidManifest application anchor missing')
    ms = ms.replace('</application>', provider + '    </application>', 1)
manifest.write_text(ms)

# After a setup code is redeemed, immediately perform the first authenticated
# config sync. This updates last_seen/config state before the user leaves setup.
prov = java / "data/SetupCodeProvisioning.kt"
ps = prov.read_text()
old = 'SetupCodeResult.Success(payload)};404->'
new = 'runCatching{sync(context)};SetupCodeResult.Success(payload)};404->'
if old not in ps: raise SystemExit('redeem success anchor missing')
ps = ps.replace(old, new, 1)
prov.write_text(ps)

print("Android v0.4.14 automatic device sync installed")
