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
python3 android/hotfixes/v064_xtream_hotfix6b.py
python3 android/hotfixes/v064_xtream_hotfix7.py
python3 android/hotfixes/v064_xtream_hotfix8.py
python3 android/hotfixes/v064_xtream_hotfix9.py
python3 android/hotfixes/v064_xtream_hotfix10.py
python3 android/hotfixes/v064_xtream_hotfix11.py
python3 android/hotfixes/v064_xtream_hotfix11b.py
python3 android/hotfixes/v064_xtream_hotfix12.py

grep -Fq 'versionName = "0.6.4.12"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 615' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'streamServerCache' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'server_info' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'direct_source' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'cachedStreamServer()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'm3uStreamUrlCache' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'm3uPrefetching' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'prefetchExactM3uAsync()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'providerM3uUrl()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'preparePlaybackItem(item: MediaEntry)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'private fun canonicalMpegTsLiveUrl(streamId: String)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'getQueryParameter("output")' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'if (canonical.isNotBlank()) return listOf(canonical)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'providerOutputFormat() !in setOf("mpegts", "mpeg-ts")' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'streamUrl = firstNonBlank(canonicalMpegTsLiveUrl(id)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq '#EXTVLCOPT:http-user-agent=' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq '#EXTHTTP:' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'entries.filterNot { it.id in alreadyLoaded }.take(4)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'XtreamClient(profile).preparePlaybackItem(item)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'xtreamLibraryCache' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'private fun xtreamLibrary(profile: PlaylistProfile, kind: MediaKind)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'val byCategory = all.groupBy { entry -> entry.categoryId }' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'categories.mapNotNull { category ->' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'byCategory[category.id].orEmpty()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
! grep -Fq 'all.take(24)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
! grep -Fq 'byCategory[category.id].orEmpty().take(24)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'contentFilterKind = null' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'state.playlists.firstOrNull { it.id == item.sourceProfileId }' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'favorites = prefs.loadFavoriteEntries(activeId)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'continueWatching = prefs.loadContinue(activeId)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'recentlyWatched = prefs.loadRecentlyWatched(activeId)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'prefs.clearPlaylistCollections(id)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'sourceProfileId.ifBlank { "legacy" }' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/model/Models.kt"
grep -Fq 'collectionKey("favorites_items", profileId)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/PrefsRepository.kt"
grep -Fq 'collectionKey("continue", profileId)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/PrefsRepository.kt"
grep -Fq 'collectionKey("recently_watched", profileId)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/PrefsRepository.kt"
grep -Fq 'fun clearPlaylistCollections(profileId: String)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/PrefsRepository.kt"
grep -Fq 'fun switchLiveChannel(item: MediaEntry, channelList: List<MediaEntry>)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'private var liveZapGeneration = 0L' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'val rememberedId=vm.browserSelectedId(kind,cat.id)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
grep -Fq 'Modifier.focusRequester(channelFocusRequester)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
grep -Fq 'vm.play(m,u.items)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
grep -Fq 'fun switchLiveBy(direction: Int): Boolean' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'KeyEvent.KEYCODE_DPAD_UP -> if(item.kind==MediaKind.LIVE)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'KeyEvent.KEYCODE_DPAD_DOWN -> if(item.kind==MediaKind.LIVE)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'u.screen !is Screen.Player' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"
grep -Fq '// Back navigation is handled by the device/system Back action.' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Common.kt"
grep -Fq 'var searchDialog by remember(providerId) { mutableStateOf(false) }' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/ParityScreens.kt"
grep -Fq 'OutlinedButton(onClick = { searchDialog = true }, modifier = Modifier.weight(1f))' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/ParityScreens.kt"
grep -Fq 'items(u.categories, key = { "category:${it.id}" })' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
grep -Fq 'items(entries, key = { it.resumeKey })' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
! grep -Fq 'items(entries.take(24)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
grep -Fq 'android.permission.REQUEST_INSTALL_PACKAGES' "$PROJECT_ROOT/app/src/main/AndroidManifest.xml"
grep -Fq 'releases/tags/v0.6.4-test' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"
grep -Fq 'EpiMediaHub_Android_v0.6.4-test.apk' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"
grep -Fq 'private fun isNewer(remote: String, local: String): Boolean' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"
grep -Fq 'Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"
grep -Fq 'canRequestPackageInstalls()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"
grep -Fq 'FileProvider.getUriForFile' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"
grep -Fq 'Country("fast", "Kostenloses Streaming", "Pluto TV · Rakuten TV"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/MediathekClient.kt"
grep -Fq 'externalUrl = "https://pluto.tv/"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/MediathekClient.kt"
grep -Fq 'appPackages = listOf("tv.pluto.android")' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/MediathekClient.kt"
grep -Fq 'externalUrl = "https://www.rakuten.tv/de"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/MediathekClient.kt"
grep -Fq 'appPackages = listOf("tv.wuaki.apptv", "tv.wuaki")' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/MediathekClient.kt"
grep -Fq '<package android:name="tv.pluto.android" />' "$PROJECT_ROOT/app/src/main/AndroidManifest.xml"
grep -Fq '<package android:name="tv.wuaki.apptv" />' "$PROJECT_ROOT/app/src/main/AndroidManifest.xml"
grep -Fq 'private fun openExternalMediathekProvider(context: Context, provider: MediathekClient.Provider)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/ParityScreens.kt"
grep -Fq 'getLaunchIntentForPackage(packageName)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/ParityScreens.kt"
grep -Fq 'parseIptvHttpRequest(raw: String)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'httpFactory.setDefaultRequestProperties(requestHeaders)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'player.setMediaItem(MediaItem.fromUri(request.url))' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'val liveLoadControl = DefaultLoadControl.Builder()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq '.setBufferDurationsMs(750, 3_000, 150, 300)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'exoBuilder.setLoadControl(liveLoadControl)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'if (false && item.kind == MediaKind.LIVE)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'player.clearMediaItems()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'InvalidResponseCodeException' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"

echo "Android v0.6.4.12 source reconstructed successfully with unlimited movie/series horizontal rows"
