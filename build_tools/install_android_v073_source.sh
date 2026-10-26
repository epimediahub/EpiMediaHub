#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v072_source.sh
python3 android/v0.7.3/patch_v073.py

grep -Fq 'versionName = "0.7.3"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 703' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'isShrinkResources = true' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'include("armeabi-v7a", "arm64-v8a")' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'https://api.epimediahub.com' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
grep -Fq 'https://download.epimediahub.com/android/latest.json' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"
grep -Fq 'fun startPairing(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
test ! -e "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"
! grep -Rq 'com.tailscale' "$PROJECT_ROOT/app/src/main"

echo "Android v0.7.3 source reconstructed successfully"
