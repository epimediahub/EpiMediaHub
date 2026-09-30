#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v105_source.sh
python3 android/v1.0.6/patch_v106.py

grep -Fq 'versionCode = 1006' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.6"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V106SmartTubePlayer(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V104SmartTubeShell.kt"
grep -Fq 'DefaultDataSource.Factory(context, http)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V106SmartTubePlayer.kt"
echo "Android 1.0.6 development source reconstructed successfully"
