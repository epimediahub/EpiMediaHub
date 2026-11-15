#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v081_source.sh
python3 android/v0.8.2/patch_v082.py

grep -Fq 'versionName = "0.8.2"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 802' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'fun V082HomeScreen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V082Home.kt"
grep -Fq 'fillMaxWidth(if (isTv) .67f else .82f)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V082Home.kt"
grep -Fq 'alpha = if (isTv) .64f else .72f' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V082Home.kt"
grep -Fq 'catalogRowsLoading = kind == MediaKind.MOVIE || kind == MediaKind.SERIES || kind == MediaKind.LIVE' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'xtreamLibrary(profile, kind)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'out["__recently_added__"] = newest' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'playlist = u.active?.name ?: "EpiMediaHub"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V082Home.kt"

echo "Android 0.8.2 source reconstructed successfully"
