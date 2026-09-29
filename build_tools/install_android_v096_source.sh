#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"
bash build_tools/install_android_v095_source.sh
python3 android/v0.9.6/patch_v096.py
grep -Fq 'versionCode = 906' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "0.9.6"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'scaleX = 1.85f' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Common.kt"
grep -Fq 'vm.themeRepo().centerMarkRes(theme.id)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V079Themes.kt"
! grep -Fq 'Modifier.align(Alignment.CenterEnd)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V079Themes.kt"
echo "Android 0.9.6 source reconstructed successfully"
