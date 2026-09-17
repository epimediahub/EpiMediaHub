#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v06414_source.sh
python3 android/hotfixes/v064_xtream_hotfix15.py

grep -Fq 'versionName = "0.6.4.15"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 618' "$PROJECT_ROOT/app/build.gradle.kts"
M3U="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/M3uParser.kt"
PROVISION="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
HUB="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
XTREAM="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"

grep -Fq 'parseReader(it)' "$M3U"
grep -Fq 'DEFAULT_STREAM_UA' "$M3U"
! grep -Fq 'it.readText()' "$M3U"
grep -Fq 'MANAGED_PROFILE_PREFIX = "managed-dashboard-"' "$PROVISION"
grep -Fq 'config.optJSONArray("playlists")' "$PROVISION"
grep -Fq 'xtreamFromM3u(url)' "$PROVISION"
grep -Fq 'localManagedMismatch' "$PROVISION"
grep -Fq 'Filme werden geladen …' "$HUB"
grep -Fq 'onError = { imageFailed = true }' "$HUB"
grep -Fq 'o.optString("cover_big")' "$XTREAM"

echo "Android v0.6.4.15 source reconstructed successfully with Dashboard 0.7 multi-playlist, streaming M3U and catalog loading UX"
