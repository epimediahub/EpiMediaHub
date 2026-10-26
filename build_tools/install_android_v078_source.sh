#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"
bash build_tools/install_android_v077_source.sh
python3 android/v0.7.8/patch_v078.py
grep -Fq 'versionName = "0.7.8"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 708' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'fun V078DashboardPairingGate' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V078DashboardPairingGate.kt"
grep -Fq 'if (!dashboardPaired)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"
echo "Android v0.7.8 source reconstructed successfully"
