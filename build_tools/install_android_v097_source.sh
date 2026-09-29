#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"
bash build_tools/install_android_v096_source.sh
python3 android/v0.9.7/patch_v097.py
grep -Fq 'versionCode = 907' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "0.9.7"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V097SkinWorld.PIT_GARAGE' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V097SkinEnvironment.kt"
grep -Fq 'V097SkinEnvironment(skinWorld, accent)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Common.kt"
grep -Fq 'V097PrivateDisplayLabel(theme.label, privateTheme)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V079Themes.kt"
echo "Android 0.9.7 source reconstructed successfully"
