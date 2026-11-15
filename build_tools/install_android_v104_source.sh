#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v103_source.sh
python3 android/v1.0.4/patch_v104.py

grep -Fq 'versionCode = 1004' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.4"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'minSdk = 25' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V104SmartTubeShell(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V083Home.kt"
grep -Fq 'https://yt.be/activate' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V104SmartTubeShell.kt"
grep -Fq 'createMpdStream' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V104SmartTubeCore.kt"
echo "Android 1.0.4 development source reconstructed successfully"
