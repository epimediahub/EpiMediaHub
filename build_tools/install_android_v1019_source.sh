#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"
bash build_tools/install_android_v1018_source.sh
python3 android/v1.0.19/patch_v119.py
grep -Fq 'versionCode = 1019' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.19"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'RadioHomeActions(showPlaylistSwitch' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V083Home.kt"
grep -Fq 'foregroundServiceType="mediaPlayback"' "$PROJECT_ROOT/app/src/main/AndroidManifest.xml"
echo 'Android 1.0.19 international radio source reconstructed successfully'
