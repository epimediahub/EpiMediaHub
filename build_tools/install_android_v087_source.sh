#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"
bash build_tools/install_android_v086_source.sh
python3 android/v0.8.7/patch_v087.py
grep -Fq 'versionCode = 807' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "0.8.7"' "$PROJECT_ROOT/app/build.gradle.kts"
echo "Android 0.8.7 source reconstructed successfully"
