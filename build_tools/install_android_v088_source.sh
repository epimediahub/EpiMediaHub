#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"
bash build_tools/install_android_v087_source.sh
python3 android/v0.8.8/patch_v088.py
grep -Fq 'versionCode = 808' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "0.8.8"' "$PROJECT_ROOT/app/build.gradle.kts"
echo "Android 0.8.8 source reconstructed successfully"
