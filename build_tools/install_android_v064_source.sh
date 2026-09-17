#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v063_source.sh
python3 android/v0.6.4/patch_v064.py
python3 android/hotfixes/v064_xtream_hotfix1.py
python3 android/hotfixes/v064_xtream_hotfix2.py
python3 android/hotfixes/v064_xtream_hotfix3.py
python3 android/hotfixes/v064_xtream_hotfix4.py

grep -Fq 'versionName = "0.6.4.4"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 607' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'streamServerCache' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'server_info' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'direct_source' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'cachedStreamServer()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'm3uStreamUrlCache' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'm3uPrefetching' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'prefetchExactM3uAsync()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'providerM3uUrl()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'preparePlaybackItem(item: MediaEntry)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'exactM3uStreamUrls()[item.id]' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'XtreamClient(profile).preparePlaybackItem(item)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'DefaultHttpDataSource.Factory()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'VLC/3.0.21 LibVLC/3.0.21' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'apiWithEndpoint("panel_api.php"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'val all = arrayAction(action)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'row.optString("category_id") == requestedCategory' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'onRenderedFirstFrame()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'postDelayed(it, 6500L)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'InvalidResponseCodeException' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'httpCode = cause.responseCode' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"

echo "Android v0.6.4.4 source reconstructed successfully with exact provider playback URL and HTTP status diagnostics"
