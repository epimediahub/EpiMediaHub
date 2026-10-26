#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v100_source.sh
python3 android/v1.0.1/patch_v101.py

grep -Fq 'versionCode = 1001' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.1"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'minSdk = 25' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq '"Kategorien verwalten"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
echo "Android 1.0.1 development source reconstructed successfully"
