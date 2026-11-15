#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# Visible version.
# ---------------------------------------------------------------------------
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 608', 'versionCode = 609', 'hotfix6 versionCode')
replace_once(gradle, 'versionName = "0.6.4.5"', 'versionName = "0.6.4.6"', 'hotfix6 versionName')

home = java / "ui/V044Home.kt"
home_text = home.read_text()
if "0.6.4.5" not in home_text:
    raise SystemExit("visible home version 0.6.4.5 not found")
home.write_text(home_text.replace("0.6.4.5", "0.6.4.6", 1))

# ---------------------------------------------------------------------------
# Real-provider Xtream/MPEG-TS handling.
# The uploaded provider M3U proves this provider emits Live streams as:
#   http://host[:port]/USER/PASS/STREAM_ID
# with no /live prefix and no extension, even though get.php uses output=mpegts.
# Avoid downloading/parsing the full ~23 MB M3U just to derive this URL.
# ---------------------------------------------------------------------------
xtream = java / "data/XtreamClient.kt"
s = xtream.read_text()

old_prepare = '''    fun preparePlaybackItem(item: MediaEntry): MediaEntry {
        if (item.kind != MediaKind.LIVE && item.kind != MediaKind.MOVIE && item.kind != MediaKind.EPISODE) return item
        val exact = exactM3uStreamUrls()[item.id].orEmpty().trim()
        return if (exact.isBlank()) item else item.copy(streamUrl = exact)
    }
'''
new_prepare = '''    private fun providerOutputFormat(): String {
        val originalOutput = runCatching {
            Uri.parse(p.originalUrl.trim()).getQueryParameter("output").orEmpty()
        }.getOrDefault("")
        return firstNonBlank(originalOutput, p.output).trim().trimStart('.').lowercase()
    }

    private fun originalPortalBase(): String {
        val fallback = p.server.trimEnd('/')
        val raw = p.originalUrl.trim()
        if (!raw.contains("get.php", ignoreCase = true)) return fallback
        return runCatching {
            val uri = Uri.parse(raw)
            val scheme = uri.scheme.orEmpty()
            val authority = uri.encodedAuthority.orEmpty()
            if (scheme.isBlank() || authority.isBlank()) return@runCatching fallback
            val parent = uri.encodedPath.orEmpty().substringBeforeLast('/', "").trimEnd('/')
            "$scheme://$authority$parent".trimEnd('/')
        }.getOrDefault(fallback)
    }

    private fun canonicalMpegTsLiveUrl(streamId: String): String {
        val format = providerOutputFormat()
        if (format != "mpegts" && format != "mpeg-ts") return ""
        val base = originalPortalBase()
        val id = streamId.trim()
        if (base.isBlank() || id.isBlank() || p.username.isBlank() || p.password.isBlank()) return ""
        return "$base/${path(p.username)}/${path(p.password)}/${path(id)}"
    }

    fun preparePlaybackItem(item: MediaEntry): MediaEntry {
        if (item.kind != MediaKind.LIVE && item.kind != MediaKind.MOVIE && item.kind != MediaKind.EPISODE) return item
        if (item.kind == MediaKind.LIVE) {
            val canonical = canonicalMpegTsLiveUrl(item.id)
            if (canonical.isNotBlank()) return item.copy(streamUrl = canonical)
        }
        val exact = cachedExactM3uUrl(item.id).trim()
        if (exact.isNotBlank()) return item.copy(streamUrl = exact)
        prefetchExactM3uAsync()
        return item
    }
'''
if old_prepare not in s:
    raise SystemExit("preparePlaybackItem hotfix6 anchor missing")
s = s.replace(old_prepare, new_prepare, 1)

old_candidates = '''        val servers = listOf(cachedStreamServer(), p.server.trimEnd('/')).filter { it.isNotBlank() }.distinct()
        val urls = mutableListOf<String>()
        cachedExactM3uUrl(item.id).takeIf { it.isNotBlank() }?.let { urls += it }
        if (item.streamUrl.isNotBlank()) urls += item.streamUrl
'''
new_candidates = '''        val servers = listOf(cachedStreamServer(), p.server.trimEnd('/')).filter { it.isNotBlank() }.distinct()
        if (item.kind == MediaKind.LIVE) {
            val canonical = canonicalMpegTsLiveUrl(item.id)
            if (canonical.isNotBlank()) return listOf(canonical)
        }
        val exactProviderUrl = cachedExactM3uUrl(item.id).trim()
        if (exactProviderUrl.isNotBlank()) return listOf(exactProviderUrl)
        val urls = mutableListOf<String>()
        if (item.streamUrl.isNotBlank()) urls += item.streamUrl
'''
if old_candidates not in s:
    raise SystemExit("stream candidate exact-provider anchor missing")
s = s.replace(old_candidates, new_candidates, 1)

old_prefetch = '''        if (kind == MediaKind.LIVE || kind == MediaKind.MOVIE) prefetchExactM3uAsync()
        return buildList {
'''
new_prefetch = '''        if (kind == MediaKind.MOVIE || (kind == MediaKind.LIVE && providerOutputFormat() !in setOf("mpegts", "mpeg-ts"))) {
            prefetchExactM3uAsync()
        }
        return buildList {
'''
if old_prefetch not in s:
    raise SystemExit("Live/VOD M3U prefetch anchor missing")
s = s.replace(old_prefetch, new_prefetch, 1)

