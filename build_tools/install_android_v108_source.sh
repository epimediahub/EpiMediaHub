#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v107_source.sh
python3 android/v1.0.8/patch_v108.py

grep -Fq 'versionCode = 1008' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.8"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V108SmartTubeShell(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V083Home.kt"
grep -Fq 'V108SmartTubeSidebar(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V108SmartTubeShell.kt"
grep -Fq 'V108TopAction(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V108SmartTubeShell.kt"
echo "Android 1.0.8 development source reconstructed successfully"
