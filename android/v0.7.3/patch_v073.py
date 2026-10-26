#!/usr/bin/env python3
from pathlib import Path
import os
import shutil


root = Path(os.environ.get("PROJECT_ROOT", "."))
assets = Path(__file__).resolve().parent
java = root / "app/src/main/java/de/epimediahub/app"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


# Version, shrinking, compressed native libraries and separate ARM APKs.
build = root / "app/build.gradle.kts"
s = build.read_text()
s = s.replace('versionCode = 702', 'versionCode = 703', 1)
s = s.replace('versionName = "0.7.2"', 'versionName = "0.7.3"', 1)
s = s.replace(
    '''    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
''',
    '''    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    splits {
        abi {
            isEnable = true
            reset()
            include("armeabi-v7a", "arm64-v8a")
            isUniversalApk = true
        }
    }
''',
    1,
)
s = s.replace(
    '    packaging { resources.excludes += "/META-INF/{AL2.0,LGPL2.1}" }',
    '''    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
        jniLibs.useLegacyPackaging = true
    }''',
    1,
)
s = s.replace('    implementation(files("libs/tailscale-embedded.aar"))\n', '')
s = s.replace('    implementation(files("libs/libtailscale.aar"))\n', '')
if 'versionCode = 703' not in s or 'isShrinkResources = true' not in s:
    raise SystemExit("Gradle v0.7.3 anchors missing")
build.write_text(s)
shutil.copyfile(assets / "proguard-rules.pro", root / "app/proguard-rules.pro")

home = java / "ui/V070Home.kt"
home.write_text(home.read_text().replace("0.7.2", "0.7.3"))
weather = java / "data/V070WeatherClient.kt"
if weather.exists():
    weather.write_text(weather.read_text().replace("EpiMediaHub-Android/0.7.2", "EpiMediaHub-Android/0.7.3"))


# Remove the embedded VPN. Tailscale can stay on the Raspberry only.
manifest = root / "app/src/main/AndroidManifest.xml"
s = manifest.read_text()
s = s.replace('    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_SYSTEM_EXEMPTED" />\n', '')
s = s.replace('        android:name="com.tailscale.ipn.App"\n', '')
service = '''        <service
            android:name="com.tailscale.ipn.IPNService"
            android:exported="false"
            android:foregroundServiceType="systemExempted"
            android:permission="android.permission.BIND_VPN_SERVICE">
            <intent-filter>
                <action android:name="android.net.VpnService" />
            </intent-filter>
        </service>
'''
if service not in s:
    raise SystemExit("Tailscale service manifest anchor missing")
manifest.write_text(s.replace(service, '', 1))
shutil.copyfile(assets / "MainActivity.kt", java / "MainActivity.kt")

app_file = java / "EpiMediaHubApp.kt"
s = app_file.read_text()
s = s.replace(
    'Die Wiedergabe, Fernwartung und Hintergrundaufgaben werden beendet.',
    'Die Wiedergabe und Hintergrundaufgaben werden beendet.',
)
s = s.replace('                        RemoteTailscaleManager.disconnect()\n', '')
app_file.write_text(s)

vm = java / "MainViewModel.kt"
s = vm.read_text()
s = s.replace(
    '        if (prefs.remoteMaintenanceUnlocked() || noPlaylist) startWebAdmin()\n'
    '        if (prefs.remoteMaintenanceUnlocked()) RemoteTailscaleManager.ensureConnected()\n',
    '        if (noPlaylist) startWebAdmin()\n',
    1,
)
s = s.replace(
    '            allowTailscaleRemote = { prefs.remoteMaintenanceUnlocked() },\n',
    '            allowTailscaleRemote = { false },\n',
    1,
)
s = s.replace('        RemoteTailscaleManager.provisionAndConnect(pin)\n', '')
s = s.replace('        RemoteTailscaleManager.disconnect()\n', '')
vm.write_text(s)

tailscale_manager = java / "RemoteTailscaleManager.kt"
if tailscale_manager.exists():
    tailscale_manager.unlink()


# App-scoped random install ID, HTTPS API domain and short-lived pairing.
setup = java / "data/SetupCodeProvisioning.kt"
s = setup.read_text()
s = s.replace('import android.provider.Settings\n', 'import android.os.Build\n')
s = s.replace(
    '    const val PRODUCTION_BASE_URL = "https://setup.epimediahub.com"',
    '    const val PRODUCTION_BASE_URL = "https://api.epimediahub.com"',
    1,
)
old_device_id = '''    fun deviceId(context: Context): String {
        val androidId = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ANDROID_ID
        )?.trim().orEmpty()
        if (androidId.isNotBlank() && androidId.lowercase(Locale.ROOT) != "9774d56d682e549c") {
            return "android-$androidId"
        }
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.getString(KEY_DEVICE_ID, null)?.takeIf { it.isNotBlank() }?.let { return it }
        val generated = "android-" + UUID.randomUUID().toString()
        prefs.edit().putString(KEY_DEVICE_ID, generated).commit()
        return generated
    }
'''
new_device_id = '''    fun deviceId(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.getString(KEY_DEVICE_ID, null)?.takeIf { it.isNotBlank() }?.let { return it }
        val generated = "android-" + UUID.randomUUID().toString()
        prefs.edit().putString(KEY_DEVICE_ID, generated).commit()
        return generated
    }
'''
if old_device_id not in s:
    raise SystemExit("legacy Android ID anchor missing")
