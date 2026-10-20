#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def require_once(text: str, needle: str, label: str):
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")


def function_span(text: str, signature: str):
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"function not found: {signature}")
    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"opening brace missing: {signature}")
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise SystemExit(f"closing brace missing: {signature}")


# ---------------------------------------------------------------------------
# Version.
# ---------------------------------------------------------------------------
build = root / "app/build.gradle.kts"
s = build.read_text()
require_once(s, 'versionCode = 617', 'v0.6.4.14 versionCode')
require_once(s, 'versionName = "0.6.4.14"', 'v0.6.4.14 versionName')
s = s.replace('versionCode = 617', 'versionCode = 618', 1)
s = s.replace('versionName = "0.6.4.14"', 'versionName = "0.6.4.15"', 1)
build.write_text(s)

for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.6.4.14", "0.6.4.15"))


# ---------------------------------------------------------------------------
# Generic M3U memory fix.
#
# v0.6.4.14 removed the giant Xtream fallback-M3U read, but a playlist that is
# actually configured as M3U still used BufferedReader.readText(). A provider
# list around 160+ MB therefore reproduced the exact same OOM. Parse line by
# line instead. Explicit Xtream VOD/series paths are skipped in generic M3U
# live mode so they do not fill the TV heap with entries the M3U UI cannot use.
# ---------------------------------------------------------------------------
m3u = java / "data/M3uParser.kt"
m3u.write_text(r'''package de.epimediahub.app.data

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import java.io.BufferedReader
import java.io.Reader
import java.io.StringReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.Locale

object M3uParser {
    data class Result(val entries: List<MediaEntry>, val groups: List<String>, val epgUrl: String = "")

    private const val DEFAULT_STREAM_UA = "VLC/3.0.20 LibVLC/3.0.20"

    fun download(url: String): Result {
        val c = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 12000
            readTimeout = 30000
            useCaches = false
            instanceFollowRedirects = true
            setRequestProperty("Accept", "*/*")
            setRequestProperty("User-Agent", DEFAULT_STREAM_UA)
        }
        return try {
            val status = c.responseCode
            if (status !in 200..299) throw IllegalStateException("M3U HTTP $status")
            c.inputStream.bufferedReader(Charsets.UTF_8).use { parseReader(it) }
        } finally {
            c.disconnect()
        }
    }

    fun parse(text: String): Result = StringReader(text).use { parseReader(it) }

    private fun parseReader(reader: Reader): Result {
        val input = if (reader is BufferedReader) reader else reader.buffered()
        val out = mutableListOf<MediaEntry>()
        val groups = linkedSetOf<String>()
        var meta = ""
        var idx = 0
        var epgUrl = ""
        var pendingUserAgent = DEFAULT_STREAM_UA
        var pendingReferer = ""
        var pendingOrigin = ""

        fun encHeader(value: String) = URLEncoder.encode(value, "UTF-8")
        fun resetHeaders() {
            pendingUserAgent = DEFAULT_STREAM_UA
            pendingReferer = ""
            pendingOrigin = ""
        }
        fun attr(line: String, key: String) = Regex("$key=\\\"([^\\\"]*)\\\"", RegexOption.IGNORE_CASE)
            .find(line)?.groupValues?.getOrNull(1).orEmpty()

        while (true) {
            val raw = input.readLine() ?: break
            val line = raw.trim()
            when {
                line.startsWith("#EXTM3U", true) ->
                    epgUrl = attr(line, "url-tvg").ifBlank { attr(line, "x-tvg-url") }
                line.startsWith("#EXTINF", true) -> {
                    meta = line
                    resetHeaders()
                }
                line.startsWith("#EXTVLCOPT:http-user-agent=", true) ->
                    pendingUserAgent = line.substringAfter('=', "").trim().ifBlank { DEFAULT_STREAM_UA }
                line.startsWith("#EXTVLCOPT:http-referrer=", true) || line.startsWith("#EXTVLCOPT:http-referer=", true) ->
                    pendingReferer = line.substringAfter('=', "").trim()
                line.startsWith("#EXTVLCOPT:http-origin=", true) ->
                    pendingOrigin = line.substringAfter('=', "").trim()
                line.startsWith("#EXTHTTP:", true) -> {
                    runCatching { org.json.JSONObject(line.substringAfter(':').trim()) }.getOrNull()?.let { h ->
                        pendingUserAgent = h.optString("User-Agent")
                            .ifBlank { h.optString("user-agent") }
                            .ifBlank { pendingUserAgent }
                        pendingReferer = h.optString("Referer")
                            .ifBlank { h.optString("Referrer") }
                            .ifBlank { h.optString("referer") }
                            .ifBlank { pendingReferer }
                        pendingOrigin = h.optString("Origin").ifBlank { h.optString("origin") }.ifBlank { pendingOrigin }
                    }
                }
                line.isNotBlank() && !line.startsWith("#") && meta.isNotBlank() -> {
                    val baseUrl = line.substringBefore('|').trim()
                    val path = runCatching { URL(baseUrl).path.lowercase(Locale.ROOT) }
                        .getOrDefault(baseUrl.lowercase(Locale.ROOT))
                    val explicitVod = path.contains("/movie/") || path.contains("/series/")
                    if (!explicitVod) {
                        val name = meta.substringAfterLast(',', attr(meta, "tvg-name").ifBlank { "Sender ${idx + 1}" }).trim()
                        val group = attr(meta, "group-title").ifBlank { "Andere" }
                        val existingOptions = line.substringAfter('|', "").trim()
                        val options = mutableListOf<String>()
                        if (existingOptions.isNotBlank()) options += existingOptions
                        if (pendingUserAgent.isNotBlank() && !existingOptions.contains("user-agent=", true)) {
                            options += "User-Agent=${encHeader(pendingUserAgent)}"
                        }
                        if (pendingReferer.isNotBlank() && !existingOptions.contains("referer=", true) && !existingOptions.contains("referrer=", true)) {
                            options += "Referer=${encHeader(pendingReferer)}"
                        }
                        if (pendingOrigin.isNotBlank() && !existingOptions.contains("origin=", true)) {
                            options += "Origin=${encHeader(pendingOrigin)}"
                        }
                        val playable = if (options.isEmpty()) baseUrl else baseUrl + "|" + options.joinToString("&")
                        out += MediaEntry(
                            id = "m3u_${idx++}",
                            name = name,
                            kind = MediaKind.LIVE,
                            categoryId = group,
                            image = attr(meta, "tvg-logo"),
                            streamUrl = playable,
                            epgId = attr(meta, "tvg-id").ifBlank { attr(meta, "tvg-name") }
                        )
                        groups += group
                    }
                    meta = ""
                    resetHeaders()
                }
            }
        }
        return Result(out, groups.toList().sorted(), epgUrl)
    }
}
''')


