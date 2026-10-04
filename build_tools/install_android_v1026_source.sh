#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?Missing PROJECT_ROOT}"
bash build_tools/install_android_v1025_source.sh
python3 android/v1.0.26/patch_v126.py
bash build_tools/prepare_chromaprint_v126.sh
grep -Fq 'versionCode = 1026' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V126RadioKeyboard(title' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/RadioScreen.kt"
