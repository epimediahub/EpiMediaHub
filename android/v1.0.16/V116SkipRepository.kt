package de.epimediahub.app.data

import android.content.Context
import android.net.Uri
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest
import kotlin.math.abs

internal data class V116TitleChoice(val title: String, val year: String, val imdb: String, val tmdb: Int)
internal data class V116SkipResult(val segments: List<V115Segment>, val status: String, val disabled: Set<V115SegmentKind> = emptySet())

internal object V116SkipKeys {
    fun hash(value: String): String = MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    // Xtream's numeric file name is shared across accounts; account/password path
    // components never leave the device. Other URLs stay distinct by a one-way hash.
    fun asset(item: MediaEntry): String {
        val uri = Uri.parse(item.streamUrl)
        val file = uri.lastPathSegment.orEmpty()
        val xtream = Regex("^[0-9]+\\.[a-zA-Z0-9]{1,8}$").matches(file) && uri.pathSegments.firstOrNull() in listOf("series", "movie")
        val origin = "${uri.scheme.orEmpty().lowercase()}://${uri.host.orEmpty().lowercase()}:${uri.port}"
        return hash(if (xtream) "$origin|${item.kind}|$file" else "${item.kind}|${item.streamUrl.ifBlank { item.resumeKey }}")
    }
    fun series(item: MediaEntry): String {
        val uri = Uri.parse(item.streamUrl)
        val title = if (item.kind == MediaKind.EPISODE) item.categoryId else item.name
        val id = if (item.kind == MediaKind.EPISODE) item.seriesId else item.id
        return hash("${uri.host}:${uri.port}|${item.kind == MediaKind.EPISODE}|${id.ifBlank { item.sourceProfileId }}|${V116Names.clean(title)}|${item.year}")
    }
    fun local(item: MediaEntry, duration: Long): String = "${asset(item)}:${duration / 1000}"
}

internal object V116Names {
    fun clean(value: String): String {
        var name = value.trim()
        repeat(5) {
            name = name.replace(Regex("(?i)^\\s*(?:[\\[(](?:DE|GER|GERMAN|IT|ITA|EN|ENG|FR|TR|ES|US|UK|HD|FHD|UHD|4K)[\\])]|(?:DE|GER|GERMAN|IT|ITA|EN|ENG|FR|TR|ES|US|UK)\\s*[|:–-])\\s*"), "").trim()
            name = name.replace(Regex("(?i)\\s*(?:[|:–-]\\s*)?(?:[\\[(])?(?:4K|UHD|FHD|FULL HD|HD|SD|HEVC|H265|H264|1080P|720P)(?:[\\])])?\\s*$"), "").trim()
        }
        return name.replace(Regex("\\s*[\\[(](?:19|20)[0-9]{2}[\\])]\\s*$"), "").trim()
    }
}

