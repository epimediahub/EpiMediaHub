#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"
bash build_tools/install_android_v092_source.sh
python3 android/v0.9.3/patch_v093.py
grep -Fq 'versionCode = 903' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "0.9.3"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'distinctBy { continueIdentity(it.media) }' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/PrefsRepository.kt"
grep -Fq 'fun setCategoryVisible(kind: MediaKind, categoryId: String, visible: Boolean)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'V093ContinueLabel(c)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
grep -Fq 'if (item.kind != MediaKind.LIVE && controls)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'V093FormatTime(position)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
echo "Android 0.9.3 source reconstructed successfully"
