#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v1011_source.sh
python3 android/v1.0.12/patch_v112.py

grep -Fq 'versionCode = 1012' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.12"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V112SmartTubeShell(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V083Home.kt"
grep -Fq 'rememberV112PlaylistHealth(u.playlists)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V070Playlists.kt"
grep -Fq 'V112PlaylistStatusLight(status)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V070Playlists.kt"
grep -Fq 'V112SmartTubeWatchHistory.mark' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V112SmartTubeShell.kt"
if grep -Fq 'getShortsObserve' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V108SmartTubeCore.kt"; then
  exit 1
fi
echo "Android 1.0.12 source reconstructed successfully"
