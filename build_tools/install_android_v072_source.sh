#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v071_source.sh
python3 android/v0.7.2/patch_v072.py

grep -Fq 'versionName = "0.7.2"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 702' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'private fun V072UseVlcLiveFallback(item: MediaEntry)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq '(?:RAW|HEVC|H\.?265)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'if (V072UseVlcLiveFallback(item))' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'fun refreshPlaylistsAtAppStart()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'Lifecycle.Event.ON_START' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"
grep -Fq 'if (sync is DeviceSyncResult.Success) vm.refreshProfiles()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"

echo "Android v0.7.2 source reconstructed successfully"
