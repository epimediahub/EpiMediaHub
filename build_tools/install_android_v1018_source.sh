#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"
bash build_tools/install_android_v1017_source.sh
python3 android/v1.0.18/patch_v118.py
grep -Fq 'versionCode = 1018' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.18"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'v118NextWindow(state.durationMs)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V115PlayerChrome.kt"
grep -Fq 'V118Names.subtitle(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V115PlayerChrome.kt"
grep -Fq '.focusRequester(nextCardFocus)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V115PlayerChrome.kt"
echo 'Android 1.0.18 source reconstructed successfully'
