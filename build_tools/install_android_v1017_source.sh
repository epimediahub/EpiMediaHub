#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"
bash build_tools/install_android_v1016_source.sh
python3 android/v1.0.17/patch_v117.py
grep -Fq 'versionCode = 1017' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.17"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'v117NextWindow(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V115PlayerChrome.kt"
grep -Fq 'vod-settings-actions' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V115PlayerChrome.kt"
grep -Fq 'Color(0xF50B111C)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
echo 'Android 1.0.17 source reconstructed successfully'
