#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v063_source.sh
python3 android/v0.6.4/patch_v064.py
python3 android/hotfixes/v064_xtream_hotfix1.py
python3 android/hotfixes/v064_xtream_hotfix2.py
python3 android/hotfixes/v064_xtream_hotfix3.py
python3 android/hotfixes/v064_xtream_hotfix4.py
python3 android/hotfixes/v064_xtream_hotfix5.py
python3 android/hotfixes/v064_xtream_hotfix6.py

grep -Fq 'versionName = "0.6.4.6"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 609' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'streamServerCache' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'server_info' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'direct_source' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'cachedStreamServer()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'm3uStreamUrlCache' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'm3uPrefetching' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'prefetchExactM3uAsync()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'providerM3uUrl()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'preparePlaybackItem(item: MediaEntry)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'val exact = cachedExactM3uUrl(item.id).trim()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'urls += "$server/$rawUser/$rawPass/$rawId"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq '#EXTVLCOPT:http-user-agent=' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq '#EXTHTTP:' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'if (exactProviderUrl.isNotBlank()) return listOf(exactProviderUrl)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'val initialWindow = entries.filterNot { it.id in alreadyLoaded }.take(8)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'initialWindow.chunked(2)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'XtreamClient(profile).preparePlaybackItem(item)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'parseIptvHttpRequest(raw: String)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'httpFactory.setDefaultRequestProperties(requestHeaders)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'player.setMediaItem(MediaItem.fromUri(request.url))' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'DefaultLoadControl.Builder()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq '.setBufferDurationsMs(1_000, 4_000, 200, 400)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'if (false && item.kind == MediaKind.LIVE)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'player.clearMediaItems()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'InvalidResponseCodeException' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"

echo "Android v0.6.4.6 source reconstructed successfully with real-provider M3U fast-zap and anti-flood fixes"
