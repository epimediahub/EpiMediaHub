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


# Version metadata.
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 603', 'versionCode = 604', 'versionCode')
replace_once(gradle, 'versionName = "0.6.3"', 'versionName = "0.6.4"', 'versionName')
home = java / "ui/V044Home.kt"
home_text = home.read_text()
if "0.6.3" not in home_text:
    raise SystemExit("visible home version 0.6.3 not found")
home.write_text(home_text.replace("0.6.3", "0.6.4"))


# Xtream providers may expose the API on one host/port and media on another.
# Resolve server_info once while we are already on an IO dispatcher, remember it
# process-wide for the profile, and keep the configured portal as a fallback.
xtream = java / "data/XtreamClient.kt"
s = xtream.read_text()

class_anchor = 'class XtreamClient(private val p: PlaylistProfile) {\n'
if class_anchor not in s:
    raise SystemExit("XtreamClient class anchor missing")
resolver = r'''class XtreamClient(private val p: PlaylistProfile) {
    companion object {
        private val streamServerCache = java.util.concurrent.ConcurrentHashMap<String, String>()
    }

    private fun streamServerKey() = "${p.server.trimEnd('/')}|${p.username}"

    private fun cachedStreamServer(): String =
        streamServerCache[streamServerKey()] ?: p.server.trimEnd('/')

    private fun resolveStreamServer(): String {
        val key = streamServerKey()
        streamServerCache[key]?.let { return it }
        val fallback = p.server.trimEnd('/')
        val resolved = runCatching {
            val authUrl = "$fallback/player_api.php?username=${enc(p.username)}&password=${enc(p.password)}"
            val root = JSONObject(text(authUrl))
            val info = root.optJSONObject("server_info") ?: return@runCatching fallback
            val fallbackUri = Uri.parse(fallback)
            val protocol = info.optString("server_protocol").trim()
                .ifBlank { fallbackUri.scheme ?: "http" }
            val rawUrl = info.optString("url").trim()
                .ifBlank { fallbackUri.host.orEmpty() }
            if (rawUrl.isBlank()) return@runCatching fallback
            val withScheme = if (rawUrl.startsWith("http://", true) || rawUrl.startsWith("https://", true)) {
                rawUrl
            } else {
                "$protocol://$rawUrl"
            }
            val uri = Uri.parse(withScheme)
            val scheme = uri.scheme?.lowercase().orEmpty().ifBlank { protocol.lowercase() }
            val host = uri.host ?: return@runCatching fallback
            val preferredPort = when (scheme) {
                "https" -> firstNonBlank(info.optString("https_port"), info.optString("port")).toIntOrNull()
                else -> info.optString("port").trim().toIntOrNull()
            }
            val port = if (uri.port > 0) uri.port else preferredPort ?: -1
            val defaultPort = (scheme == "http" && port == 80) || (scheme == "https" && port == 443)
            val prefixPath = uri.encodedPath.orEmpty().trimEnd('/').takeUnless { it == "/" }.orEmpty()
            buildString {
                append(scheme.ifBlank { "http" }).append("://").append(host)
                if (port > 0 && !defaultPort) append(":").append(port)
                if (prefixPath.isNotBlank()) append(prefixPath)
            }
        }.getOrDefault(fallback).trimEnd('/')
        streamServerCache[key] = resolved
        return resolved
    }
'''
s = s.replace(class_anchor, resolver, 1)

