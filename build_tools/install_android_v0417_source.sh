#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v0416_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.17/patch_v0417.py

grep -q 'versionName = "0.4.17"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 57' "$PROJECT_ROOT/app/build.gradle.kts"
GATE="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ProvisioningGateActivity.kt"
MANIFEST="$PROJECT_ROOT/app/src/main/AndroidManifest.xml"
UPDATER="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"

grep -Fq 'https://epimedia.tail58077d.ts.net' "$GATE"
grep -Fq 'android.permission.REQUEST_INSTALL_PACKAGES' "$MANIFEST"
grep -Fq 'canRequestPackageInstalls()' "$UPDATER"
grep -Fq 'ACTION_MANAGE_UNKNOWN_APP_SOURCES' "$UPDATER"
grep -Fq 'ACTION_SECURITY_SETTINGS' "$UPDATER"
grep -Fq '${applicationId}.fileprovider' "$MANIFEST"
grep -Fq 'FLAG_GRANT_READ_URI_PERMISSION' "$UPDATER"
grep -Fq 'candidates.maxByOrNull { it.second.versionCode }' "$UPDATER"

echo "Android v0.4.17 public provisioning and updater permission reconstructed successfully"
