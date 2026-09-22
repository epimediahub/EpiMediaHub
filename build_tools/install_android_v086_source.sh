#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"
bash build_tools/install_android_v084_source.sh
python3 android/v0.8.6/patch_v086.py
rg -q 'versionName = "0.8.6"' "$PROJECT_ROOT/app/build.gradle.kts"
rg -q 'tracks.isTypeSupported' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
echo "Android 0.8.6 source reconstructed successfully"
