#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v082_source.sh
python3 android/v0.8.3/patch_v083.py

grep -Fq 'versionName = "0.8.3"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 803' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'fun V083HomeScreen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V083Home.kt"
grep -Fq 'targetValue = if (focused) 1.025f else 1f' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V083Home.kt"
grep -Fq 'targetValue = if (focused) 1.035f else 1f' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
grep -Fq 'targetValue = if (focused) 1.012f else 1f' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V076LiveTv.kt"
! grep -Fq 'LaunchedEffect(visibleCategories, selectedCategoryId, categoryStartIndex)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
! grep -Fq 'LaunchedEffect(selectedId, channels.size)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V076LiveTv.kt"

echo "Android 0.8.3 source reconstructed successfully"
