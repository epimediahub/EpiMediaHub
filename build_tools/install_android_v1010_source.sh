#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v109_source.sh
python3 android/v1.0.10/patch_v1010.py
python3 android/v1.0.10/patch_global_search_v1010.py

grep -Fq 'versionCode = 1010' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.10"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V110SmartTubeShell(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V083Home.kt"
grep -Fq 'V110TvKeyboardDialog(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V110SmartTubeShell.kt"
grep -Fq 'Player.STATE_ENDED' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V110SmartTubePlayer.kt"
grep -Fq 'onPreviewKeyEvent' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V110SmartTubePlayer.kt"
grep -Fq 'V110TvKeyboardDialog(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V035Screens.kt"

echo "Android 1.0.10 development source reconstructed successfully"
