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
if text.count("dependencies {") != 1 or "coreLibraryDesugaringEnabled = true" not in text:
    raise SystemExit("Refusing: unsupported Gradle configuration (desugaring must be enabled)")
new_gradle = text.replace("dependencies {", "dependencies {\n"+dep, 1)
if 'coreLibraryDesugaring(' not in new_gradle:
    new_gradle = new_gradle.replace('dependencies {\n'+dep,
        'dependencies {\n'+dep+'    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.0.4")\n',1)

service = '''        <!-- WireGuard internal beta: Android user consent required, no auto-connect. -->
        <service
            android:name="com.wireguard.android.backend.GoBackend$VpnService"
            android:permission="android.permission.BIND_VPN_SERVICE"
            android:exported="true">
            <intent-filter>
                <action android:name="android.net.VpnService" />
            </intent-filter>
        </service>
'''
xml = manifest.read_text()
if "GoBackend$VpnService" in xml:
    raise SystemExit("Refusing: VPN service already configured")
if xml.count("</application>") != 1:
    raise SystemExit("Refusing: unexpected Manifest structure")
new_manifest = xml.replace("</application>",service+"    </application>",1)
files = [
    (src/"V134VpnRoutingPolicy.kt",java/"V134VpnRoutingPolicy.kt"),
    (src/"V134WireGuardDeviceTunnel.kt",java/"V134WireGuardDeviceTunnel.kt"),
    (src/"V134VpnRoutingPolicyTest.kt",
        root/"app/src/test/java/de/epimediahub/app/vpn/V134VpnRoutingPolicyTest.kt"),
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
