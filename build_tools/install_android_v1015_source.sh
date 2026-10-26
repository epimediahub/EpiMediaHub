#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"
bash build_tools/install_android_v1014_source.sh
python3 android/v1.0.15/patch_v115.py
grep -Fq 'versionCode = 1015' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.15"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V115VodPlayer(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'FOCUS_BLOCK_DESCENDANTS' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V115VodPlayer.kt"
grep -Fq 'list_versions=true' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/V115SkipRepository.kt"
echo 'Android 1.0.15 source reconstructed successfully'