# ---------------------------------------------------------------------------
# Dashboard 0.7 true multi-playlist sync.
#
# Dashboard 0.7 returns config.playlists[] with stable managed-dashboard-* ids.
# v0.6.4.13/14 still read only the legacy top-level config into one fixed
# managed-dashboard profile. Consume the full array, mirror additions/deletions,
# preserve local playlists, and keep the current selection whenever possible.
# Standard Xtream get.php M3U URLs are promoted internally to Xtream so the app
# avoids downloading a huge provider M3U and gets native Live/VOD/Series APIs.
# ---------------------------------------------------------------------------
provision = java / "data/SetupCodeProvisioning.kt"
s = provision.read_text()
s = s.replace('import java.net.URLEncoder\n', 'import java.net.URLEncoder\nimport java.net.URLDecoder\n', 1)
s = s.replace('    private const val MANAGED_PROFILE_ID = "managed-dashboard"\n', '    private const val LEGACY_MANAGED_PROFILE_ID = "managed-dashboard"\n    private const val MANAGED_PROFILE_PREFIX = "managed-dashboard-"\n', 1)

old_mismatch = '''            val localManagedMissing = PrefsRepository(context)
                .loadPlaylists()
                .none { it.id == MANAGED_PROFILE_ID }
            val shouldApply = serverChanged || version != knownVersion || localManagedMissing
'''
require_once(s, old_mismatch, 'single-dashboard-profile mismatch block')
new_mismatch = '''            val remoteManagedIds = managedIds(config)
            val localManagedIds = PrefsRepository(context)
                .loadPlaylists()
                .filter { it.id == LEGACY_MANAGED_PROFILE_ID || it.id.startsWith(MANAGED_PROFILE_PREFIX) }
                .map { it.id }
                .toSet()
            val localManagedMismatch = remoteManagedIds != localManagedIds
            val shouldApply = serverChanged || version != knownVersion || localManagedMismatch
'''
s = s.replace(old_mismatch, new_mismatch, 1)

