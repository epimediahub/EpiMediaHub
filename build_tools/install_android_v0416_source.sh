#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v0415_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.16/patch_v0416.py

grep -q 'versionName = "0.4.16"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 56' "$PROJECT_ROOT/app/build.gradle.kts"
GATE="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ProvisioningGateActivity.kt"
MANIFEST="$PROJECT_ROOT/app/src/main/AndroidManifest.xml"
PROVISION="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"

test -f "$GATE"
grep -Fq 'EpiMediaHub verbinden' "$GATE"
grep -Fq 'SetupCodeProvisioning.redeem' "$GATE"
grep -Fq 'SetupCodeProvisioning.sync' "$GATE"
grep -Fq 'http://100.96.157.82:8787' "$GATE"
grep -Fq 'de.epimediahub.app.ProvisioningGateActivity' "$MANIFEST"
grep -Fq 'android.intent.action.MAIN' "$MANIFEST"
grep -Fq 'usesCleartextTraffic="true"' "$MANIFEST"
grep -Fq '/v1/setup/redeem' "$PROVISION"
grep -Fq '/v1/device/config' "$PROVISION"
grep -Fq 'session_token' "$PROVISION"
# Preserve updater + startup sync fixes.
grep -Fq '${applicationId}.fileprovider' "$MANIFEST"
grep -Fq '${applicationId}.provisioning-init' "$MANIFEST"
grep -Fq 'candidates.maxByOrNull { it.second.versionCode }' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"

echo "Android v0.4.16 provisioning gate reconstructed successfully"
