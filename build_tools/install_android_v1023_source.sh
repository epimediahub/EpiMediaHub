#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"
bash build_tools/install_android_v1022_source.sh
python3 android/v1.0.23/patch_v123.py
grep -Fq 'versionCode = 1023' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V123AudioRenderers(context)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
test -f "$PROJECT_ROOT/ffmpeg-audio/src/main/jni/ffmpeg_jni.cc"
echo 'Android 1.0.23 audio source reconstructed successfully'
