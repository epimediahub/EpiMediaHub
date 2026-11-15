#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"
bash build_tools/install_android_v093_source.sh
python3 android/v0.9.4/patch_v094.py
grep -Fq 'versionCode = 904' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "0.9.4"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'val watermark = remember(themeId)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Common.kt"
grep -Fq '.graphicsLayer { alpha = .11f }' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Common.kt"
! grep -Fq 'val skinMotif = remember(u.themeId)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V083Home.kt"
echo "Android 0.9.4 source reconstructed successfully"
