#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"
bash build_tools/install_android_v091_source.sh
python3 android/v0.9.2/patch_v092.py
grep -Fq 'versionCode = 902' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "0.9.2"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'val needsCompatibilityPlayer = hasVideo || !hasAudio || !player.isPlaying' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'compatibilityUrl = playbackUrls.getOrNull(attempt).orEmpty()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
! grep -Fq 'if (false && item.kind == MediaKind.LIVE)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
echo "Android 0.9.2 source reconstructed successfully"
