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
# Xtream hotfix: prefer exact provider M3U URLs and retain raw path variants.
# ---------------------------------------------------------------------------
xtream = java / "data/XtreamClient.kt"
s = xtream.read_text()

old_companion = '''    companion object {
        private val streamServerCache = java.util.concurrent.ConcurrentHashMap<String, String>()
    }
'''
new_companion = '''    companion object {
        private val streamServerCache = java.util.concurrent.ConcurrentHashMap<String, String>()
        private val m3uStreamUrlCache = java.util.concurrent.ConcurrentHashMap<String, Map<String, String>>()
    }
'''
if old_companion not in s:
    raise SystemExit("Xtream companion cache anchor missing")
s = s.replace(old_companion, new_companion, 1)

resolver_end = '''        streamServerCache[key] = resolved
        return resolved
    }
'''
if resolver_end not in s:
    raise SystemExit("stream server resolver end anchor missing")

m3u_helpers = r'''        streamServerCache[key] = resolved
        return resolved
    }

    private fun m3uStreamKey() = "${p.server.trimEnd('/')}|${p.username}|${p.output}"

    private fun providerM3uUrl(): String {
        val original = p.originalUrl.trim()
        if (original.contains("get.php", ignoreCase = true)) return original
        return "${p.server.trimEnd('/')}/get.php?username=${enc(p.username)}&password=${enc(p.password)}&type=m3u_plus&output=${enc(p.output.ifBlank { "ts" })}"
    }

    private fun idFromProviderStreamUrl(raw: String): String {
        val uri = runCatching { Uri.parse(raw) }.getOrNull() ?: return ""
        listOf("stream_id", "stream", "id").forEach { key ->
            val value = uri.getQueryParameter(key).orEmpty().trim()
            if (value.isNotBlank()) return value
        }
        val last = uri.lastPathSegment.orEmpty().trim()
        if (last.isBlank()) return ""
        val withoutExt = last.substringBeforeLast('.', last)
        return withoutExt.ifBlank { last }
    }

    private fun exactM3uStreamUrls(): Map<String, String> {
        val key = m3uStreamKey()
        m3uStreamUrlCache[key]?.let { return it }
        val resolved = runCatching {
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
        m3uStreamUrlCache[key] = resolved
        return resolved
    }

    private fun cachedExactM3uUrl(streamId: String): String =
        m3uStreamUrlCache[m3uStreamKey()]?.get(streamId).orEmpty()
'''
s = s.replace(resolver_end, m3u_helpers, 1)

old_candidate_head = '''    fun streamCandidates(item: MediaEntry): List<String> {
        val user = path(p.username)
        val pass = path(p.password)
        val id = path(item.id)
        val configured = p.output.trim().trimStart('.').ifBlank { "ts" }
        val extension = item.extension.trim().trimStart('.').ifBlank { configured }
        val servers = listOf(cachedStreamServer(), p.server.trimEnd('/')).filter { it.isNotBlank() }.distinct()
        val urls = mutableListOf<String>()
        if (item.streamUrl.isNotBlank()) urls += item.streamUrl
'''
new_candidate_head = '''    fun streamCandidates(item: MediaEntry): List<String> {
        val user = path(p.username)
        val pass = path(p.password)
        val id = path(item.id)
        val rawUser = p.username.trim()
        val rawPass = p.password
        val rawId = item.id.trim()
        val configured = p.output.trim().trimStart('.').ifBlank { "ts" }
        val extension = item.extension.trim().trimStart('.').ifBlank { configured }
        val servers = listOf(cachedStreamServer(), p.server.trimEnd('/')).filter { it.isNotBlank() }.distinct()
        val urls = mutableListOf<String>()
        cachedExactM3uUrl(item.id).takeIf { it.isNotBlank() }?.let { urls += it }
        if (item.streamUrl.isNotBlank()) urls += item.streamUrl
'''
if old_candidate_head not in s:
    raise SystemExit("streamCandidates hotfix anchor missing")
s = s.replace(old_candidate_head, new_candidate_head, 1)

old_live_block = '''                    extensions.forEach { ext ->
                        urls += "$server/live/$user/$pass/$id.$ext"
                        urls += "$server/$user/$pass/$id.$ext"
                    }
                    urls += "$server/live/$user/$pass/$id"
                    urls += "$server/$user/$pass/$id"
'''
new_live_block = '''                    extensions.forEach { ext ->
                        urls += "$server/live/$user/$pass/$id.$ext"
                        urls += "$server/$user/$pass/$id.$ext"
                        if (rawUser.isNotBlank() && rawPass.isNotBlank() && rawId.isNotBlank()) {
                            urls += "$server/live/$rawUser/$rawPass/$rawId.$ext"
                            urls += "$server/$rawUser/$rawPass/$rawId.$ext"
                        }
                    }
                    urls += "$server/live/$user/$pass/$id"
                    urls += "$server/$user/$pass/$id"
                    if (rawUser.isNotBlank() && rawPass.isNotBlank() && rawId.isNotBlank()) {
                        urls += "$server/live/$rawUser/$rawPass/$rawId"
                        urls += "$server/$rawUser/$rawPass/$rawId"
                    }
'''
if old_live_block not in s:
    raise SystemExit("Live candidate fallback block missing")
s = s.replace(old_live_block, new_live_block, 1)

