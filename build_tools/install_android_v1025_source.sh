#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"
bash build_tools/install_android_v1024_source.sh
python3 android/v1.0.25/patch_v125.py
grep -Fq 'versionCode = 1025' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'allowEmpty = true' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/RadioScreen.kt"
echo 'Android 1.0.25 radio and skip support source reconstructed successfully'
