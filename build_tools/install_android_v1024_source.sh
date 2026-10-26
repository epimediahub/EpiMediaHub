#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"
bash build_tools/install_android_v1023_source.sh
python3 android/v1.0.24/patch_v124.py
grep -Fq 'versionCode = 1024' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V124SmartTubeBrowseLayer(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V112SmartTubePlayer.kt"
grep -Fq 'getMetadataObserve(videoId)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V108SmartTubeCore.kt"
echo 'Android 1.0.24 SmartTube source reconstructed successfully'
