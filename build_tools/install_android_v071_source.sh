#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v070_source.sh
python3 android/v0.7.1/patch_v071.py

grep -Fq 'versionName = "0.7.1"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 701' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'private fun V071CategoryRail(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
grep -Fq 'contentState.animateScrollToItem(categoryStartIndex + index)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
grep -Fq 'durationMillis = 145' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
grep -Fq 'private fun V071UseVlcLiveFallback(item: MediaEntry)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'VLCVideoLayout(context)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'setEnableDecoderFallback(true)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'org.videolan.android:libvlc-all:3.6.5' "$PROJECT_ROOT/app/build.gradle.kts"

echo "Android v0.7.1 source reconstructed successfully"
