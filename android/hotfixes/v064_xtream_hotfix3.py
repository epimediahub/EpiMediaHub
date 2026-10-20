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
# Visible hotfix version.
# ---------------------------------------------------------------------------
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 605', 'versionCode = 606', 'hotfix3 versionCode')
replace_once(gradle, 'versionName = "0.6.4.2"', 'versionName = "0.6.4.3"', 'hotfix3 versionName')

home = java / "ui/V044Home.kt"
home_text = home.read_text()
if "0.6.4.2" not in home_text:
    raise SystemExit("visible home version 0.6.4.2 not found")
home.write_text(home_text.replace("0.6.4.2", "0.6.4.3", 1))


# ---------------------------------------------------------------------------
# Speed: do not block Live/VOD category loading on a full provider M3U download.
# Warm the exact-M3U cache in the background instead. Playback candidate creation
# already reads cachedExactM3uUrl(), so a completed prefetch is picked up later.
# ---------------------------------------------------------------------------
xtream = java / "data/XtreamClient.kt"
s = xtream.read_text()

old_companion = '''    companion object {
        private val streamServerCache = java.util.concurrent.ConcurrentHashMap<String, String>()
        private val m3uStreamUrlCache = java.util.concurrent.ConcurrentHashMap<String, Map<String, String>>()
    }
'''
new_companion = '''    companion object {
        private val streamServerCache = java.util.concurrent.ConcurrentHashMap<String, String>()
        private val m3uStreamUrlCache = java.util.concurrent.ConcurrentHashMap<String, Map<String, String>>()
        private val m3uPrefetching = java.util.concurrent.ConcurrentHashMap.newKeySet<String>()
    }
'''
if old_companion not in s:
    raise SystemExit("Xtream companion hotfix3 anchor missing")
s = s.replace(old_companion, new_companion, 1)

old_cached = '''    private fun cachedExactM3uUrl(streamId: String): String =
        m3uStreamUrlCache[m3uStreamKey()]?.get(streamId).orEmpty()
    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")
'''
new_cached = '''    private fun cachedExactM3uUrl(streamId: String): String =
        m3uStreamUrlCache[m3uStreamKey()]?.get(streamId).orEmpty()

    private fun prefetchExactM3uAsync() {
        val key = m3uStreamKey()
        if (m3uStreamUrlCache.containsKey(key) || !m3uPrefetching.add(key)) return
        Thread({
            try {
                exactM3uStreamUrls()
            } finally {
                m3uPrefetching.remove(key)
            }
        }, "Epi-Xtream-M3U-Prefetch").apply {
            isDaemon = true
            start()
        }
    }

    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")
'''
if old_cached not in s:
    raise SystemExit("cached M3U helper anchor missing")
s = s.replace(old_cached, new_cached, 1)

old_entries = '''        val streamServer = if (kind == MediaKind.LIVE || kind == MediaKind.MOVIE) resolveStreamServer() else cachedStreamServer()
        val exactM3u = if (kind == MediaKind.LIVE || kind == MediaKind.MOVIE) exactM3uStreamUrls() else emptyMap()
        return buildList {
'''
new_entries = '''        val streamServer = if (kind == MediaKind.LIVE || kind == MediaKind.MOVIE) resolveStreamServer() else cachedStreamServer()
        if (kind == MediaKind.LIVE || kind == MediaKind.MOVIE) prefetchExactM3uAsync()
        return buildList {
'''
if old_entries not in s:
    raise SystemExit("blocking exact-M3U entries anchor missing")
s = s.replace(old_entries, new_entries, 1)

old_live_url = '''                                streamUrl = firstNonBlank(exactM3u[id].orEmpty(), o.optString("direct_source"), "$streamServer/live/${path(p.username)}/${path(p.password)}/${path(id)}.${p.output.trimStart('.')}"),
'''
new_live_url = '''                                streamUrl = firstNonBlank(cachedExactM3uUrl(id), o.optString("direct_source"), "$streamServer/live/${path(p.username)}/${path(p.password)}/${path(id)}.${p.output.trimStart('.')}"),
'''
if old_live_url not in s:
    raise SystemExit("live cached exact-M3U anchor missing")
s = s.replace(old_live_url, new_live_url, 1)

old_movie_url = '''                                streamUrl = firstNonBlank(exactM3u[id].orEmpty(), o.optString("direct_source"), "$streamServer/movie/${path(p.username)}/${path(p.password)}/${path(id)}.$ext"),
'''
new_movie_url = '''                                streamUrl = firstNonBlank(cachedExactM3uUrl(id), o.optString("direct_source"), "$streamServer/movie/${path(p.username)}/${path(p.password)}/${path(id)}.$ext"),
'''
if old_movie_url not in s:
    raise SystemExit("movie cached exact-M3U anchor missing")
s = s.replace(old_movie_url, new_movie_url, 1)

