#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v0413_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.14/patch_v0414.py

grep -q 'versionName = "0.4.14"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 54' "$PROJECT_ROOT/app/build.gradle.kts"
PROVISION="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
STARTUP="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/ProvisioningInitProvider.kt"
MANIFEST="$PROJECT_ROOT/app/src/main/AndroidManifest.xml"
grep -Fq 'runCatching{sync(context)}' "$PROVISION"
grep -Fq 'SetupCodeProvisioning.sessionToken(app)' "$STARTUP"
grep -Fq 'SetupCodeProvisioning.sync(app)' "$STARTUP"
grep -Fq '${applicationId}.provisioning-init' "$MANIFEST"
grep -Fq 'android:initOrder="100"' "$MANIFEST"
# Preserve the repaired in-app APK installer from 0.4.13.
grep -Fq '${applicationId}.fileprovider' "$MANIFEST"
grep -Fq 'FLAG_GRANT_READ_URI_PERMISSION' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"

echo "Android v0.4.14 startup/immediate device sync reconstructed successfully"
