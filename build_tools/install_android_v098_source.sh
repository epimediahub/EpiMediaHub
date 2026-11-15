#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"
bash build_tools/install_android_v097_source.sh
python3 android/v0.9.8/patch_v098.py
grep -Fq 'versionCode = 908' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "0.9.8"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V097SkinWorld.LUXURY' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V097SkinEnvironment.kt"
grep -Fq 'val epgHeight = if (isTv) 43.dp else 52.dp' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V076LiveTv.kt"
grep -Fq 'val activeSkinMark = remember(u.themeId)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V076LiveTv.kt"
echo "Android 0.9.8 source reconstructed successfully"
