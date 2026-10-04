#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?Missing PROJECT_ROOT}"
bash build_tools/install_android_v1026_source.sh
python3 android/v1.0.27/patch_v127.py
python3 build_tools/generate_intro_sound_v127.py "$PROJECT_ROOT/app/src/main/res/raw/epimedia_intro_heartbeat_cinema.wav"
grep -Fq 'versionCode = 1027' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'val focusSegment = active.firstOrNull' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V115PlayerChrome.kt"
grep -Fq 'focusProgress.value' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
