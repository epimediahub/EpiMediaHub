#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v102_source.sh
python3 android/v1.0.3/patch_v103.py

grep -Fq 'versionCode = 1003' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.3"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'minSdk = 25' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'isMinifyEnabled = false' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'isShrinkResources = false' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq -- '-keepattributes Signature, InnerClasses, EnclosingMethod' "$PROJECT_ROOT/app/proguard-rules.pro"
echo "Android 1.0.3 development source reconstructed successfully"