# Insert Dashboard 0.7 helpers after the complete expression-bodied
# isHttpUrl() implementation. function_span() stops at the closing brace of
# runCatching { ... }, while the original Kotlin function continues with the
# chained .getOrDefault(false). Keeping that chain attached is required for a
# valid Boolean-returning function.
a, b = function_span(s, "    private fun isHttpUrl(value: String)")
tail = '.getOrDefault(false)'
if not s.startswith(tail, b):
    raise SystemExit("isHttpUrl getOrDefault tail missing")
b += len(tail)
helpers = r'''

    private data class DerivedXtream(
        val server: String,
        val username: String,
        val password: String,
        val output: String
    )

    private fun remoteConfigs(config: JSONObject): List<JSONObject> {
        val array = config.optJSONArray("playlists")
        if (array != null) {
            return buildList {
                for (i in 0 until array.length()) array.optJSONObject(i)?.let(::add)
            }
        }
        val legacy = config.optString("playlist_type").isNotBlank() ||
            config.optString("playlist_url").isNotBlank() ||
            config.optString("xtream_server").isNotBlank()
        return if (legacy) listOf(config) else emptyList()
    }

    private fun managedId(item: JSONObject, index: Int): String {
        val serverId = item.optString("id").trim()
        return if (serverId.startsWith(MANAGED_PROFILE_PREFIX)) serverId
        else if (serverId == LEGACY_MANAGED_PROFILE_ID) "$MANAGED_PROFILE_PREFIX${index + 1}"
        else "$MANAGED_PROFILE_PREFIX${serverId.ifBlank { (index + 1).toString() }}"
    }

    private fun managedIds(config: JSONObject): Set<String> =
        remoteConfigs(config).mapIndexed { index, item -> managedId(item, index) }.toSet()

    private fun xtreamFromM3u(value: String): DerivedXtream? = runCatching {
        val url = URL(value)
        if (!url.path.lowercase(Locale.ROOT).endsWith("/get.php") &&
            !url.path.lowercase(Locale.ROOT).endsWith("get.php")) return@runCatching null
        val query = url.query.orEmpty().split('&').mapNotNull { part ->
            val key = part.substringBefore('=', "").trim()
            if (key.isBlank()) null else key.lowercase(Locale.ROOT) to URLDecoder.decode(part.substringAfter('=', ""), "UTF-8")
        }.toMap()
        val username = query["username"].orEmpty().trim()
        val password = query["password"].orEmpty()
        if (username.isBlank() || password.isBlank()) return@runCatching null
        val port = if (url.port > 0 && url.port != url.defaultPort) ":${url.port}" else ""
        val server = "${url.protocol}://${url.host}$port"
        val output = query["output"].orEmpty().ifBlank { "ts" }
        DerivedXtream(server, username, password, output)
    }.getOrNull()
'''
s = s[:b] + helpers + s[b:]

