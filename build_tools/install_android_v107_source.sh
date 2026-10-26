#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v106_source.sh
python3 android/v1.0.7/patch_v107.py

grep -Fq 'versionCode = 1007' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.7"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'androidx.media3:media3-exoplayer-dash:' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'DashMediaSource.Factory(dataSource)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V106SmartTubePlayer.kt"
echo "Android 1.0.7 DASH playback source reconstructed successfully"

