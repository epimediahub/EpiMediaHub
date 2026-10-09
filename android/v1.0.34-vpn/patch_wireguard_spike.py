#!/usr/bin/env python3
"""Opt-in VPN integration *spike* for reconstructed Android v1.0.33 source.

No user-facing toggle, no automatic connection, no payment features.
Intended for a separate test build only; does not publish an APK.
"""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"]).resolve(strict=True)
src = Path(__file__).resolve().parent
gradle = root / "app/build.gradle.kts"
manifest = root / "app/src/main/AndroidManifest.xml"
java = root / "app/src/main/java/de/epimediahub/app/vpn"

if not gradle.is_file() or 'versionName = "1.0.33"' not in gradle.read_text():
    raise SystemExit("Refusing: expected reconstructed Android 1.0.33")
if not manifest.is_file() or "</application>" not in manifest.read_text():
    raise SystemExit("Refusing: unsupported AndroidManifest.xml")
if (src/"V134WireGuardDeviceTunnel.kt").stat().st_size < 100:
    raise SystemExit("Refusing: WireGuard bridge not present")

dep = '    implementation("com.wireguard.android:tunnel:1.0.20260102")\n'
text = gradle.read_text()
if "com.wireguard.android:tunnel" in text:
    raise SystemExit("Refusing: tunnel dependency is already configured")
if text.count("dependencies {") != 1:
    raise SystemExit("Refusing: unsupported dependencies configuration")
new_gradle = text.replace("dependencies {", "dependencies {\n"+dep, 1)
if 'coreLibraryDesugaring(' not in new_gradle:
    new_gradle = new_gradle.replace('dependencies {\n'+dep,
        'dependencies {\n'+dep+'    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.0.4")\n',1)
if "isCoreLibraryDesugaringEnabled = true" not in new_gradle and "coreLibraryDesugaringEnabled = true" not in new_gradle:
    if new_gradle.count("compileOptions {") != 1:
        raise SystemExit("Refusing: unknown compileOptions setup")
    new_gradle = new_gradle.replace("compileOptions {",
        "compileOptions {\n        isCoreLibraryDesugaringEnabled = true", 1)
if new_gradle.count("versionCode = 1033") != 1 or new_gradle.count('versionName = "1.0.33"') != 1:
    raise SystemExit("Refusing: expected 1.0.33 version")
new_gradle = new_gradle.replace("versionCode = 1033", "versionCode = 1046", 1)
new_gradle = new_gradle.replace('versionName = "1.0.33"', 'versionName = "1.0.46"', 1)
# This beta MUST install beside the user's daily production app.
import re
matches = re.findall(r'applicationId\s*=\s*"([^"]+)"', new_gradle)
if len(matches) != 1:
    raise SystemExit("Refusing: cannot reliably locate exactly one Android applicationId")
production_id = matches[0]
if production_id != "de.epimediahub.app":
    raise SystemExit("Refusing: unexpected production applicationId " + production_id)
# Official QA is a signed in-place upgrade of the registered app; the
# isolated test variant remains available for destructive experiments.
OFFICIAL_CANDIDATE = os.environ.get("EPIMEDIAHUB_OFFICIAL_CANDIDATE") == "1"
new_id = "de.epimediahub.app" if OFFICIAL_CANDIDATE else "de.epimediahub.app.vpnbeta"
new_gradle = re.sub(r'applicationId\s*=\s*"[^"]+"',
                    f'applicationId = "{new_id}"', new_gradle, count=1)


service = '''        <!-- WireGuard internal beta: Android user consent required, no auto-connect. -->
        <service
            android:name="com.wireguard.android.backend.GoBackend$VpnService"
            android:permission="android.permission.BIND_VPN_SERVICE"
            android:exported="false">
            <intent-filter>
                <action android:name="android.net.VpnService" />
            </intent-filter>
        </service>
'''
xml = manifest.read_text()
# Keep EpiMediaHub's regular MainActivity as the ONLY TV/phone launcher.
# A diagnostic activity may be opened from Settings, never stacked as home.
xml = manifest.read_text()
if not 1 <= xml.count('android.intent.action.MAIN') <= 3:
    raise SystemExit("Refusing: MainActivity launcher intent filters missing")
beta_settings = """        <activity
            android:name="de.epimediahub.app.vpn.V134VpnDiagnosticActivity"
            android:label="VPN Diagnose"
            android:exported="false" />
"""
if "V134VpnDiagnosticActivity" in xml:
    raise SystemExit("Refusing: VPN diagnostic activity already exists")
xml = xml.replace("</application>", beta_settings + "    </application>", 1)
if "GoBackend$VpnService" in xml:
    raise SystemExit("Refusing: VPN service already configured")
if xml.count("</application>") != 1:
    raise SystemExit("Refusing: unexpected Manifest structure")
new_manifest = xml.replace("</application>",service+"    </application>",1)
files = [
    (src/"V134VpnRoutingPolicy.kt",java/"V134VpnRoutingPolicy.kt"),
    (src/"V134WireGuardDeviceTunnel.kt",java/"V134WireGuardDeviceTunnel.kt"),
    (src/"V134VpnDiagnosticActivity.kt",java/"V134VpnDiagnosticActivity.kt"),
    (src/"V141VpnSettings.kt",java/"V141VpnSettings.kt"),
    (src/"V142VpnPrivateKeyStore.kt",java/"V142VpnPrivateKeyStore.kt"),
    (src/"V142VpnAutoProvision.kt",java/"V142VpnAutoProvision.kt"),
    (src/"V134VpnSession.kt",java/"V134VpnSession.kt"),
    (src/"V139VpnEncryptedProfileStore.kt",java/"V139VpnEncryptedProfileStore.kt"),
    (src/"V134VpnRouteUi.kt",java/"V134VpnRouteUi.kt"),
    (src/"V140SpeedTest.kt",java/"V140SpeedTest.kt"),
    (src/"V140SpeedTransfer.kt",java/"V140SpeedTransfer.kt"),
    (src/"V144GigabitTransfer.kt",java/"V144GigabitTransfer.kt"),
    (src/"V140VpnLossMonitor.kt",java/"V140VpnLossMonitor.kt"),
    (src/"V134VpnRoutingPolicyTest.kt",
        root/"app/src/test/java/de/epimediahub/app/vpn/V134VpnRoutingPolicyTest.kt"),
    (src/"V140SpeedTransferTest.kt",
        root/"app/src/test/java/de/epimediahub/app/vpn/V140SpeedTransferTest.kt"),
    (src/"V140VpnLossMonitorTest.kt",
        root/"app/src/test/java/de/epimediahub/app/vpn/V140VpnLossMonitorTest.kt"),
]
for old, new in files:
    if not old.is_file() or new.exists():
        raise SystemExit(f"Refusing: source absent or destination already exists: {old} / {new}")
for old, new in files:
    new.parent.mkdir(parents=True,exist_ok=True)
    new.write_bytes(old.read_bytes())
gradle.write_text(new_gradle)
manifest.write_text(new_manifest)
print("Added dormant app-only WireGuard bridge to Android v1.0.33 test source.")
print("No VPN starts without explicit Android consent and a valid device configuration.")
print("No playback integration, release APK, or production changes were made.")
