#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v104_source.sh
python3 android/v1.0.5/patch_v105.py

grep -Fq 'versionCode = 1005' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.5"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'minSdk = 25' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V105SmartTubeCore.resolvePlayback' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V104SmartTubeShell.kt"
grep -Fq 'EpiMediaPlaybackBridge.getMedia3CompatibleFormatInfo' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V105SmartTubeCore.kt"
grep -Fq 'fun getMedia3CompatibleFormatInfo(' "$PROJECT_ROOT/.smarttube/MediaServiceCore/youtubeapi/src/main/java/com/liskovsoft/youtubeapi/service/internal/FormatInfoWrapper.kt"
echo "Android 1.0.5 development source reconstructed successfully"
