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


# Visible version.
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 607', 'versionCode = 608', 'hotfix5 versionCode')
replace_once(gradle, 'versionName = "0.6.4.4"', 'versionName = "0.6.4.5"', 'hotfix5 versionName')

home = java / "ui/V044Home.kt"
home_text = home.read_text()
if "0.6.4.4" not in home_text:
    raise SystemExit("visible home version 0.6.4.4 not found")
home.write_text(home_text.replace("0.6.4.4", "0.6.4.5", 1))

# ---------------------------------------------------------------------------
# Xtream provider M3U: preserve IPTV request headers. Providers commonly encode
# them either as URL|User-Agent=...&Referer=... or as #EXTVLCOPT / #EXTHTTP
# lines. ExoPlayer does not interpret those conventions itself.
# ---------------------------------------------------------------------------
xtream = java / "data/XtreamClient.kt"
s = xtream.read_text()
old = '''        val resolved = runCatching {
            val out = LinkedHashMap<String, String>()
            text(providerM3uUrl()).lineSequence().forEach { line ->
                val url = line.trim()
                if (url.startsWith("http://", true) || url.startsWith("https://", true)) {
                    val id = idFromProviderStreamUrl(url)
                    if (id.isNotBlank() && id !in out) out[id] = url
                }
            }
            out.toMap()
        }.getOrDefault(emptyMap())
'''
new = '''        val resolved = runCatching {
            val out = LinkedHashMap<String, String>()
            var pendingUserAgent = ""
            var pendingReferer = ""
            var pendingOrigin = ""
            fun resetHeaders() {
                pendingUserAgent = ""
                pendingReferer = ""
                pendingOrigin = ""
            }
            text(providerM3uUrl()).lineSequence().forEach { rawLine ->
                val line = rawLine.trim()
                when {
                    line.startsWith("#EXTINF", true) -> resetHeaders()
                    line.startsWith("#EXTVLCOPT:http-user-agent=", true) -> pendingUserAgent = line.substringAfter('=', "").trim()
                    line.startsWith("#EXTVLCOPT:http-referrer=", true) || line.startsWith("#EXTVLCOPT:http-referer=", true) -> pendingReferer = line.substringAfter('=', "").trim()
                    line.startsWith("#EXTVLCOPT:http-origin=", true) -> pendingOrigin = line.substringAfter('=', "").trim()
                    line.startsWith("#EXTHTTP:", true) -> {
                        runCatching { JSONObject(line.substringAfter(':').trim()) }.getOrNull()?.let { h ->
                            pendingUserAgent = firstNonBlank(h.optString("User-Agent"), h.optString("user-agent"), pendingUserAgent)
                            pendingReferer = firstNonBlank(h.optString("Referer"), h.optString("Referrer"), h.optString("referer"), pendingReferer)
                            pendingOrigin = firstNonBlank(h.optString("Origin"), h.optString("origin"), pendingOrigin)
                        }
                    }
                    line.startsWith("http://", true) || line.startsWith("https://", true) -> {
                        val baseUrl = line.substringBefore('|').trim()
                        val existingOptions = line.substringAfter('|', "").trim()
                        val options = mutableListOf<String>()
                        if (existingOptions.isNotBlank()) options += existingOptions
                        if (pendingUserAgent.isNotBlank() && !existingOptions.contains("user-agent=", true)) options += "User-Agent=${enc(pendingUserAgent)}"
                        if (pendingReferer.isNotBlank() && !existingOptions.contains("referer=", true) && !existingOptions.contains("referrer=", true)) options += "Referer=${enc(pendingReferer)}"
                        if (pendingOrigin.isNotBlank() && !existingOptions.contains("origin=", true)) options += "Origin=${enc(pendingOrigin)}"
                        val playable = if (options.isEmpty()) baseUrl else baseUrl + "|" + options.joinToString("&")
                        val id = idFromProviderStreamUrl(baseUrl)
                        if (id.isNotBlank() && id !in out) out[id] = playable
                        resetHeaders()
                    }
                }
            }
            out.toMap()
        }.getOrDefault(emptyMap())
'''
if old not in s:
    raise SystemExit("exact M3U parsing anchor missing")
s = s.replace(old, new, 1)
xtream.write_text(s)

# ---------------------------------------------------------------------------
# Generic M3U parser: retain the same header conventions for direct M3U lists.
# Store them in the standard IPTV URL|Header=Value convention; PlayerScreen
# below interprets it before handing the real URL to ExoPlayer.
# ---------------------------------------------------------------------------
m3u = java / "data/M3uParser.kt"
s = m3u.read_text()
if 'import java.net.URLEncoder\n' not in s:
    s = s.replace('import java.net.URL\n', 'import java.net.URL\nimport java.net.URLEncoder\n', 1)