s = s.replace(old_device_id, new_device_id, 1)
s = s.replace(
    '''        if (base.startsWith("https://")) return base
        // Explicit development escape hatch used by the existing Tailscale setup.
        if (base.startsWith("http://100.")) return base
        return null
''',
    '''        if (base.startsWith("https://")) return base
        return null
''',
    1,
)
s = s.replace(
    '''    fun provisioningBaseUrl(context: Context): String =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_BASE_URL, null)
            ?.takeIf { cleanBase(it) != null }
            ?: PRODUCTION_BASE_URL
''',
    '''    fun provisioningBaseUrl(context: Context): String {
        // Existing v0.7.2 session tokens remain valid on the dedicated API domain.
        return PRODUCTION_BASE_URL
    }
''',
    1,
)
s = s.replace(
    '\nobject SetupCodeProvisioning {',
    (assets / "PairingModels.kt.inc").read_text() + '\nobject SetupCodeProvisioning {',
    1,
)
s = s.replace(
    '    private const val KEY_BASE_URL = "provisioning_base_url"\n',
    '    private const val KEY_BASE_URL = "provisioning_base_url"\n'
    '    private const val KEY_PAIRING = "pending_pairing"\n',
    1,
)
s = s.replace(
    '    fun savedPayload(context: Context): JSONObject? =',
    (assets / "PairingMethods.kt.inc").read_text() + '\n    fun savedPayload(context: Context): JSONObject? =',
    1,
)
setup.write_text(s)
shutil.copyfile(assets / "V047WebAdmin.kt", java / "ui/V047WebAdmin.kt")


# From v0.7.3 forward, updates are selected by ABI from the own download domain.
updates = java / "data/UpdateManager.kt"
s = updates.read_text()
s = s.replace(
    '    // This is the same moving test-release that the Android CI pipeline updates.\n'
    '    private const val RELEASE_API_URL = "https://api.github.com/repos/epimediahub/EpiMediaHub/releases/tags/v0.7.0-test"\n',
    '    private const val MANIFEST_URL = "https://download.epimediahub.com/android/latest.json"\n',
    1,
)
s = s.replace(
    '    private const val STABLE_APK_URL = "https://github.com/epimediahub/EpiMediaHub/releases/download/v0.7.0-test/EpiMediaHub_Android_v0.7.0-test.apk"',
    '    private const val STABLE_APK_URL = "https://download.epimediahub.com/android/EpiMediaHub_Android_v0.7.0-test.apk"',
    1,
)
s = s.replace(
    '''    private fun fetchLatestInfo(): AppUpdateInfo {
        val raw = fetchJson(RELEASE_API_URL, "application/vnd.github+json")
        return parseRelease(JSONObject(raw))
    }
''',
    '''    private fun fetchLatestInfo(): AppUpdateInfo {
        val raw = fetchJson(MANIFEST_URL)
        return parseManifest(JSONObject(raw))
    }
''',
    1,
)
s = s.replace(
    '    private fun parseRelease(json: JSONObject): AppUpdateInfo {',
    (assets / "UpdateManifestParser.kt.inc").read_text()
    + '    private fun parseRelease(json: JSONObject): AppUpdateInfo {',
    1,
)
s = s.replace('error("GitHub-Weiterleitung ohne Ziel.")', 'error("Weiterleitung ohne Ziel.")')
updates.write_text(s)

local_web = java / "data/LocalWebAdmin.kt"
s = local_web.read_text()
s = s.replace(
    'Playlist-Verwaltung · lokal mit Websetup-PIN · Fernwartung nach separater Fernwartungs-PIN über Tailscale',
    'Playlist-Verwaltung · sicher im lokalen Heimnetz mit Websetup-PIN',
)
s = s.replace('Lokales Websetup: PIN aus der App (über Tailscale nicht nötig)', 'Websetup-PIN aus der App')
local_web.write_text(s)


checks = {
    build: ['versionName = "0.7.3"', 'isShrinkResources = true', 'include("armeabi-v7a", "arm64-v8a")'],
    manifest: ['android:name=".MainActivity"'],
    setup: ['https://api.epimediahub.com', 'fun startPairing(', 'UUID.randomUUID()'],
    updates: ['https://download.epimediahub.com/android/latest.json', 'Build.SUPPORTED_ABIS'],
    java / "ui/V047WebAdmin.kt": ['Kopplungscode erzeugen', 'PairingPollResult.Connected'],
}
for path, markers in checks.items():
    text = path.read_text()
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"missing v0.7.3 marker {marker} in {path}")
if "tailscale-embedded.aar" in build.read_text() or "com.tailscale" in manifest.read_text():
    raise SystemExit("embedded Tailscale references remain in Android build")

print("Android v0.7.3 domain pairing, updater and slim ARM builds applied")
