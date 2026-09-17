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
# Xtream fast-zap: once the provider M3U supplied an exact playable URL, use
# that canonical URL only. Trying seven additional guessed paths after the
# canonical URL fails adds latency and can trigger provider anti-flood limits.
# Providers without an exact M3U URL still retain the legacy fallback matrix.
# ---------------------------------------------------------------------------
xtream = java / "data/XtreamClient.kt"
s = xtream.read_text()
old_candidates = '''        val servers = listOf(cachedStreamServer(), p.server.trimEnd('/')).filter { it.isNotBlank() }.distinct()
        val urls = mutableListOf<String>()
        cachedExactM3uUrl(item.id).takeIf { it.isNotBlank() }?.let { urls += it }
        if (item.streamUrl.isNotBlank()) urls += item.streamUrl
'''
new_candidates = '''        val servers = listOf(cachedStreamServer(), p.server.trimEnd('/')).filter { it.isNotBlank() }.distinct()
        val exactProviderUrl = cachedExactM3uUrl(item.id).trim()
        if (exactProviderUrl.isNotBlank()) return listOf(exactProviderUrl)
        val urls = mutableListOf<String>()
        if (item.streamUrl.isNotBlank()) urls += item.streamUrl
'''
if old_candidates not in s:
    raise SystemExit("stream candidate exact-provider anchor missing")
s = s.replace(old_candidates, new_candidates, 1)
xtream.write_text(s)

# ---------------------------------------------------------------------------
# Provider anti-flood: do not clear already loaded EPG on every Live category
# switch, and preload only a small visible-window batch with low concurrency.
# The old code fired up to 72 short-EPG requests per category (and potentially
# twice that through endpoint fallbacks), competing directly with Live startup.
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
                        val initialWindow = entries.filterNot { it.id in alreadyLoaded }.take(8)
                        for (chunk in initialWindow.chunked(2)) {
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
if old_epg_loop not in s:
    raise SystemExit("Live EPG preload loop anchor missing")
s = s.replace(old_epg_loop, new_epg_loop, 1)
vm.write_text(s)

# ---------------------------------------------------------------------------
# Player fast-zap:
# - use a small Live-oriented buffer so accepted MPEG-TS/HLS streams render fast;
# - disable the old 6.5 s first-frame watchdog (it was skipping valid slow-start
#   streams and opening more provider connections);
# - explicitly stop/clear the player before release so providers with strict
#   one-connection/session limits see the previous channel close immediately.
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
            .setBufferDurationsMs(1_000, 4_000, 200, 400)
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
new_watchdog_gate = '''            // v0.6.4.6: do not abandon an accepted Live stream merely because
            // its first decoded frame needs a few seconds. HTTP/player errors
            // still advance immediately, but normal buffering no longer opens
            // a second competing stream connection.
            if (false && item.kind == MediaKind.LIVE) {
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
            player.stop()
            player.clearMediaItems()
            player.release()
        }
'''
if old_dispose not in s:
    raise SystemExit("Player dispose anchor missing")
s = s.replace(old_dispose, new_dispose, 1)
player.write_text(s)

# Sanity.
checks = [
    (gradle, 'versionName = "0.6.4.6"'),
    (gradle, 'versionCode = 609'),
    (xtream, 'if (exactProviderUrl.isNotBlank()) return listOf(exactProviderUrl)'),
    (vm, 'val initialWindow = entries.filterNot { it.id in alreadyLoaded }.take(8)'),
    (vm, 'initialWindow.chunked(2)'),
    (player, 'DefaultLoadControl.Builder()'),
    (player, '.setBufferDurationsMs(1_000, 4_000, 200, 400)'),
    (player, 'if (false && item.kind == MediaKind.LIVE)'),
    (player, 'player.clearMediaItems()'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing hotfix6 marker {marker} in {path}")

print("Android v0.6.4.6 fast-zap + provider anti-flood hotfix applied")