old_vars = '''        var meta = ""
        var idx = 0
        var epgUrl = ""
'''
new_vars = '''        var meta = ""
        var idx = 0
        var epgUrl = ""
        var pendingUserAgent = ""
        var pendingReferer = ""
        var pendingOrigin = ""
        fun encHeader(value: String) = URLEncoder.encode(value, "UTF-8")
        fun resetHeaders() {
            pendingUserAgent = ""
            pendingReferer = ""
            pendingOrigin = ""
        }
'''
if old_vars not in s:
    raise SystemExit("M3uParser state anchor missing")
s = s.replace(old_vars, new_vars, 1)
old_when = '''                line.startsWith("#EXTM3U", true) -> epgUrl = attr(line, "url-tvg").ifBlank { attr(line, "x-tvg-url") }
                line.startsWith("#EXTINF", true) -> meta = line
                line.isNotBlank() && !line.startsWith("#") && meta.isNotBlank() -> {
                    val name = meta.substringAfterLast(',', attr(meta, "tvg-name").ifBlank { "Sender ${idx + 1}" }).trim()
                    val group = attr(meta, "group-title").ifBlank { "Andere" }
                    out += MediaEntry(
                        id = "m3u_${idx++}", name = name, kind = MediaKind.LIVE, categoryId = group,
                        image = attr(meta, "tvg-logo"), streamUrl = line,
                        epgId = attr(meta, "tvg-id").ifBlank { attr(meta, "tvg-name") }
                    )
                    meta = ""
                }
'''
new_when = '''                line.startsWith("#EXTM3U", true) -> epgUrl = attr(line, "url-tvg").ifBlank { attr(line, "x-tvg-url") }
                line.startsWith("#EXTINF", true) -> { meta = line; resetHeaders() }
                line.startsWith("#EXTVLCOPT:http-user-agent=", true) -> pendingUserAgent = line.substringAfter('=', "").trim()
                line.startsWith("#EXTVLCOPT:http-referrer=", true) || line.startsWith("#EXTVLCOPT:http-referer=", true) -> pendingReferer = line.substringAfter('=', "").trim()
                line.startsWith("#EXTVLCOPT:http-origin=", true) -> pendingOrigin = line.substringAfter('=', "").trim()
                line.startsWith("#EXTHTTP:", true) -> {
                    runCatching { org.json.JSONObject(line.substringAfter(':').trim()) }.getOrNull()?.let { h ->
                        pendingUserAgent = h.optString("User-Agent").ifBlank { h.optString("user-agent") }.ifBlank { pendingUserAgent }
                        pendingReferer = h.optString("Referer").ifBlank { h.optString("Referrer") }.ifBlank { h.optString("referer") }.ifBlank { pendingReferer }
                        pendingOrigin = h.optString("Origin").ifBlank { h.optString("origin") }.ifBlank { pendingOrigin }
                    }
                }
                line.isNotBlank() && !line.startsWith("#") && meta.isNotBlank() -> {
                    val name = meta.substringAfterLast(',', attr(meta, "tvg-name").ifBlank { "Sender ${idx + 1}" }).trim()
                    val group = attr(meta, "group-title").ifBlank { "Andere" }
                    val baseUrl = line.substringBefore('|').trim()
                    val existingOptions = line.substringAfter('|', "").trim()
                    val options = mutableListOf<String>()
                    if (existingOptions.isNotBlank()) options += existingOptions
                    if (pendingUserAgent.isNotBlank() && !existingOptions.contains("user-agent=", true)) options += "User-Agent=${encHeader(pendingUserAgent)}"
                    if (pendingReferer.isNotBlank() && !existingOptions.contains("referer=", true) && !existingOptions.contains("referrer=", true)) options += "Referer=${encHeader(pendingReferer)}"
                    if (pendingOrigin.isNotBlank() && !existingOptions.contains("origin=", true)) options += "Origin=${encHeader(pendingOrigin)}"
                    val playable = if (options.isEmpty()) baseUrl else baseUrl + "|" + options.joinToString("&")
                    out += MediaEntry(
                        id = "m3u_${idx++}", name = name, kind = MediaKind.LIVE, categoryId = group,
                        image = attr(meta, "tvg-logo"), streamUrl = playable,
                        epgId = attr(meta, "tvg-id").ifBlank { attr(meta, "tvg-name") }
                    )
                    meta = ""
                    resetHeaders()
                }
'''
if old_when not in s:
    raise SystemExit("M3uParser when anchor missing")
s = s.replace(old_when, new_when, 1)
m3u.write_text(s)

