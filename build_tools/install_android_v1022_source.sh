#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"
bash build_tools/install_android_v1021_source.sh
python3 android/v1.0.22/patch_v122.py
grep -Fq 'versionCode = 1022' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.22"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V121VodSurface(player, isTv, Modifier.fillMaxSize())' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'setVideoFrameMetadataListener(metadata)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V121VodSurface.kt"
echo 'Android 1.0.22 live TV and VOD playback source reconstructed successfully'
