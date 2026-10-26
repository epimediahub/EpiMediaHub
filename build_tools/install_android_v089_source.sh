#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"
bash build_tools/install_android_v088_source.sh
python3 android/v0.8.9/patch_v089.py
grep -Fq 'versionCode = 809' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "0.8.9"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'keepAwakeView.keepScreenOn = true' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
echo "Android 0.8.9 source reconstructed successfully"
