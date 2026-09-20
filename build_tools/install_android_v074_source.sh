#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v073_source.sh
python3 android/v0.7.4/patch_v074.py

grep -Fq 'versionName = "0.7.4"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 704' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'KeyEvent.KEYCODE_CHANNEL_UP' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'fun rememberedLibraryCategory(kind: MediaKind)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'MediaKind.LIVE -> "LIVE TV"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
grep -Fq 'RELEASE_API_URL' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"

echo "Android v0.7.4 source reconstructed successfully"
