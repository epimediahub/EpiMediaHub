#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v050_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.5.1/patch_v051.py

grep -q 'versionName = "0.5.1"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 501' "$PROJECT_ROOT/app/build.gradle.kts"
PROVISION="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
DIALOG="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V051DashboardConnect.kt"
WEB="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V047WebAdmin.kt"
APP="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"

grep -Fq 'rawCode(raw).chunked(4).joinToString("-")' "$PROVISION"
grep -Fq 'rawCode(code).length==12' "$PROVISION"
grep -Fq 'managed-dashboard' "$PROVISION"
grep -Fq 'playlist_type' "$PROVISION"
grep -Fq 'xtream_server' "$PROVISION"
grep -Fq 'Bindestriche werden automatisch gesetzt.' "$DIALOG"
grep -Fq 'ABCD-EFGH-IJKL' "$DIALOG"
grep -Fq 'showDashboardPin = true' "$WEB"
grep -Fq 'verifyRemoteMaintenancePin' "$WEB"
grep -Fq 'SetupCodeProvisioning.sync' "$APP"
! grep -Fq 'showRemoteUnlock = true\n        }\n    }' "$WEB" || true

echo "Android v0.5.1 dashboard-link source reconstructed successfully"
