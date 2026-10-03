#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"
bash build_tools/install_android_v1020_source.sh
python3 android/v1.0.21/patch_v121.py
python3 build_tools/generate_intro_sound_v121.py "$PROJECT_ROOT/app/src/main/res/raw/epimedia_intro_heartbeat_cinema.wav"
grep -Fq 'versionCode = 1021' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.21"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'setEnableComposeSurfaceSyncWorkaround(true)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V121VodSurface.kt"
grep -Fq 'The whole world' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V070Intro.kt"
echo 'Android 1.0.21 cinematic intro and VOD source reconstructed successfully'