internal class V116SkipRepository(private val context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("v116_own_skip", Context.MODE_PRIVATE)
    private val publicData = V115SkipRepository(context)
    private fun tokenScope(): String = SetupCodeProvisioning.sessionToken(context)?.let(V116SkipKeys::hash).orEmpty()
    private fun read(key: String): JSONObject? = runCatching { JSONObject(prefs.getString(key, "") ?: "") }.getOrNull()
    private fun write(key: String, value: JSONObject) { prefs.edit().putString(key, value.toString()).apply() }
    private fun enc(value: String) = URLEncoder.encode(value, "UTF-8")

    private suspend fun request(url: String, body: JSONObject? = null, authenticated: Boolean = false): JSONObject? = withContext(Dispatchers.IO) {
        if (authenticated && SetupCodeProvisioning.sessionToken(context).isNullOrBlank()) return@withContext null
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 4_000; readTimeout = 5_000; instanceFollowRedirects = false
            setRequestProperty("Accept", "application/json"); setRequestProperty("User-Agent", "EpiMediaHub/1.0.16 Android")
            if (authenticated) setRequestProperty("Authorization", "Bearer ${SetupCodeProvisioning.sessionToken(context)}")
            if (body != null) { requestMethod = "POST"; doOutput = true; setRequestProperty("Content-Type", "application/json") }
        }
        try {
            if (body != null) connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            if (connection.responseCode !in 200..299) return@withContext null
            val text = connection.inputStream.bufferedReader().use { reader ->
                val result = StringBuilder(); val buffer = CharArray(4096)
                while (true) { ensureActive(); val n = reader.read(buffer); if (n < 0) break; if (result.length + n > 200_000) return@use ""; result.append(buffer, 0, n) }
                result.toString()
            }
            if (text.startsWith("[")) JSONObject().put("rows", JSONArray(text)) else JSONObject(text)
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { null }
        finally { connection.disconnect() }
    }

    private fun playlistId(item: MediaEntry): Int = if (item.sourceProfileId.startsWith("managed-dashboard-")) item.sourceProfileId.removePrefix("managed-dashboard-").toIntOrNull()?.takeIf { it > 0 } ?: 0 else 0

    fun payload(item: MediaEntry, duration: Long): JSONObject {
        val known = identity(item) ?: V115Identity(V115SkipPolicy.imdb(item.imdbId), V115SkipPolicy.tmdb(item.tmdbId))
        val file = Uri.parse(item.streamUrl).lastPathSegment.orEmpty()
        return JSONObject().put("asset_key", V116SkipKeys.asset(item)).put("source_key", V116SkipKeys.series(item))
        .put("media_type", if (item.kind == MediaKind.EPISODE) "episode" else "movie")
        .put("title", V116Names.clean(if (item.kind == MediaKind.EPISODE) item.categoryId else item.name).take(180))
        .put("year", item.year.take(4).takeIf { it.matches(Regex("(?:19|20)[0-9]{2}")) }.orEmpty())
        .put("season", if (item.kind == MediaKind.EPISODE) item.season else 0).put("episode", if (item.kind == MediaKind.EPISODE) item.episode else 0)
        .put("duration_ms", duration).put("imdb_id", known.imdb).put("tmdb_id", known.tmdb)
        .put("playlist_id", playlistId(item)).put("stream_id", file.substringBeforeLast('.').takeIf { it.matches(Regex("[0-9]{1,12}")) }.orEmpty())
        .put("extension", file.substringAfterLast('.', "").lowercase())
    }

    suspend fun presence(item: MediaEntry) {
        val id = playlistId(item)
        if (id > 0) request("${SetupCodeProvisioning.provisioningBaseUrl(context)}/v1/device/skip/presence", JSONObject().put("playlist_id", id), true)
    }

    suspend fun flushPending() {
        if (SetupCodeProvisioning.sessionToken(context).isNullOrBlank()) return
        var count = 0
        for (key in prefs.all.keys.filter { it.startsWith("own:") }) {
            val root = read(key) ?: continue
            val marks = root.optJSONObject("marks") ?: continue
            for (kind in V115SegmentKind.values()) {
                val row = marks.optJSONObject(kind.name) ?: continue
                if (!row.optBoolean("pending") || (row.optString("scope").isNotBlank() && row.optString("scope") != tokenScope())) continue
                if (++count > 5) return
                val body = JSONObject(row.toString()).apply { remove("scope"); remove("pending") }
                val accepted = request("${SetupCodeProvisioning.provisioningBaseUrl(context)}/v1/device/skip/submit", body, true) ?: return
                if (accepted.optString("status") !in listOf("pending", "approved", "rejected", "superseded")) return
                val latest = read(key) ?: continue
                val current = latest.optJSONObject("marks")?.optJSONObject(kind.name) ?: continue
                if (current.toString() != row.toString()) continue
                current.put("pending", false).put("scope", tokenScope()); write(key, latest)
            }
        }
    }

    fun overrides(item: MediaEntry, duration: Long): Map<V115SegmentKind, V115Segment?> {
        val rows = read("own:${V116SkipKeys.local(item, duration)}")?.optJSONObject("marks") ?: return emptyMap()
        return V115SegmentKind.values().mapNotNull { kind ->
            val row = rows.optJSONObject(kind.name) ?: return@mapNotNull null
            if (abs(row.optLong("duration_ms") - duration) > 2_000L) return@mapNotNull null
            if (row.optBoolean("disabled")) kind to null
            else V115Segment(kind, row.optLong("start_ms", -1), row.optLong("end_ms", -1), "Eigene Zeitmarke", true, 1.0)
                .takeIf { V115SkipPolicy.valid(it, duration) }?.let { kind to it }
        }.toMap()
    }

    fun merge(item: MediaEntry, duration: Long, automatic: List<V115Segment>, disabled: Set<V115SegmentKind> = emptySet()): List<V115Segment> {
        val own = overrides(item, duration)
        return (V115SkipPolicy.select(automatic.filter { it.kind !in disabled }, duration).filter { it.kind !in own } + own.values.filterNotNull()).sortedBy { it.startMs }
    }

    fun save(item: MediaEntry, duration: Long, kind: V115SegmentKind, start: Long?, end: Long?, disabled: Boolean = false): Boolean {
        if (duration <= 0) return false
        if (!disabled && (start == null || end == null || !V115SkipPolicy.valid(V115Segment(kind, start, end, "Eigene Zeitmarke", true, 1.0), duration))) return false
        val key = "own:${V116SkipKeys.local(item, duration)}"
        val root = read(key) ?: JSONObject()
        val marks = root.optJSONObject("marks") ?: JSONObject()
        val record = payload(item, duration).put("segment_type", kind.name.lowercase()).put("disabled", disabled)
            .put("start_ms", start ?: 0L).put("end_ms", end ?: 0L).put("scope", tokenScope()).put("pending", true)
        marks.put(kind.name, record); root.put("marks", marks); write(key, root)
        return true
    }

    fun reset(item: MediaEntry, duration: Long, kind: V115SegmentKind) {
        val key = "own:${V116SkipKeys.local(item, duration)}"
        val root = read(key) ?: return
        root.optJSONObject("marks")?.remove(kind.name); write(key, root)
    }

    fun identity(item: MediaEntry): V115Identity? = read("identity:${V116SkipKeys.series(item)}")?.let {
        V115Identity(V115SkipPolicy.imdb(it.optString("imdb_id")), V115SkipPolicy.tmdb(it.optString("tmdb_id"))).takeIf { id -> id.usable }
    }
    fun setIdentity(item: MediaEntry, choice: V116TitleChoice) {
        write("identity:${V116SkipKeys.series(item)}", JSONObject().put("imdb_id", choice.imdb).put("tmdb_id", choice.tmdb))
    }

    suspend fun sync(item: MediaEntry, duration: Long): String {
        if (SetupCodeProvisioning.sessionToken(context).isNullOrBlank()) return "Auf diesem Gerät gespeichert · Gerät für die zentrale Nutzung koppeln"
        val key = "own:${V116SkipKeys.local(item, duration)}"
        val root = read(key) ?: return ""
        val marks = root.optJSONObject("marks") ?: return ""
        var pending = false
        for (kind in V115SegmentKind.values()) {
            val row = marks.optJSONObject(kind.name) ?: continue
            if (!row.optBoolean("pending")) continue
            if (row.optString("scope").isNotBlank() && row.optString("scope") != tokenScope()) continue
            val body = JSONObject(row.toString()).apply { remove("scope"); remove("pending") }
            val accepted = request("${SetupCodeProvisioning.provisioningBaseUrl(context)}/v1/device/skip/submit", body, true)
            // Re-read after the network request: a newer edit must never be lost.
            val latest = read(key) ?: continue
            val current = latest.optJSONObject("marks")?.optJSONObject(kind.name) ?: continue
            if (current.toString() != row.toString()) continue
            if (accepted?.optString("status") in listOf("pending", "approved", "rejected", "superseded")) {
                current.put("pending", false).put("scope", tokenScope()); write(key, latest)
            } else pending = true
        }
        return if (pending) "Auf diesem Gerät gespeichert · zentrale Übertragung wird später erneut versucht" else "Auf diesem Gerät gespeichert · zentrale Freigabe im Dashboard prüfen"
    }

    private fun approved(root: JSONObject, item: MediaEntry, duration: Long): Pair<List<V115Segment>, Set<V115SegmentKind>> {
        if (root.optString("asset_key") != V116SkipKeys.asset(item) || abs(root.optLong("duration_ms") - duration) > 2_000L) return emptyList<V115Segment>() to emptySet()
        val rows = root.optJSONArray("segments") ?: return emptyList<V115Segment>() to emptySet()
        val disabled = mutableSetOf<V115SegmentKind>(); val result = mutableListOf<V115Segment>()
        for (i in 0 until rows.length()) {
            val row = rows.optJSONObject(i) ?: continue
            if (row.optString("status") != "approved" || abs(row.optLong("duration_ms") - duration) > 2_000L) continue
            val kind = runCatching { V115SegmentKind.valueOf(row.optString("segment_type").uppercase()) }.getOrNull() ?: continue
            if (row.optBoolean("disabled")) disabled += kind
            else V115Segment(kind, row.optLong("start_ms", -1), row.optLong("end_ms", -1), "EpiMediaHub · geprüft", true, 1.0)
                .takeIf { V115SkipPolicy.valid(it, duration) }?.let(result::add)
        }
        return result.filter { it.kind !in disabled } to disabled
    }

    suspend fun load(item: MediaEntry, duration: Long): V116SkipResult = supervisorScope {
        val cacheKey = "remote:${tokenScope()}:${V116SkipKeys.local(item, duration)}"
        val remote = request("${SetupCodeProvisioning.provisioningBaseUrl(context)}/v1/device/skip/lookup", payload(item, duration), true)
            ?.takeIf { it.optString("asset_key") == V116SkipKeys.asset(item) && it.optString("source_key") == V116SkipKeys.series(item) }
            ?.also { write(cacheKey, JSONObject().put("expires", System.currentTimeMillis() + 3_600_000L).put("data", it)) }
            ?: read(cacheKey)?.takeIf { it.optLong("expires") > System.currentTimeMillis() }?.optJSONObject("data")
        val resolved = identity(item) ?: remote?.optJSONObject("identity")?.let {
            V115Identity(V115SkipPolicy.imdb(it.optString("imdb_id")), V115SkipPolicy.tmdb(it.optString("tmdb_id"))).takeIf { id -> id.usable }
        }
        val prepared = if (resolved == null) item else item.copy(imdbId = resolved.imdb, tmdbId = resolved.tmdb.takeIf { it > 0 }?.toString().orEmpty())
        val data = withTimeoutOrNull(25_000L) { publicData.load(prepared, duration) }.orEmpty()
        val (central, disabled) = remote?.let { approved(it, item, duration) } ?: (emptyList<V115Segment>() to emptySet())
        // Reviewed provider-file marks take precedence over generic database data.
        val centralKinds = central.map { it.kind }.toSet() + disabled
        val automatic = data.filter { it.kind !in centralKinds } + central
        val merged = merge(item, duration, automatic)
        V116SkipResult(automatic, if (merged.isNotEmpty()) "Passende Zeitmarken verfügbar" else "Keine passenden Zeitmarken · Zeiten selbst markieren oder Zuordnung prüfen", disabled)
    }

    suspend fun candidates(item: MediaEntry): List<V116TitleChoice> = supervisorScope {
        val name = V116Names.clean(if (item.kind == MediaKind.EPISODE) item.categoryId else item.name)
        if (name.length !in 2..180) return@supervisorScope emptyList()
        val skip = async { request("https://skipdb.tv/api/titles/search?q=${enc(name)}") }
        val maze = async { if (item.kind == MediaKind.EPISODE) request("https://api.tvmaze.com/search/shows?q=${enc(name)}") else null }
        val result = mutableListOf<V116TitleChoice>()
        skip.await()?.let { root ->
            for (key in listOf("results", "local")) {
                val rows = root.optJSONArray(key) ?: continue
                for (i in 0 until rows.length()) {
                    val row = rows.optJSONObject(i) ?: continue
                    if (row.optString("mediaType") != (if (item.kind == MediaKind.EPISODE) "series" else "movie")) continue
                    result += V116TitleChoice(row.optString("name"), row.optString("year"), V115SkipPolicy.imdb(row.optString("imdb_id")), row.optInt("tmdbId"))
                }
            }
        }
        maze.await()?.optJSONArray("rows")?.let { rows ->
            for (i in 0 until rows.length()) {
                val row = rows.optJSONObject(i)?.optJSONObject("show") ?: continue
                result += V116TitleChoice(row.optString("name"), row.optString("premiered").take(4), V115SkipPolicy.imdb(row.optJSONObject("externals")?.optString("imdb").orEmpty()), 0)
            }
        }
        result.filter { it.title.isNotBlank() && (it.imdb.isNotBlank() || it.tmdb > 0) }.distinctBy { "${it.imdb}:${it.tmdb}:${it.title}" }.take(20)
    }
}
