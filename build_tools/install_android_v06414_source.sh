#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v06413_source.sh
python3 android/hotfixes/v064_xtream_hotfix14.py

grep -Fq 'versionName = "0.6.4.14"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 617' "$PROJECT_ROOT/app/build.gradle.kts"
XTREAM="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
MAIN="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainActivity.kt"

grep -Fq 'provider get.php M3U may exceed the Android TV heap' "$XTREAM"
grep -Fq 'val exactM3u = emptyMap<String, String>()' "$XTREAM"
! grep -Fq 'text(providerM3uUrl()).lineSequence()' "$XTREAM"
grep -Fq 'SetupCodeProvisioning.sync(applicationContext)' "$MAIN"
grep -Fq 'result is DeviceSyncResult.Success && result.changed' "$MAIN"
grep -Fq 'recreate()' "$MAIN"

echo "Android v0.6.4.14 source reconstructed successfully with OOM-free Xtream catalogs and foreground dashboard sync"