# Replace the legacy one-profile writer.
a, b = function_span(s, "    private fun applyConfigToApp(context: Context, config: JSONObject)")
apply_multi = r'''    private fun applyConfigToApp(context: Context, config: JSONObject): String? {
        val remote = remoteConfigs(config)
        val profiles = mutableListOf<PlaylistProfile>()

        remote.forEachIndexed { index, item ->
            val type = item.optString("playlist_type", "").uppercase(Locale.ROOT)
            val name = item.optString("playlist_name", "EpiMediaHub Dashboard")
                .ifBlank { "EpiMediaHub Dashboard" }
            val id = managedId(item, index)
            val url = item.optString("playlist_url", "").trim()
            val server = item.optString("xtream_server", "").trim().trimEnd('/')
            val username = item.optString("xtream_username", "").trim()
            val password = item.optString("xtream_password", "")
            val output = item.optString("xtream_output", "ts").ifBlank { "ts" }

            when (type) {
                "XTREAM" -> {
                    if (!isHttpUrl(server) || username.isBlank() || password.isBlank()) {
                        return "Dashboard-Xtream-Konfiguration ist unvollständig"
                    }
                    profiles += PlaylistProfile(id, name, "", PlaylistType.XTREAM, server, username, password, output)
                }
                "M3U" -> {
                    if (!isHttpUrl(url)) return "Dashboard-M3U-Konfiguration ist ungültig"
                    val derived = xtreamFromM3u(url)
                    profiles += if (derived != null) {
                        PlaylistProfile(
                            id, name, url, PlaylistType.XTREAM,
                            derived.server, derived.username, derived.password, derived.output
                        )
                    } else {
                        PlaylistProfile(id, name, url, PlaylistType.M3U)
                    }
                }
                else -> return "Dashboard-Konfiguration enthält keinen unterstützten Playlist-Typ"
            }
        }

        return try {
            val repo = PrefsRepository(context)
            val previousActive = repo.activePlaylistId
            val local = repo.loadPlaylists().filterNot {
                it.id == LEGACY_MANAGED_PROFILE_ID || it.id.startsWith(MANAGED_PROFILE_PREFIX)
            }
            val merged = profiles + local
            repo.savePlaylists(merged)

            val requestedActive = config.optString("active_playlist_id").trim()
            repo.activePlaylistId = when {
                merged.any { it.id == previousActive } -> previousActive
                requestedActive.isNotBlank() && merged.any { it.id == requestedActive } -> requestedActive
                profiles.isNotEmpty() -> profiles.first().id
                local.isNotEmpty() -> local.first().id
                else -> ""
            }
            null
        } catch (_: Exception) {
            "Dashboard-Konfiguration konnte nicht gespeichert werden"
        }
    }'''
s = s[:a] + apply_multi + s[b:]

# playlistUrl() is only a compatibility helper, but make it understand the array.
a, b = function_span(s, "    fun playlistUrl(context: Context)")
playlist_url_fun = r'''    fun playlistUrl(context: Context): String? {
        val config = savedPayload(context)?.optJSONObject("config") ?: return null
        val first = config.optJSONArray("playlists")?.optJSONObject(0)
        return first?.optString("playlist_url")?.takeIf { it.isNotBlank() }
            ?: config.optString("playlist_url").takeIf { it.isNotBlank() }
    }'''
s = s[:a] + playlist_url_fun + s[b:]
provision.write_text(s)


# ---------------------------------------------------------------------------
# Movie/series loading UX: do not enter a half-empty catalog while the Xtream
# library is still being grouped. Show one short full content-area spinner, then
# reveal the catalog. Also clear catalogRowsLoading on category failures.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
vs = vm.read_text()
a, b = function_span(vs, "    private fun loadCategories(kind: MediaKind)")
block = vs[a:b]
old_failure = 'set { it.copy(loading = false, error = e.message ?: "Fehler beim Laden") }'
if old_failure not in block:
    raise SystemExit("loadCategories failure anchor missing")
block = block.replace(old_failure, 'set { it.copy(loading = false, catalogRowsLoading = false, error = e.message ?: "Fehler beim Laden") }', 1)
vs = vs[:a] + block + vs[b:]
vm.write_text(vs)