old_entries_prelude = '''        val a = array(api(action, extra))
        val streamServer = if (kind == MediaKind.LIVE || kind == MediaKind.MOVIE) resolveStreamServer() else cachedStreamServer()
        return buildList {
'''
new_entries_prelude = '''        val a = array(api(action, extra))
        val streamServer = if (kind == MediaKind.LIVE || kind == MediaKind.MOVIE) resolveStreamServer() else cachedStreamServer()
        val exactM3u = if (kind == MediaKind.LIVE || kind == MediaKind.MOVIE) exactM3uStreamUrls() else emptyMap()
        return buildList {
'''
if old_entries_prelude not in s:
    raise SystemExit("entries hotfix prelude missing")
s = s.replace(old_entries_prelude, new_entries_prelude, 1)

old_live_url = '''                                streamUrl = firstNonBlank(o.optString("direct_source"), "$streamServer/live/${path(p.username)}/${path(p.password)}/${path(id)}.${p.output.trimStart('.')}"),
'''
new_live_url = '''                                streamUrl = firstNonBlank(exactM3u[id].orEmpty(), o.optString("direct_source"), "$streamServer/live/${path(p.username)}/${path(p.password)}/${path(id)}.${p.output.trimStart('.')}"),
'''
if old_live_url not in s:
    raise SystemExit("live exact-M3U anchor missing")
s = s.replace(old_live_url, new_live_url, 1)

old_movie_url = '''                                streamUrl = firstNonBlank(o.optString("direct_source"), "$streamServer/movie/${path(p.username)}/${path(p.password)}/${path(id)}.$ext"),
'''
new_movie_url = '''                                streamUrl = firstNonBlank(exactM3u[id].orEmpty(), o.optString("direct_source"), "$streamServer/movie/${path(p.username)}/${path(p.password)}/${path(id)}.$ext"),
'''
if old_movie_url not in s:
    raise SystemExit("movie exact-M3U anchor missing")
s = s.replace(old_movie_url, new_movie_url, 1)

old_episode_prelude = '''        val streamServer = resolveStreamServer()
        val out = mutableListOf<MediaEntry>()
'''
new_episode_prelude = '''        val streamServer = resolveStreamServer()
        val exactM3u = exactM3uStreamUrls()
        val out = mutableListOf<MediaEntry>()
'''
if old_episode_prelude not in s:
    raise SystemExit("episode exact-M3U prelude missing")
s = s.replace(old_episode_prelude, new_episode_prelude, 1)

old_episode_url = '''                    streamUrl = firstNonBlank(o.optString("direct_source"), "$streamServer/series/${path(p.username)}/${path(p.password)}/${path(id)}.$ext"),
'''
new_episode_url = '''                    streamUrl = firstNonBlank(exactM3u[id].orEmpty(), o.optString("direct_source"), "$streamServer/series/${path(p.username)}/${path(p.password)}/${path(id)}.$ext"),
'''
if old_episode_url not in s:
    raise SystemExit("episode exact-M3U anchor missing")
s = s.replace(old_episode_url, new_episode_url, 1)

xtream.write_text(s)

# ---------------------------------------------------------------------------
# Playback HTTP compatibility: IPTV/VLC-like User-Agent and redirect handling.
# ---------------------------------------------------------------------------
player = java / "ui/PlayerScreen.kt"
s = player.read_text()
if 'import androidx.media3.datasource.DefaultHttpDataSource\n' not in s:
    if 'import androidx.media3.exoplayer.ExoPlayer\n' not in s:
        raise SystemExit("ExoPlayer import anchor missing")
    s = s.replace(
        'import androidx.media3.exoplayer.ExoPlayer\n',
        'import androidx.media3.exoplayer.ExoPlayer\nimport androidx.media3.datasource.DefaultHttpDataSource\nimport androidx.media3.exoplayer.source.DefaultMediaSourceFactory\nimport androidx.media3.common.util.UnstableApi\n',
        1,
    )

if '@OptIn(UnstableApi::class)\n@Composable\nfun PlayerScreen' not in s:
    anchor = '@Composable\nfun PlayerScreen'
    if anchor not in s:
        raise SystemExit("PlayerScreen composable anchor missing")
    s = s.replace(anchor, '@OptIn(UnstableApi::class)\n' + anchor, 1)

old_player = '    val player = remember(item.resumeKey) { ExoPlayer.Builder(context).build() }\n'
new_player = '''    val player = remember(item.resumeKey) {
        val httpFactory = DefaultHttpDataSource.Factory()
            .setUserAgent("VLC/3.0.21 LibVLC/3.0.21")
            .setAllowCrossProtocolRedirects(true)
        ExoPlayer.Builder(context)
            .setMediaSourceFactory(DefaultMediaSourceFactory(context).setDataSourceFactory(httpFactory))
            .build()
    }
'''
if old_player not in s:
    raise SystemExit("Player construction anchor missing")
s = s.replace(old_player, new_player, 1)
player.write_text(s)

# Sanity markers.
xf = xtream.read_text()
pf = player.read_text()
for marker in [
    'm3uStreamUrlCache',
    'providerM3uUrl()',
    'exactM3uStreamUrls()',
    'cachedExactM3uUrl(item.id)',
    'exactM3u[id].orEmpty()',
    'rawUser',
]:
    if marker not in xf:
        raise SystemExit(f"missing Xtream hotfix marker: {marker}")
for marker in [
    'DefaultHttpDataSource.Factory()',
    'VLC/3.0.21 LibVLC/3.0.21',
    'setAllowCrossProtocolRedirects(true)',
    '@OptIn(UnstableApi::class)',
]:
    if marker not in pf:
        raise SystemExit(f"missing player hotfix marker: {marker}")

print("Android v0.6.4 Xtream exact-M3U/User-Agent hotfix applied")
