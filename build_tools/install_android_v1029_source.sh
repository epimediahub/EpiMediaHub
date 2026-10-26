#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?Missing PROJECT_ROOT}"
bash build_tools/install_android_v1028_source.sh
python3 android/v1.0.29/patch_v129.py
grep -Fq 'versionCode = 1029' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V129JsonRows.load' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'getKidsHomeObserve()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V108SmartTubeCore.kt"
