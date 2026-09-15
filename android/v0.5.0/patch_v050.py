#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"

# Move the already validated v0.4.13 source to the first production provisioning release.
gradle = root / "app/build.gradle.kts"
s = gradle.read_text()
if 'versionCode = 53' not in s or 'versionName = "0.4.13"' not in s:
    raise SystemExit("v0.4.13 version anchors missing")
s = s.replace('versionCode = 53', 'versionCode = 500', 1)
s = s.replace('versionName = "0.4.13"', 'versionName = "0.5.0"', 1)
gradle.write_text(s)

for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.4.13", "0.5.0"))

# Pin normal Internet provisioning to the production domain. A direct Tailscale
# 100.x URL remains available as an explicit service/debug escape hatch.
provision = java / "data/SetupCodeProvisioning.kt"
s = provision.read_text()
anchor = 'object SetupCodeProvisioning {\n private const val PREFS="epimediahub_provisioning";'
if anchor not in s:
    raise SystemExit("SetupCodeProvisioning object anchor missing")
s = s.replace(
    anchor,
    'object SetupCodeProvisioning {\n const val PRODUCTION_BASE_URL="https://setup.epimediahub.com"\n private const val PREFS="epimediahub_provisioning";',
    1,
)
old = ''' private fun post(context:Context,baseUrl:String,path:String,key:String,value:String):SetupCodeResult {\n  if(!baseUrl.startsWith("https://") && !baseUrl.startsWith("http://100.")) return SetupCodeResult.Error("Provisionierungsserver nicht sicher konfiguriert")\n  return try {\n   val cleanBase=baseUrl.trimEnd('/'); val conn=connection(cleanBase+path,"POST")'''
new = ''' private fun post(context:Context,baseUrl:String,path:String,key:String,value:String):SetupCodeResult {\n  val requested=baseUrl.trimEnd('/')\n  val cleanBase=if(requested.startsWith("http://100.")) requested else PRODUCTION_BASE_URL\n  return try {\n   val conn=connection(cleanBase+path,"POST")'''
if old not in s:
    raise SystemExit("provisioning post anchor missing")
s = s.replace(old, new, 1)
old = ' fun provisioningBaseUrl(context:Context):String?=context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getString(KEY_BASE_URL,null)?.takeIf{it.isNotBlank()}'
new = ' fun provisioningBaseUrl(context:Context):String=context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getString(KEY_BASE_URL,null)?.takeIf{it.isNotBlank()}?:PRODUCTION_BASE_URL'
if old not in s:
    raise SystemExit("provisioning base URL anchor missing")
s = s.replace(old, new, 1)
provision.write_text(s)

# Default the setup-code UI to the production endpoint while keeping the
# parameter for backwards/source compatibility with any existing caller.
login = java / "ui/SetupCodeLogin.kt"
s = login.read_text()
old = '@Composable fun SetupCodeLogin(provisioningBaseUrl:String,onProvisioned:()->Unit,modifier:Modifier=Modifier)'
new = '@Composable fun SetupCodeLogin(provisioningBaseUrl:String=SetupCodeProvisioning.PRODUCTION_BASE_URL,onProvisioned:()->Unit,modifier:Modifier=Modifier)'
if old not in s:
    raise SystemExit("SetupCodeLogin signature anchor missing")
login.write_text(s.replace(old, new, 1))

# v0.5.0 starts a monotonic semantic versionCode scheme (0.5.0 -> 500,
# 0.5.1 -> 501). This keeps the release-API updater fallback consistent with
# BuildConfig.VERSION_CODE and avoids 0.5.0 being interpreted as code 50.
update = java / "data/UpdateManager.kt"
s = update.read_text()
old = '''        // Existing EpiMediaHub versionCode scheme: 0.3.6 -> 36, 0.4.12 -> 52.\n        return if (parts[0] == 0) parts[1] * 10 + parts[2]\n        else parts[0] * 10000 + parts[1] * 100 + parts[2]'''
new = '''        // Since v0.5.0 use a monotonic semantic scheme: 0.5.0 -> 500, 0.5.1 -> 501.\n        return if (parts[0] == 0) parts[1] * 100 + parts[2]\n        else parts[0] * 10000 + parts[1] * 100 + parts[2]'''
if old not in s:
    raise SystemExit("UpdateManager versionCodeFrom anchor missing")
update.write_text(s.replace(old, new, 1))

print("Android v0.5.0 production domain and versioning patch applied")