# ---------------------------------------------------------------------------
# Player: split IPTV pipe options away from the HTTP URL and apply them as real
# HTTP headers to DefaultHttpDataSource before every candidate is prepared.
# ---------------------------------------------------------------------------
player = java / "ui/PlayerScreen.kt"
s = player.read_text()
if 'import java.net.URLDecoder\n' not in s:
    anchor = 'import kotlinx.coroutines.delay\n'
    if anchor not in s:
        raise SystemExit("delay import anchor missing")
    s = s.replace(anchor, anchor + 'import java.net.URLDecoder\n', 1)

composable_anchor = '''@OptIn(UnstableApi::class)
@Composable
fun PlayerScreen'''
helpers = '''private data class IptvHttpRequest(
    val url: String,
    val userAgent: String = "",
    val referer: String = "",
    val origin: String = ""
)

private fun parseIptvHttpRequest(raw: String): IptvHttpRequest {
    val url = raw.substringBefore('|').trim()
    val options = raw.substringAfter('|', "").trim()
    if (options.isBlank()) return IptvHttpRequest(url)
    var userAgent = ""
    var referer = ""
    var origin = ""
    options.split('&').forEach { token ->
        val rawKey = token.substringBefore('=', "").trim()
        val rawValue = token.substringAfter('=', "").trim()
        if (rawKey.isBlank() || rawValue.isBlank()) return@forEach
        val key = runCatching { URLDecoder.decode(rawKey, "UTF-8") }.getOrDefault(rawKey)
        val value = runCatching { URLDecoder.decode(rawValue, "UTF-8") }.getOrDefault(rawValue)
        when (key.lowercase()) {
            "user-agent", "http-user-agent" -> userAgent = value
            "referer", "referrer", "http-referrer", "http-referer" -> referer = value
            "origin", "http-origin" -> origin = value
        }
    }
    return IptvHttpRequest(url, userAgent, referer, origin)
}

@OptIn(UnstableApi::class)
@Composable
fun PlayerScreen'''
if composable_anchor not in s:
    raise SystemExit("PlayerScreen helper anchor missing")
s = s.replace(composable_anchor, helpers, 1)

old_player = '''    val player = remember(item.resumeKey) {
        val httpFactory = DefaultHttpDataSource.Factory()
            .setUserAgent("VLC/3.0.21 LibVLC/3.0.21")
            .setAllowCrossProtocolRedirects(true)
        ExoPlayer.Builder(context)
            .setMediaSourceFactory(DefaultMediaSourceFactory(context).setDataSourceFactory(httpFactory))
            .build()
    }
'''
new_player = '''    val playbackEngine = remember(item.resumeKey, item.streamUrl) {
        val httpFactory = DefaultHttpDataSource.Factory()
            .setUserAgent("VLC/3.0.21 LibVLC/3.0.21")
            .setAllowCrossProtocolRedirects(true)
        val exo = ExoPlayer.Builder(context)
            .setMediaSourceFactory(DefaultMediaSourceFactory(context).setDataSourceFactory(httpFactory))
            .build()
        httpFactory to exo
    }
    val httpFactory = playbackEngine.first
    val player = playbackEngine.second
'''
if old_player not in s:
    raise SystemExit("Player factory anchor missing")
s = s.replace(old_player, new_player, 1)

old_set = '''            playbackError = ""
            player.setMediaItem(MediaItem.fromUri(playbackUrls[index]))
            player.prepare()
'''
new_set = '''            playbackError = ""
            val request = parseIptvHttpRequest(playbackUrls[index])
            httpFactory.setUserAgent(request.userAgent.ifBlank { "VLC/3.0.21 LibVLC/3.0.21" })
            val requestHeaders = linkedMapOf<String, String>()
            if (request.referer.isNotBlank()) requestHeaders["Referer"] = request.referer
            if (request.origin.isNotBlank()) requestHeaders["Origin"] = request.origin
            httpFactory.setDefaultRequestProperties(requestHeaders)
            player.setMediaItem(MediaItem.fromUri(request.url))
            player.prepare()
'''
if old_set not in s:
    raise SystemExit("Player setMediaItem anchor missing")
s = s.replace(old_set, new_set, 1)
player.write_text(s)

# Sanity.
checks = [
    (gradle, 'versionName = "0.6.4.5"'),
    (gradle, 'versionCode = 608'),
    (xtream, '#EXTVLCOPT:http-user-agent='),
    (xtream, '#EXTHTTP:'),
    (m3u, 'val playable = if (options.isEmpty()) baseUrl else baseUrl + "|"'),
    (player, 'private fun parseIptvHttpRequest(raw: String)'),
    (player, 'httpFactory.setDefaultRequestProperties(requestHeaders)'),
    (player, 'player.setMediaItem(MediaItem.fromUri(request.url))'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing hotfix5 marker {marker} in {path}")

print("Android v0.6.4.5 IPTV M3U header compatibility hotfix applied")
