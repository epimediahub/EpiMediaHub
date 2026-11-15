#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v064_source.sh
python3 android/hotfixes/v064_xtream_hotfix13.py

grep -Fq 'versionName = "0.6.4.13"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 616' "$PROJECT_ROOT/app/build.gradle.kts"
PROVISION="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
WORKER="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/DashboardSyncWorker.kt"
MAIN="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainActivity.kt"

grep -Fq 'const val PRODUCTION_BASE_URL = "https://setup.epimediahub.com"' "$PROVISION"
grep -Fq '/v1/device/config?version=' "$PROVISION"
grep -Fq '/v1/device/sync-result' "$PROVISION"
grep -Fq 'MANAGED_PROFILE_ID = "managed-dashboard"' "$PROVISION"
grep -Fq 'PlaylistType.XTREAM' "$PROVISION"
grep -Fq 'PlaylistType.M3U' "$PROVISION"
grep -Fq 'serverChanged || version != knownVersion || localManagedMissing' "$PROVISION"
grep -Fq 'DashboardSyncWorker.schedule(context.applicationContext)' "$PROVISION"
grep -Fq 'PeriodicWorkRequestBuilder<DashboardSyncWorker>(15, TimeUnit.MINUTES)' "$WORKER"
grep -Fq 'NetworkType.CONNECTED' "$WORKER"
grep -Fq 'DashboardSyncWorker.schedule(applicationContext)' "$MAIN"

echo "Android v0.6.4.13 source reconstructed successfully with Dashboard 0.7 automatic sync"
