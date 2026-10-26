#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?Missing PROJECT_ROOT}"
bash build_tools/install_android_v1029_source.sh
python3 android/v1.0.30/patch_v130.py
grep -Fq 'versionCode = 1030' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'if (!parental.settings().hasPin) leaveKids()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V130SmartTubeGate.kt"