xtream.write_text(s)


# ---------------------------------------------------------------------------
# Live playback reliability: ExoPlayer only advanced to the next candidate on
# an explicit player error. Some IPTV servers accept the socket and then never
# deliver a decodable first video frame, leaving a permanent black screen.
# Add a first-frame watchdog for LIVE. If no rendered frame appears in 6.5 s,
# automatically try the next candidate URL.
# ---------------------------------------------------------------------------
player = java / "ui/PlayerScreen.kt"
s = player.read_text()

if 'import android.os.Handler\n' not in s:
    if 'import android.view.KeyEvent\n' not in s:
        raise SystemExit("KeyEvent import anchor missing")
    s = s.replace('import android.view.KeyEvent\n', 'import android.os.Handler\nimport android.os.Looper\nimport android.view.KeyEvent\n', 1)

old_active = '''        player.trackSelectionParameters = params
        var activeUrl = 0
        fun openUrl(index: Int) {
            activeUrl = index
            playbackError = ""
            player.setMediaItem(MediaItem.fromUri(playbackUrls[index]))
            player.prepare()
            player.playWhenReady = true
        }
'''
new_active = '''        player.trackSelectionParameters = params
        var activeUrl = 0
        var firstFrameRendered = false
        val watchdogHandler = Handler(Looper.getMainLooper())
        var watchdogRunnable: Runnable? = null

        fun cancelWatchdog() {
            watchdogRunnable?.let { watchdogHandler.removeCallbacks(it) }
            watchdogRunnable = null
        }

        fun openUrl(index: Int) {
            activeUrl = index
            firstFrameRendered = false
            cancelWatchdog()
            playbackError = ""
            player.setMediaItem(MediaItem.fromUri(playbackUrls[index]))
            player.prepare()
            player.playWhenReady = true
            if (item.kind == MediaKind.LIVE) {
                val attempt = index
                watchdogRunnable = Runnable {
                    if (!firstFrameRendered && activeUrl == attempt) {
                        val next = attempt + 1
                        if (next < playbackUrls.size) {
                            openUrl(next)
                        } else {
                            playbackError = "Live-Stream verbunden, aber kein Videobild empfangen. Alle Stream-Varianten wurden getestet."
                        }
                    }
                }.also { watchdogHandler.postDelayed(it, 6500L) }
            }
        }
'''
if old_active not in s:
    raise SystemExit("player active URL anchor missing")
s = s.replace(old_active, new_active, 1)

old_listener = '''        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) save()
            }
            override fun onPlayerError(error: PlaybackException) {
                val next = activeUrl + 1
                if (next < playbackUrls.size) {
                    openUrl(next)
                } else {
                    playbackError = "Der Anbieter hat alle kompatiblen Stream-Adressen abgelehnt (${error.errorCodeName})."
                }
            }
        }
'''
new_listener = '''        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) save()
            }
            override fun onRenderedFirstFrame() {
                firstFrameRendered = true
                cancelWatchdog()
            }
            override fun onPlayerError(error: PlaybackException) {
                cancelWatchdog()
                val next = activeUrl + 1
                if (next < playbackUrls.size) {
                    openUrl(next)
                } else {
                    playbackError = "Der Anbieter hat alle kompatiblen Stream-Adressen abgelehnt (${error.errorCodeName})."
                }
            }
        }
'''
if old_listener not in s:
    raise SystemExit("player listener anchor missing")
s = s.replace(old_listener, new_listener, 1)

old_dispose = '''        onDispose {
            save()
            player.removeListener(listener)
            player.release()
        }
'''
new_dispose = '''        onDispose {
            cancelWatchdog()
            save()
            player.removeListener(listener)
            player.release()
        }
'''
if old_dispose not in s:
    raise SystemExit("player dispose anchor missing")
s = s.replace(old_dispose, new_dispose, 1)

player.write_text(s)

# Sanity markers.
xf = xtream.read_text()
pf = player.read_text()
for marker in [
    'm3uPrefetching',
    'prefetchExactM3uAsync()',
    'Epi-Xtream-M3U-Prefetch',
    'cachedExactM3uUrl(id)',
]:
    if marker not in xf:
        raise SystemExit(f"missing hotfix3 Xtream marker: {marker}")
if 'val exactM3u = if (kind == MediaKind.LIVE || kind == MediaKind.MOVIE) exactM3uStreamUrls()' in xf:
    raise SystemExit("blocking Live/VOD exact-M3U load still present")
for marker in [
    'Handler(Looper.getMainLooper())',
    'onRenderedFirstFrame()',
    'postDelayed(it, 6500L)',
    'Live-Stream verbunden, aber kein Videobild empfangen',
]:
    if marker not in pf:
        raise SystemExit(f"missing hotfix3 player marker: {marker}")

print("Android v0.6.4.3 fast-list + Live first-frame watchdog hotfix applied")
