#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"
bash build_tools/install_android_v090_source.sh
python3 android/v0.9.1/patch_v091.py
grep -Fq 'versionCode = 901' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "0.9.1"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'LazyRow(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
grep -Fq 'Staffel $season' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
grep -Fq 'delay(if (item.kind == MediaKind.LIVE) 4500 else 3500)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'useController = item.kind != MediaKind.LIVE && !(isTv && item.kind == MediaKind.EPISODE)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
echo "Android 0.9.1 source reconstructed successfully"