old_live_url = '''                                streamUrl = firstNonBlank(cachedExactM3uUrl(id), o.optString("direct_source"), "$streamServer/live/${path(p.username)}/${path(p.password)}/${path(id)}.${p.output.trimStart('.')}"),
'''
new_live_url = '''                                streamUrl = firstNonBlank(canonicalMpegTsLiveUrl(id), cachedExactM3uUrl(id), o.optString("direct_source"), "$streamServer/live/${path(p.username)}/${path(p.password)}/${path(id)}.${p.output.trimStart('.')}"),
'''
if old_live_url not in s:
    raise SystemExit("Live entry streamUrl anchor missing")
s = s.replace(old_live_url, new_live_url, 1)
xtream.write_text(s)

# ---------------------------------------------------------------------------
# Provider anti-flood: retain EPG cache and dramatically reduce category-load
# short-EPG traffic. The previous 72 requests competed with Live startup.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
s = vm.read_text()
old_reset = '''        set { it.copy(loading = true, items = emptyList(), epg = if (kind == MediaKind.LIVE) emptyMap() else it.epg, details = emptyMap(), detailLoading = emptySet(), error = "") }
'''
new_reset = '''        set { it.copy(loading = true, items = emptyList(), epg = it.epg, details = emptyMap(), detailLoading = emptySet(), error = "") }
'''
if old_reset not in s:
    raise SystemExit("Live EPG reset anchor missing")
s = s.replace(old_reset, new_reset, 1)

old_epg_loop = '''                        val out = mutableMapOf<String, List<EpgItem>>()
                        for (chunk in entries.take(72).chunked(8)) {
                            coroutineScope {
                                chunk.map { channel ->
                                    async {
                                        channel.id to runCatching { client.shortEpg(channel.id) }.getOrDefault(emptyList())
                                    }
                                }.awaitAll()
                            }.forEach { (id, list) -> if (list.isNotEmpty()) out[id] = list }
                        }
                        out
'''
new_epg_loop = '''                        val out = mutableMapOf<String, List<EpgItem>>()
                        val alreadyLoaded = _ui.value.epg.keys
                        val initialWindow = entries.filterNot { it.id in alreadyLoaded }.take(4)
                        for (channel in initialWindow) {
                            val list = runCatching { client.shortEpg(channel.id) }.getOrDefault(emptyList())
                            if (list.isNotEmpty()) out[channel.id] = list
                        }
                        out
'''
if old_epg_loop not in s:
    raise SystemExit("Live EPG preload loop anchor missing")
s = s.replace(old_epg_loop, new_epg_loop, 1)
vm.write_text(s)

# ---------------------------------------------------------------------------
# Player fast-zap: smaller buffer, no first-frame watchdog, immediate teardown.
# ---------------------------------------------------------------------------
player = java / "ui/PlayerScreen.kt"
s = player.read_text()
if 'import androidx.media3.exoplayer.DefaultLoadControl\n' not in s:
    anchor = 'import androidx.media3.exoplayer.ExoPlayer\n'
    if anchor not in s:
        raise SystemExit("ExoPlayer import anchor missing")
    s = s.replace(anchor, 'import androidx.media3.exoplayer.DefaultLoadControl\n' + anchor, 1)

old_engine = '''        val exo = ExoPlayer.Builder(context)
            .setMediaSourceFactory(DefaultMediaSourceFactory(context).setDataSourceFactory(httpFactory))
            .build()
'''
new_engine = '''        val loadControl = DefaultLoadControl.Builder()
            .setBufferDurationsMs(750, 3_000, 150, 300)
            .setPrioritizeTimeOverSizeThresholds(true)
            .build()
        val exo = ExoPlayer.Builder(context)
            .setLoadControl(loadControl)
            .setMediaSourceFactory(DefaultMediaSourceFactory(context).setDataSourceFactory(httpFactory))
            .build()
'''
if old_engine not in s:
    raise SystemExit("Player engine anchor missing")
s = s.replace(old_engine, new_engine, 1)

old_watchdog_gate = '''            if (item.kind == MediaKind.LIVE) {
                val attempt = index
'''
new_watchdog_gate = '''            if (false && item.kind == MediaKind.LIVE) {
                val attempt = index
'''
if old_watchdog_gate not in s:
    raise SystemExit("Live watchdog gate anchor missing")
s = s.replace(old_watchdog_gate, new_watchdog_gate, 1)

old_dispose = '''        onDispose {
            cancelWatchdog()
            save()
            player.removeListener(listener)
            player.release()
        }
'''
new_dispose = '''        onDispose {
            cancelWatchdog()
            save()
            player.removeListener(listener)
            player.playWhenReady = false
            player.stop()
            player.clearMediaItems()
            player.release()
        }
'''
if old_dispose not in s:
    raise SystemExit("Player dispose anchor missing")
s = s.replace(old_dispose, new_dispose, 1)
player.write_text(s)

checks = [
    (gradle, 'versionName = "0.6.4.6"'),
    (gradle, 'versionCode = 609'),
    (xtream, 'private fun canonicalMpegTsLiveUrl(streamId: String)'),
    (xtream, 'getQueryParameter("output")'),
    (xtream, 'if (canonical.isNotBlank()) return listOf(canonical)'),
    (xtream, 'providerOutputFormat() !in setOf("mpegts", "mpeg-ts")'),
    (xtream, 'streamUrl = firstNonBlank(canonicalMpegTsLiveUrl(id)'),
    (vm, 'entries.filterNot { it.id in alreadyLoaded }.take(4)'),
    (player, '.setBufferDurationsMs(750, 3_000, 150, 300)'),
    (player, 'if (false && item.kind == MediaKind.LIVE)'),
    (player, 'player.clearMediaItems()'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing hotfix6 marker {marker} in {path}")

print("Android v0.6.4.6 real-provider fast-zap hotfix applied")