# Candidate generation uses the server_info host if entries() has already resolved it,
# while retaining the configured portal as a full fallback set.
old_candidates = r'''    fun streamCandidates(item: MediaEntry): List<String> {
        val server = p.server.trimEnd('/')
        val user = path(p.username)
        val pass = path(p.password)
        val id = path(item.id)
        val configured = p.output.trim().trimStart('.').ifBlank { "ts" }
        val extension = item.extension.trim().trimStart('.').ifBlank { configured }
        val urls = mutableListOf<String>()
        if (item.streamUrl.isNotBlank()) urls += item.streamUrl
        when (item.kind) {
            MediaKind.LIVE -> {
                val extensions = listOf(configured, "ts", "m3u8").distinct()
                extensions.forEach { ext ->
                    urls += "$server/live/$user/$pass/$id.$ext"
                    urls += "$server/$user/$pass/$id.$ext"
                }
                urls += "$server/live/$user/$pass/$id"
                urls += "$server/$user/$pass/$id"
            }
            MediaKind.MOVIE -> urls += "$server/movie/$user/$pass/$id.$extension"
            MediaKind.EPISODE -> urls += "$server/series/$user/$pass/$id.$extension"
            else -> Unit
        }
        return urls.filter { it.isNotBlank() }.distinct()
    }
'''
new_candidates = r'''    fun streamCandidates(item: MediaEntry): List<String> {
        val user = path(p.username)
        val pass = path(p.password)
        val id = path(item.id)
        val configured = p.output.trim().trimStart('.').ifBlank { "ts" }
        val extension = item.extension.trim().trimStart('.').ifBlank { configured }
        val servers = listOf(cachedStreamServer(), p.server.trimEnd('/')).filter { it.isNotBlank() }.distinct()
        val urls = mutableListOf<String>()
        if (item.streamUrl.isNotBlank()) urls += item.streamUrl
        servers.forEach { server ->
            when (item.kind) {
                MediaKind.LIVE -> {
                    val extensions = listOf(configured, "ts", "m3u8").distinct()
                    extensions.forEach { ext ->
                        urls += "$server/live/$user/$pass/$id.$ext"
                        urls += "$server/$user/$pass/$id.$ext"
                    }
                    urls += "$server/live/$user/$pass/$id"
                    urls += "$server/$user/$pass/$id"
                }
                MediaKind.MOVIE -> urls += "$server/movie/$user/$pass/$id.$extension"
                MediaKind.EPISODE -> urls += "$server/series/$user/$pass/$id.$extension"
                else -> Unit
            }
        }
        return urls.filter { it.isNotBlank() && it != "null" }.distinct()
    }
'''
if old_candidates not in s:
    raise SystemExit("streamCandidates anchor missing")
s = s.replace(old_candidates, new_candidates, 1)

# Resolve media host while entries are loaded on Dispatchers.IO.
entries_anchor = '        val a = array(api(action, extra))\n        return buildList {\n'
if entries_anchor not in s:
    raise SystemExit("entries array anchor missing")
s = s.replace(entries_anchor, '        val a = array(api(action, extra))\n        val streamServer = if (kind == MediaKind.LIVE || kind == MediaKind.MOVIE) resolveStreamServer() else cachedStreamServer()\n        return buildList {\n', 1)

old_live_url = '                                streamUrl = "${p.server}/live/${path(p.username)}/${path(p.password)}/${path(id)}.${p.output.trimStart(\'.\')}",\n'
new_live_url = '                                streamUrl = firstNonBlank(o.optString("direct_source"), "$streamServer/live/${path(p.username)}/${path(p.password)}/${path(id)}.${p.output.trimStart(\'.\')}"),\n'
if old_live_url not in s:
    raise SystemExit("live streamUrl anchor missing")
s = s.replace(old_live_url, new_live_url, 1)

old_movie_url = '                                streamUrl = "${p.server}/movie/${path(p.username)}/${path(p.password)}/${path(id)}.$ext",\n'
new_movie_url = '                                streamUrl = firstNonBlank(o.optString("direct_source"), "$streamServer/movie/${path(p.username)}/${path(p.password)}/${path(id)}.$ext"),\n'
if old_movie_url not in s:
    raise SystemExit("movie streamUrl anchor missing")
s = s.replace(old_movie_url, new_movie_url, 1)

# Episodes can also live on the server_info media host.
episodes_anchor = '        val out = mutableListOf<MediaEntry>()\n'
if episodes_anchor not in s:
    raise SystemExit("episodes out anchor missing")
s = s.replace(episodes_anchor, '        val streamServer = resolveStreamServer()\n        val out = mutableListOf<MediaEntry>()\n', 1)
old_episode_url = '                    streamUrl = "${p.server}/series/${path(p.username)}/${path(p.password)}/${path(id)}.$ext",\n'
new_episode_url = '                    streamUrl = firstNonBlank(o.optString("direct_source"), "$streamServer/series/${path(p.username)}/${path(p.password)}/${path(id)}.$ext"),\n'
if old_episode_url not in s:
    raise SystemExit("episode streamUrl anchor missing")
s = s.replace(old_episode_url, new_episode_url, 1)

xtream.write_text(s)

# Sanity checks.
check = xtream.read_text()
required = [
    'streamServerCache',
    'server_info',
    'resolveStreamServer()',
    'o.optString("direct_source")',
    'listOf(cachedStreamServer(), p.server.trimEnd',
]
for marker in required:
    if marker not in check:
        raise SystemExit(f"missing v0.6.4 marker: {marker}")

print("Android v0.6.4 Xtream server_info/direct_source patch applied")
