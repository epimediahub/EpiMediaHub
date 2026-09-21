#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v083_source.sh
python3 android/v0.8.4/patch_v084.py

grep -Fq 'versionName = "0.8.4"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 804' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'return item.kind == MediaKind.LIVE' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq -- '--audio-replay-gain-mode=none' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"

echo "Android 0.8.4 source reconstructed successfully"
