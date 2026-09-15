#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v0412_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.13/patch_v0413.py

grep -q 'versionName = "0.4.13"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 53' "$PROJECT_ROOT/app/build.gradle.kts"
PROVISION="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
LOGIN="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/SetupCodeLogin.kt"
grep -Fq '/v1/setup/redeem' "$PROVISION"
grep -Fq '/v1/setup/redeem-token' "$PROVISION"
grep -Fq 'device_id' "$PROVISION"
grep -Fq 'Settings.Secure.ANDROID_ID' "$PROVISION"
grep -Fq 'Einrichtung wurde bereits verwendet' "$PROVISION"
grep -Fq 'Einrichtungscode ist abgelaufen' "$PROVISION"
grep -Fq 'Provisionierungsserver nicht erreichbar' "$PROVISION"
grep -Fq 'playlist_url' "$PROVISION"
grep -Fq 'session_token' "$PROVISION"
grep -Fq 'Oder mit Einrichtungscode anmelden' "$LOGIN"

echo "Android v0.4.13 device-aware setup provisioning reconstructed successfully"
