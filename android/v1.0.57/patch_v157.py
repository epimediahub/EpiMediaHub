#!/usr/bin/env python3
"""EpiMediaHub 1.0.57 official: unified Android TV/Fire TV LIVE playback,
and provider-backed 'Zuletzt hinzugefügt' for movies and series.

Apply after v1.0.56, without changing playlist settings, persisted credentials,
registration, VPN fail-closed policy, customer data, or application package ID.
"""
from pathlib import Path
import os, shutil

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
java = root / "app/src/main/java/de/epimediahub/app"
tests = root / "app/src/test/java/de/epimediahub/app"

def replace(path: Path, old: str, new: str):
    source = path.read_text()
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{path.name}: expected one anchor, got {count}: {old[:120]}")
    path.write_text(source.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
replace(gradle, "versionCode = 1056", "versionCode = 1057")
replace(gradle, 'versionName = "1.0.56"', 'versionName = "1.0.57"')

xtream = java / "data/XtreamClient.kt"

# Don't force MPEGTS canonical no-extension URL on Fire TV. Prefer the exact
# provider URL, then make canonical addresses part of a bounded fallback list.
replace(xtream,
'''        if (item.kind == MediaKind.LIVE) {
            val canonical = canonicalMpegTsLiveUrl(item.id)
            if (canonical.isNotBlank()) return item.copy(streamUrl = canonical)
        }
        val exact = cachedExactM3uUrl(item.id).trim()
        if (exact.isNotBlank()) return item.copy(streamUrl = exact)
        // v1.0.55:''',
'''        val exact = cachedExactM3uUrl(item.id).trim()
        if (exact.isNotBlank()) return item.copy(streamUrl = exact)
        // v1.0.55:''')

replace(xtream,
'''        if (item.kind == MediaKind.LIVE && V155ExactM3uLive.nonFireTvDevice()) {
            // M3U was already prefetched once, during Live catalogue loading.''',
'''        if (item.kind == MediaKind.LIVE) {
            // The same bounded index is now used by Fire TV and other Android TV.
            // M3U was already prefetched once, during Live catalogue loading.''')

replace(xtream,
'''            if (!exactLive.isNullOrBlank()) return item.copy(streamUrl = exactLive)
        }
        prefetchExactM3uAsync()
        return item
    }

    fun streamCandidates(item: MediaEntry): List<String> {''',
'''            if (!exactLive.isNullOrBlank()) return item.copy(streamUrl = exactLive)
            val canonical = canonicalMpegTsLiveUrl(item.id)
            if (canonical.isNotBlank()) return item.copy(streamUrl = canonical)
        }
        prefetchExactM3uAsync()
        return item
    }

    fun streamCandidates(item: MediaEntry): List<String> {''')

replace(xtream,
'''        if (item.kind == MediaKind.LIVE) {
            val canonical = canonicalMpegTsLiveUrl(item.id)
            if (canonical.isNotBlank()) return listOf(canonical)
        }
        val exactProviderUrl = cachedExactM3uUrl(item.id).trim()
        if (exactProviderUrl.isNotBlank()) return listOf(exactProviderUrl)
        val urls = mutableListOf<String>()
        if (item.streamUrl.isNotBlank()) urls += item.streamUrl''',
'''        val urls = mutableListOf<String>()
        // Prepared exact URL from authenticated provider M3U is primary.
        if (item.streamUrl.isNotBlank()) urls += item.streamUrl
        val exactProviderUrl = cachedExactM3uUrl(item.id).trim()
        if (exactProviderUrl.isNotBlank()) urls += exactProviderUrl
        if (item.kind == MediaKind.LIVE) {
            val canonical = canonicalMpegTsLiveUrl(item.id)
            if (canonical.isNotBlank()) urls += canonical
        }''')

replace(xtream,
'''        return urls.filter { it.isNotBlank() && it != "null" }.distinct()
    }

    fun categories(kind: MediaKind): List<MediaCategory> {''',
'''        val distinct = urls.filter { it.isNotBlank() && it != "null" }.distinct()
        // No hundred-URL fallback loop if the provider does not play.
        return if (item.kind == MediaKind.LIVE) distinct.take(10) else distinct
    }

    fun categories(kind: MediaKind): List<MediaCategory> {''')

replace(xtream,
'''        if (kind == MediaKind.LIVE && V155ExactM3uLive.nonFireTvDevice() &&
            providerOutputFormat() !in setOf("mpegts", "mpeg-ts")) {
            V156ExactM3uCache.warm(m3uStreamKey() + "|" + p.password, providerM3uUrl())
        }''',
'''        if (kind == MediaKind.LIVE) {
            // Warm once for all Android TV platforms; channel zaps read the
            // bounded per-provider index instead of re-downloading get.php.
            V156ExactM3uCache.warm(m3uStreamKey() + "|" + p.password, providerM3uUrl())
        }''')

# Media3: handle a channel that never delivers the first frame by trying
# the next candidate before switching to LibVLC. The old code went directly
# to VLC after the first silent hang, hiding URL mismatch failures.
player = java / "ui/PlayerScreen.kt"
replace(player,
'''                        if (needsCompatibilityPlayer) {
                            compatibilityUrl = playbackUrls.getOrNull(attempt).orEmpty()
                            playbackError = ""
                            useVlc = true
                        }''',
'''                        if (needsCompatibilityPlayer) {
                            val nextCandidate = activeUrl + 1
                            if (nextCandidate < playbackUrls.size && activeUrl < 2) {
                                openUrl(nextCandidate)
                            } else {
                                compatibilityUrl = playbackUrls.getOrNull(attempt).orEmpty()
                                playbackError = ""
                                useVlc = true
                            }
                        }''')

# Existing V128 newest section has a real gap: if provider doesn't send
# addedAt, it stays empty and is completely hidden. Use provider order then.
vm = java / "MainViewModel.kt"
replace(vm,
'''                            val newest = all.asSequence().filter { it.addedAt > 0 }.sortedByDescending { it.addedAt }.take(36).toList()
                            if (newest.isNotEmpty()) rows["__recently_added__"] = newest''',
'''                            val newest = V157RecentlyAdded.select(all, 36)
                            if (newest.isNotEmpty()) rows["__recently_added__"] = newest''')

# Fix the real 'Mehr' category access: previous nested branch was unreachable,
# because MOVIE / SERIES were intercepted by the parent if.
replace(vm,
'''                        if (kind == MediaKind.MOVIE || kind == MediaKind.SERIES) {
                            val all = xtreamLibrary(p, kind)
                            if (cat == "__all__") all else all.filter { entry -> entry.categoryId == cat }
                        } else {
                            if (cat == "__recently_added__" && (kind == MediaKind.MOVIE || kind == MediaKind.SERIES)) {
                            xtreamLibrary(p, kind)
                                .filter { it.addedAt > 0L }
                                .sortedByDescending { it.addedAt }
                                .take(300)
                        } else {
                            XtreamClient(p).entries(kind, cat)
                        }
                        }''',
'''                        if (kind == MediaKind.MOVIE || kind == MediaKind.SERIES) {
                            val all = xtreamLibrary(p, kind)
                            when (cat) {
                                "__recently_added__" -> V157RecentlyAdded.select(all, 300)
                                "__all__" -> all
                                else -> all.filter { entry -> entry.categoryId == cat }
                            }
                        } else {
                            XtreamClient(p).entries(kind, cat)
                        }''')

# Save only a few kilobytes of code/test, not downloaded playlists.
shutil.copyfile(here / "V157RecentlyAdded.kt", java / "data/V157RecentlyAdded.kt")
shutil.copyfile(here / "V157RecentlyAddedTest.kt", tests / "data/V157RecentlyAddedTest.kt")

# Catalogue entries are intentionally shown in two UI rows: the new recently
# added row and their regular provider categories. The old V128 test counted
# row appearances and assumed each film could occur in only one row. Preserve
# its concurrency/re-entry network assertions but check unique media identities.
catalogue_test = tests / "ui/V128CatalogueLoadingTest.kt"
replace(catalogue_test,
'''            assertEquals(2, vm.ui.value.catalogRows.values.sumOf { it.size })''',
'''            assertEquals(2, vm.ui.value.catalogRows.values.flatMap { it }.distinctBy { it.resumeKey }.size)
            assertEquals(2, vm.ui.value.catalogRows["__recently_added__"].orEmpty().size)''')


source = xtream.read_text()
assert source.count("V156ExactM3uCache.resolve(") == 1
assert source.count("V156ExactM3uCache.warm(") == 1
assert "if (item.kind == MediaKind.LIVE && V155ExactM3uLive.nonFireTvDevice())" not in source
assert "if (canonical.isNotBlank()) return listOf(canonical)" not in source
assert "return if (item.kind == MediaKind.LIVE) distinct.take(10) else distinct" in source
assert "val nextCandidate = activeUrl + 1" in player.read_text()
assert 'V157RecentlyAdded.select(all, 36)' in vm.read_text()
assert 'V157RecentlyAdded.select(all, 300)' in vm.read_text()
assert "V153DirectPolicy.canPlay" in (java / "vpn/V134VpnSession.kt").read_text()
print("1.0.57 official source: Fire TV and GalaBox shared bounded warm URL cache; fallbacks")
print("1.0.57 movie/series recent: provider timestamp order, stable fallback, open-all fixed")
print("User profiles / VPN fail-closed / device registration left unchanged")
