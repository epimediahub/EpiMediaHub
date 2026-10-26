#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"
bash build_tools/install_android_v094_source.sh
python3 android/v0.9.5/patch_v095.py
grep -Fq 'versionCode = 905' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "0.9.5"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'alpha = .46f' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Common.kt"
grep -Fq '.graphicsLayer { alpha = .30f }' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Common.kt"
echo "Android 0.9.5 source reconstructed successfully"
