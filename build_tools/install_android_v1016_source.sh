#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"
bash build_tools/install_android_v1015_source.sh
python3 android/v1.0.16/patch_v116.py
grep -Fq 'versionCode = 1016' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.16"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V116VodPlayer(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'player.play()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V116VodPlayer.kt"
echo 'Android 1.0.16 source reconstructed successfully'
