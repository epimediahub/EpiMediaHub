#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v0413_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.5.0/patch_v050.py

grep -q 'versionName = "0.5.0"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 500' "$PROJECT_ROOT/app/build.gradle.kts"
PROVISION="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
LOGIN="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/SetupCodeLogin.kt"
UPDATER="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"
grep -Fq 'https://setup.epimediahub.com' "$PROVISION"
grep -Fq 'PRODUCTION_BASE_URL' "$PROVISION"
grep -Fq 'PRODUCTION_BASE_URL' "$LOGIN"
grep -Fq 'parts[1] * 100 + parts[2]' "$UPDATER"
grep -Fq '/v1/setup/redeem' "$PROVISION"
grep -Fq '/v1/setup/redeem-token' "$PROVISION"
grep -Fq '/v1/device/config' "$PROVISION"
grep -Fq 'session_token' "$PROVISION"
grep -Fq 'playlist_url' "$PROVISION"

echo "Android v0.5.0 production source reconstructed successfully"
