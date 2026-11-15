#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?Missing PROJECT_ROOT}"
bash build_tools/install_android_v1027_source.sh
python3 android/v1.0.28/patch_v128.py
python3 build_tools/generate_intro_sound_v128.py "$PROJECT_ROOT/app/src/main/res/raw/epimedia_intro_heartbeat_cinema.wav"
grep -Fq 'versionCode = 1028' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'allowParentalNavigation' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'warmPlayback(context)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V112SmartTubeShell.kt"