hub = java / "ui/V060CinematicHub.kt"
hs = hub.read_text()
a, b = function_span(hs, "fun V060CinematicHubScreen(vm: MainViewModel, kind: MediaKind, accent: Color, isTv: Boolean)")
new_hub = r'''fun V060CinematicHubScreen(vm: MainViewModel, kind: MediaKind, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val recent = u.recentlyWatched.filter { it.kind == kind || (kind == MediaKind.SERIES && it.kind == MediaKind.EPISODE) }
    val continueItems = u.continueWatching.filter { it.media.kind == kind || (kind == MediaKind.SERIES && it.media.kind == MediaKind.EPISODE) }
    val firstCatalog = u.categories.asSequence().mapNotNull { u.catalogRows[it.id]?.firstOrNull() }.firstOrNull()
    val hero = recent.firstOrNull() ?: firstCatalog
    BackHandler { vm.back() }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(if (kind == MediaKind.MOVIE) "FILME" else "SERIEN", R.drawable.brand_header, { vm.back() })
        if (u.loading || u.catalogRowsLoading) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator(Modifier.size(if (isTv) 46.dp else 38.dp), color = accent, strokeWidth = 3.dp)
                    Spacer(Modifier.height(16.dp))
                    Text(
                        if (kind == MediaKind.MOVIE) "Filme werden geladen …" else "Serien werden geladen …",
                        color = Color.White,
                        fontSize = if (isTv) 20.sp else 17.sp,
                        fontWeight = FontWeight.Black
                    )
                    Spacer(Modifier.height(6.dp))
                    Text("Katalog wird vorbereitet", color = Color.White.copy(.66f), fontSize = if (isTv) 14.sp else 12.sp)
                }
            }
        } else {
            LoadingOrError(false, u.error)
            LazyColumn(
                Modifier.fillMaxSize(),
                contentPadding = PaddingValues(bottom = 34.dp),
                verticalArrangement = Arrangement.spacedBy(if (isTv) 21.dp else 15.dp)
            ) {
                hero?.let { featured ->
                    item(key = "hero:${featured.resumeKey}") {
                        V060Hero(featured, accent, isTv) { vm.navigate(Screen.Details(featured)) }
                    }
                }
                item(key = "actions") {
                    Row(
                        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = if (isTv) 44.dp else 14.dp),
                        horizontalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        V060Action("Suchen", Icons.Default.Search, accent) { vm.openKindSearch(kind) }
                        V060Action("Zuletzt gesehen", Icons.Default.History, accent) { vm.navigate(Screen.RecentlyWatched) }
                        V060Action("Favoriten", Icons.Default.FavoriteBorder, accent) { vm.openKindFavorites(kind) }
                    }
                }
                if (continueItems.isNotEmpty()) {
                    item(key = "continue") {
                        V060PosterRow("WEITERSCHAUEN", continueItems.map { it.media }, accent, isTv, onMore = { vm.navigate(Screen.ContinueWatching) }) {
                            if (it.kind == MediaKind.EPISODE) vm.play(it) else vm.navigate(Screen.Details(it))
                        }
                    }
                }
                if (recent.isNotEmpty()) {
                    item(key = "recent") {
                        V060PosterRow("ZULETZT GESEHEN", recent, accent, isTv, onMore = { vm.navigate(Screen.RecentlyWatched) }) {
                            if (it.kind == MediaKind.EPISODE) vm.play(it) else vm.navigate(Screen.Details(it))
                        }
                    }
                }
                items(u.categories, key = { "category:${it.id}" }) { category ->
                    val row = u.catalogRows[category.id].orEmpty()
                    if (row.isNotEmpty()) {
                        V060PosterRow(category.name.uppercase(), row, accent, isTv, onMore = { vm.switchLibraryCategory(kind, category) }) {
                            vm.navigate(Screen.Details(it))
                        }
                    }
                }
                if (u.categories.isNotEmpty()) {
                    item(key = "all-categories") {
                        TextButton(onClick = { vm.switchLibraryCategory(kind, u.categories.first()) }, modifier = Modifier.padding(horizontal = if (isTv) 44.dp else 14.dp)) {
                            Text("Alle Kategorien öffnen", color = accent, fontWeight = FontWeight.Black)
                        }
                    }
                }
            }
        }
    }
}'''
hs = hs[:a] + new_hub + hs[b:]

