#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v0412_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.13/patch_v0413.py

grep -q 'versionName = "0.4.13"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 53' "$PROJECT_ROOT/app/build.gradle.kts"
PROVISION="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
LOGIN="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/SetupCodeLogin.kt"
MANIFEST="$PROJECT_ROOT/app/src/main/AndroidManifest.xml"
PATHS="$PROJECT_ROOT/app/src/main/res/xml/epimediahub_file_paths.xml"
grep -Fq '/v1/setup/redeem' "$PROVISION"
grep -Fq '/v1/setup/redeem-token' "$PROVISION"
grep -Fq '/v1/device/config' "$PROVISION"
grep -Fq '/v1/device/sync-result' "$PROVISION"
grep -Fq 'stable_device_id' "$PROVISION"
grep -Fq 'UUID.randomUUID()' "$PROVISION"
grep -Fq 'Settings.Secure.ANDROID_ID' "$PROVISION"
grep -Fq 'device_id' "$PROVISION"
grep -Fq 'playlist_url' "$PROVISION"
grep -Fq 'session_token' "$PROVISION"
grep -Fq 'Oder mit Einrichtungscode anmelden' "$LOGIN"
grep -Fq '${applicationId}.fileprovider' "$MANIFEST"
grep -Fq 'android.support.FILE_PROVIDER_PATHS' "$MANIFEST"
grep -Fq '@xml/epimediahub_file_paths' "$MANIFEST"
grep -Fq 'external-files-path' "$PATHS"
grep -Fq 'path="Download/"' "$PATHS"
grep -Fq 'FLAG_GRANT_READ_URI_PERMISSION' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"

echo "Android v0.4.13 provisioning, config sync and FileProvider updater fix reconstructed successfully"
