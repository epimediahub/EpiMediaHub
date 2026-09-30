#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v1012_source.sh
python3 android/v1.0.13/patch_v113.py

grep -Fq 'versionCode = 1013' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.13"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V113LiveTvKeys.channels(playlistId, selectedCategory?.id.orEmpty())' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V076LiveTv.kt"
grep -Fq 'val state = v111RememberLazyListState(memoryKey)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V076LiveTv.kt"
if grep -Fq 'v111RememberLazyListState("livetv-channels:" + selectedId)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V076LiveTv.kt"; then exit 1; fi
echo "Android 1.0.13 source reconstructed successfully"