# Broken poster URLs should never leave a visually blank tile.
a, b = function_span(hs, "private fun V060Poster(item: MediaEntry, accent: Color, isTv: Boolean, onClick: () -> Unit)")
new_poster = r'''private fun V060Poster(item: MediaEntry, accent: Color, isTv: Boolean, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    var imageFailed by remember(item.resumeKey, item.image) { mutableStateOf(false) }
    val scale by animateFloatAsState(if (focused) 1.10f else 1f, spring(stiffness = 360f), label = "posterFocus")
    val width = if (isTv) 172.dp else 126.dp
    val height = if (isTv) 250.dp else 190.dp
    val shape = RoundedCornerShape(14.dp)
    Box(
        Modifier.width(width).height(height).graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(if (focused) 26.dp else 2.dp, shape).onFocusChanged { focused = it.isFocused }.focusable()
            .clip(shape).background(Color(0xFF111A26)).border(if (focused) 3.dp else 1.dp, if (focused) accent else Color.White.copy(.10f), shape).clickable(onClick = onClick)
    ) {
        if (item.image.isNotBlank() && !imageFailed) {
            AsyncImage(
                model = item.image,
                contentDescription = item.name,
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Crop,
                onError = { imageFailed = true }
            )
        }
        if (item.image.isBlank() || imageFailed) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Icon(Icons.Default.Tv, null, tint = accent.copy(.78f), modifier = Modifier.size(44.dp))
            }
        }
        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent, Color.Transparent, Color.Black.copy(.94f)))))
        Column(Modifier.align(Alignment.BottomStart).padding(10.dp)) {
            Text(item.name, color = Color.White, fontSize = if (isTv) 14.sp else 12.sp, lineHeight = if (isTv) 17.sp else 15.sp, fontWeight = FontWeight.Black, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (item.rating.isNotBlank()) Text("★ ${item.rating}", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 3.dp))
        }
        if (focused) Text("OK", color = Color.Black, fontSize = 10.sp, fontWeight = FontWeight.Black, modifier = Modifier.align(Alignment.TopEnd).padding(8.dp).background(accent, RoundedCornerShape(7.dp)).padding(horizontal = 7.dp, vertical = 4.dp))
    }
}'''
hs = hs[:a] + new_poster + hs[b:]
hub.write_text(hs)


# ---------------------------------------------------------------------------
# Use all common Xtream artwork fields before falling back to a placeholder.
# ---------------------------------------------------------------------------
xtream = java / "data/XtreamClient.kt"
xs = xtream.read_text()
xs = xs.replace(
    'image = o.optString("stream_icon"),',
    'image = firstNonBlank(o.optString("stream_icon"), o.optString("movie_image"), o.optString("cover"), o.optString("cover_big")),',
)
xs = xs.replace(
    'image = o.optString("cover"),',
    'image = firstNonBlank(o.optString("cover"), o.optString("stream_icon"), o.optString("cover_big"), o.optString("movie_image")),',
    1,
)
xtream.write_text(xs)


# Sanity checks.
checks = [
    (build, 'versionName = "0.6.4.15"'),
    (build, 'versionCode = 618'),
    (m3u, 'parseReader(it)'),
    (m3u, 'DEFAULT_STREAM_UA'),
    (provision, 'MANAGED_PROFILE_PREFIX = "managed-dashboard-"'),
    (provision, 'config.optJSONArray("playlists")'),
    (provision, 'xtreamFromM3u(url)'),
    (provision, '}.getOrDefault(false)\n\n    private data class DerivedXtream('),
    (hub, 'Filme werden geladen …'),
    (hub, 'onError = { imageFailed = true }'),
    (xtream, 'o.optString("cover_big")'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing v0.6.4.15 marker {marker} in {path}")

if 'it.readText()' in m3u.read_text():
    raise SystemExit("unsafe generic M3U readText still present")

print("Android v0.6.4.15 multi-playlist Dashboard 0.7 + streaming M3U + catalog loader applied")
