#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v101_source.sh
python3 android/v1.0.2/patch_v102.py

grep -Fq 'versionCode = 1002' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.2"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'minSdk = 25' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'SmartTube-Core:' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V100SmartTubeCore.kt"
grep -Fq -- '-keep class com.liskovsoft.** { *; }' "$PROJECT_ROOT/app/proguard-rules.pro"
echo "Android 1.0.2 development source reconstructed successfully"
