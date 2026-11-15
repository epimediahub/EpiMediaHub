#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v060_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.6.1/patch_v061.py

grep -q 'versionName = "0.6.1"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 601' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'EpiMediaHub beenden?' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"
grep -Fq 'finishAndRemoveTask' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"
grep -Fq 'streamCandidates' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'SubcomposeAsyncImage' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/BrowserRows.kt"
! grep -Fq 'skinMarkRes' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/BrowserRows.kt"
! grep -Fq 'val center = remember(themeId)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Common.kt"

echo "Android v0.6.1 source reconstructed successfully"
