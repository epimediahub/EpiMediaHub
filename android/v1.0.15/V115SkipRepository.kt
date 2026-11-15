package de.epimediahub.app.data

import android.content.Context
import android.os.SystemClock
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.text.Normalizer
import java.util.Locale
import kotlin.math.abs

internal data class V115Identity(val imdb: String = "", val tmdb: Int = 0) {
    val usable: Boolean get() = imdb.isNotBlank() || tmdb > 0
}

internal enum class V115SegmentKind(val label: String) {
    INTRO("Intro überspringen"), RECAP("Rückblick überspringen"), OUTRO("Abspann überspringen")
}

internal data class V115Segment(
    val kind: V115SegmentKind, val startMs: Long, val endMs: Long, val source: String,
    val durationMatched: Boolean = false, val confidence: Double = 0.0
) {
    fun active(positionMs: Long): Boolean = positionMs >= startMs && positionMs < endMs - 500L
}

internal object V115SkipPolicy {
    fun imdb(value: String): String = Regex("tt[0-9]{7,10}").find(value)?.value.orEmpty()
    fun tmdb(value: String): Int = value.trim().toIntOrNull()?.takeIf { it in 1..100_000_000 } ?: 0
    fun firstImdb(vararg values: String): String = values.firstNotNullOfOrNull { imdb(it).takeIf(String::isNotBlank) }.orEmpty()
    fun firstTmdb(vararg values: String): Int = values.firstNotNullOfOrNull { tmdb(it).takeIf { id -> id > 0 } } ?: 0
    fun cleanTitle(value: String): String = value
        .replace(Regex("(?i)^\\s*(?:DE|GER|IT|ITA|EN|ENG|FR|TR|ES|US|UK)\\s*[|:–-]\\s*"), "")
        .replace(Regex("(?i)\\s*(?:[\\[(](?:19|20)[0-9]{2}[\\])])?\\s+(?:4K|UHD|FHD|HD|SD|HEVC|H265|H264|1080P|720P)(?:\\s.*)?$"), "")
        .replace(Regex("\\s*[\\[(](?:19|20)[0-9]{2}[\\])]\\s*$"), "").trim()
    fun normalized(value: String): String = Normalizer.normalize(cleanTitle(value), Normalizer.Form.NFD)
        .replace(Regex("\\p{M}+"), "").lowercase(Locale.ROOT).replace(Regex("[^\\p{L}\\p{N}]+"), " ").trim()

    fun valid(segment: V115Segment, duration: Long): Boolean {
        val maxLength = if (segment.kind == V115SegmentKind.OUTRO) 900_000L else 300_000L
        return duration > 0 && segment.startMs >= 0 && segment.endMs <= duration &&
            segment.endMs - segment.startMs in 5_000L..maxLength
    }

    // Missing data, estimates, shifted versions and conflicting sources never
    // produce a skip action. No percentage or fixed episode offset is used.
    fun select(candidates: List<V115Segment>, duration: Long): List<V115Segment> =
        candidates.filter { valid(it, duration) }.groupBy { it.kind }.flatMap { (_, entries) ->
            val trusted = entries.filter { it.durationMatched && it.confidence >= .85 }
            val providers = trusted.map { it.source }.distinct()
            trusted.mapNotNull { candidate ->
                val agreeing = entries.filter {
                    abs(it.startMs - candidate.startMs) <= 3_000L && abs(it.endMs - candidate.endMs) <= 3_000L
                }
                if (providers.any { provider -> agreeing.none { it.source == provider && it.durationMatched } }) null
                else candidate.copy(
                    startMs = agreeing.maxOf { it.startMs }, endMs = agreeing.minOf { it.endMs },
                    source = agreeing.map { it.source }.distinct().sorted().joinToString(" + ")
                ).takeIf { valid(it, duration) }
            }
        }.distinctBy { Triple(it.kind, it.startMs, it.endMs) }.sortedBy { it.startMs }

    fun skipDb(root: JSONObject, duration: Long): List<V115Segment> {
        val all = root.optJSONObject("segments") ?: return emptyList()
        return listOf("intro" to V115SegmentKind.INTRO, "recap" to V115SegmentKind.RECAP, "outro" to V115SegmentKind.OUTRO).mapNotNull { (key, kind) ->
            val s = all.optJSONObject(key) ?: return@mapNotNull null
            if (s.optString("match") != "exact" || s.optBoolean("adjusted")) return@mapNotNull null
            V115Segment(kind, s.optLong("start_ms", -1), s.optLong("end_ms", -1), "SkipDB", true, s.optDouble("confidence", 0.0))
        }.filter { valid(it, duration) }
    }

    fun matchingVersion(root: JSONObject, duration: Long): Long? {
        val versions = root.optJSONArray("versions") ?: return null
        return (0 until versions.length()).mapNotNull { versions.optJSONObject(it)?.optLong("duration_ms") }
            .filter { it > 0L && abs(it - duration) <= 2_000L }.minByOrNull { abs(it - duration) }
    }

    fun theIntroDb(root: JSONObject, duration: Long, matchedVersion: Boolean): List<V115Segment> =
        listOf("intro" to V115SegmentKind.INTRO, "recap" to V115SegmentKind.RECAP, "credits" to V115SegmentKind.OUTRO).flatMap { (key, kind) ->
            val a = root.optJSONArray(key) ?: return@flatMap emptyList()
            (0 until a.length()).mapNotNull { index ->
                val s = a.optJSONObject(index) ?: return@mapNotNull null
                if (!s.has("start_ms") || !s.has("end_ms")) return@mapNotNull null
                val start = if (s.isNull("start_ms") && kind != V115SegmentKind.OUTRO) 0L else s.optLong("start_ms", -1L)
                val end = if (s.isNull("end_ms") && kind == V115SegmentKind.OUTRO) duration else s.optLong("end_ms", -1L)
                V115Segment(kind, start, end, "TheIntroDB", matchedVersion, s.optDouble("confidence", .9))
            }
        }.filter { valid(it, duration) }

    fun introDb(root: JSONObject, duration: Long): List<V115Segment> {
        // This API does not expose version matching. Only an explicit runtime or
        // a terminal credit/post-credit boundary can establish a duration match.
        val runtime = root.optLong("video_duration_ms", root.optLong("duration_ms", 0L))
        val terminal = listOf("outro", "post_credits").mapNotNull { root.optJSONObject(it) }
            .any { abs(it.optLong("end_ms", -1L) - duration) <= 2_000L }
        val match = (runtime > 0L && abs(runtime - duration) <= 2_000L) || terminal
        return listOf("intro" to V115SegmentKind.INTRO, "recap" to V115SegmentKind.RECAP, "outro" to V115SegmentKind.OUTRO).mapNotNull { (key, kind) ->
            val s = root.optJSONObject(key) ?: return@mapNotNull null
            V115Segment(kind, s.optLong("start_ms", -1), s.optLong("end_ms", -1), "IntroDB", match, s.optDouble("confidence", 0.0))
        }.filter { valid(it, duration) }
    }

    fun searchIdentity(root: JSONObject, title: String, year: Int, episode: Boolean): V115Identity {
        fun matches(a: JSONArray?): List<JSONObject> = if (a == null) emptyList() else (0 until a.length()).mapNotNull { a.optJSONObject(it) }.filter {
            val type = it.optString("mediaType")
            normalized(it.optString("name")) == normalized(title) && type == (if (episode) "series" else "movie") &&
                (year <= 0 || it.optInt("year", 0) == year)
        }
        val remote = matches(root.optJSONArray("results")).distinctBy { it.optInt("tmdbId") }
        val local = matches(root.optJSONArray("local")).distinctBy { it.optString("imdb_id") }
        if (remote.size > 1 || local.size > 1) return V115Identity()
        return V115Identity(
            if (local.size == 1) imdb(local.single().optString("imdb_id")) else "",
            if (remote.size == 1) remote.single().optInt("tmdbId", 0) else 0
        )
    }

    fun mazeIdentity(rows: JSONArray, title: String, year: Int): String {
        val exact = (0 until rows.length()).mapNotNull { rows.optJSONObject(it)?.optJSONObject("show") }.filter {
            normalized(it.optString("name")) == normalized(title) &&
                (year <= 0 || it.optString("premiered").take(4).toIntOrNull() == year)
        }.mapNotNull { it.optJSONObject("externals")?.optString("imdb")?.let(::imdb)?.takeIf(String::isNotBlank) }.distinct()
        return exact.singleOrNull().orEmpty()
    }
}

internal class V115SkipRepository(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("v115_skip_metadata", Context.MODE_PRIVATE)
    private fun enc(value: String) = URLEncoder.encode(value, "UTF-8")
    private fun cached(key: String): JSONObject? = runCatching {
        JSONObject(prefs.getString(key, "") ?: "").takeIf { it.optLong("expires") > System.currentTimeMillis() }?.optJSONObject("value")
    }.getOrNull()
    private fun cache(key: String, value: JSONObject, hours: Int) {
        val editor = prefs.edit()
        // Bound persistent storage without retaining provider credentials or URLs.
        if (prefs.all.size > 500) prefs.all.entries.sortedBy {
            runCatching { JSONObject(it.value.toString()).optLong("expires") }.getOrDefault(0L)
        }.take(100).forEach { editor.remove(it.key) }
        editor.putString(key, JSONObject().put("expires", System.currentTimeMillis() + hours * 3_600_000L).put("value", value).toString()).apply()
    }

    private suspend fun fetch(url: String): JSONObject? {
        val host = URL(url).host
        val gate = synchronized(gates) { gates.getOrPut(host) { Mutex() } }
        return gate.withLock {
            if ((blockedUntil[host] ?: 0L) > SystemClock.elapsedRealtime()) return@withLock null
            val spacing = if (url.contains("/titles/")) 2_100L else 550L
            delay(((lastRequest[host] ?: 0L) + spacing - SystemClock.elapsedRealtime()).coerceAtLeast(0L))
            lastRequest[host] = SystemClock.elapsedRealtime()
            try {
                withContext(Dispatchers.IO) {
                    val connection = (URL(url).openConnection() as HttpURLConnection).apply {
                        connectTimeout = 4_000; readTimeout = 5_000
                        setRequestProperty("User-Agent", "EpiMediaHub/1.0.15 Android")
                        setRequestProperty("Accept", "application/json")
                    }
                    try {
                        if (connection.responseCode == 429) {
                            blockedUntil[host] = SystemClock.elapsedRealtime() + 60_000L
                            return@withContext null
                        }
                        if (connection.responseCode != 200) return@withContext null
                        val data = connection.inputStream.bufferedReader().use { reader ->
                            val buffer = CharArray(4_096); val body = StringBuilder()
                            while (true) {
                                val n = reader.read(buffer)
                                if (n < 0) break
                                if (body.length + n > 300_000) return@use ""
                                body.append(buffer, 0, n)
                            }
                            body.toString()
                        }
                        if (data.startsWith("[")) JSONObject().put("rows", JSONArray(data)) else JSONObject(data)
                    } finally { connection.disconnect() }
                }
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { null }
        }
    }

    private suspend fun identify(item: MediaEntry): V115Identity = supervisorScope {
        val supplied = V115Identity(V115SkipPolicy.imdb(item.imdbId), V115SkipPolicy.tmdb(item.tmdbId))
        if (supplied.imdb.isNotBlank()) return@supervisorScope supplied
        val title = V115SkipPolicy.cleanTitle(if (item.kind == MediaKind.EPISODE) item.categoryId else item.name)
        if (title.length !in 2..180) return@supervisorScope supplied
        val year = item.year.take(4).toIntOrNull() ?: 0
        val key = "identity:${item.kind == MediaKind.EPISODE}:$title:$year:${supplied.tmdb}"
        cached(key)?.let { return@supervisorScope V115Identity(it.optString("imdb"), it.optInt("tmdb")) }
        val search = async { fetch("https://skipdb.tv/api/titles/search?q=${enc(title)}") }
        val maze = async { if (item.kind == MediaKind.EPISODE) fetch("https://api.tvmaze.com/search/shows?q=${enc(title)}") else null }
        val found = search.await()?.let { V115SkipPolicy.searchIdentity(it, title, year, item.kind == MediaKind.EPISODE) } ?: V115Identity()
        val mazeId = maze.await()?.optJSONArray("rows")?.let { V115SkipPolicy.mazeIdentity(it, title, year) }.orEmpty()
        if (supplied.tmdb > 0 && found.tmdb > 0 && supplied.tmdb != found.tmdb) return@supervisorScope supplied
        // Different exact title matches are ambiguous; never choose the first hit.
        val imdb = if (found.imdb.isNotBlank() && mazeId.isNotBlank() && found.imdb != mazeId) "" else found.imdb.ifBlank { mazeId }
        val result = V115Identity(imdb, supplied.tmdb.takeIf { it > 0 } ?: found.tmdb)
        if (result.usable) cache(key, JSONObject().put("imdb", result.imdb).put("tmdb", result.tmdb), 168)
        result
    }

    suspend fun load(item: MediaEntry, durationMs: Long): List<V115Segment> = withContext(Dispatchers.IO) {
        if (durationMs <= 0 || item.kind !in listOf(MediaKind.MOVIE, MediaKind.EPISODE)) return@withContext emptyList()
        if (item.kind == MediaKind.EPISODE && (item.season < 0 || item.episode <= 0)) return@withContext emptyList()
        val identity = identify(item)
        if (!identity.usable) return@withContext emptyList()
        val tv = item.kind == MediaKind.EPISODE
        val suffix = if (tv) "&season=${item.season}&episode=${item.episode}" else ""
        val key = "segments:${identity.imdb}:${identity.tmdb}:$tv:${item.season}:${item.episode}:${durationMs / 1000}"
        cached(key)?.optJSONArray("segments")?.let { rows ->
            return@withContext (0 until rows.length()).mapNotNull { index ->
                runCatching {
                    val s = rows.getJSONObject(index)
                    V115Segment(V115SegmentKind.valueOf(s.getString("kind")), s.getLong("start"), s.getLong("end"), s.getString("source"), true, 1.0)
                }.getOrNull()?.takeIf { V115SkipPolicy.valid(it, durationMs) }
            }
        }
        val candidates = supervisorScope {
            val skip = async {
                if (identity.imdb.isBlank()) emptyList() else fetch("https://api.skipdb.tv/api/segments?imdb_id=${identity.imdb}$suffix&duration=${durationMs / 1000}&adjust=none")
                    ?.takeIf { it.optString("imdb_id") == identity.imdb && (!tv || (it.optInt("season", -1) == item.season && it.optInt("episode", -1) == item.episode)) }
                    ?.let { V115SkipPolicy.skipDb(it, durationMs) } ?: emptyList()
            }
            val intro = async {
                if (identity.imdb.isBlank()) emptyList() else fetch("https://api.introdb.app/segments?imdb_id=${identity.imdb}${if (tv) suffix else "&is_movie=true"}")
                    ?.takeIf { it.optString("imdb_id") == identity.imdb && it.optBoolean("is_movie") != tv && (!tv || (it.optInt("season", -1) == item.season && it.optInt("episode", -1) == item.episode)) }
                    ?.let { V115SkipPolicy.introDb(it, durationMs) } ?: emptyList()
            }
            val theIntro = async {
                val id = if (identity.tmdb > 0) "tmdb_id=${identity.tmdb}" else "imdb_id=${identity.imdb}"
                val base = "https://api.theintrodb.org/v3/media?$id$suffix"
                val versions = fetch("$base&list_versions=true") ?: return@async emptyList()
                if (versions.optString("type") != (if (tv) "tv" else "movie") ||
                    (identity.tmdb > 0 && versions.optInt("tmdb_id") != identity.tmdb) ||
                    (tv && (versions.optInt("season", -1) != item.season || versions.optInt("episode", -1) != item.episode))) return@async emptyList()
                val matched = V115SkipPolicy.matchingVersion(versions, durationMs) ?: return@async emptyList()
                fetch("$base&duration_ms=$matched&merge_unknown=false")?.takeIf {
                    it.optInt("tmdb_id") == versions.optInt("tmdb_id") && it.optString("type") == versions.optString("type") &&
                        (!tv || (it.optInt("season", -1) == item.season && it.optInt("episode", -1) == item.episode))
                }?.let { V115SkipPolicy.theIntroDb(it, durationMs, true) } ?: emptyList()
            }
            skip.await() + intro.await() + theIntro.await()
        }
        val selected = V115SkipPolicy.select(candidates, durationMs)
        // Cache positive data for a week; unknown/network failures remain retryable.
        if (selected.isNotEmpty()) cache(key, JSONObject().put("segments", JSONArray().apply {
            selected.forEach { put(JSONObject().put("kind", it.kind.name).put("start", it.startMs).put("end", it.endMs).put("source", it.source)) }
        }), 168)
        selected
    }

    companion object {
        private val gates = mutableMapOf<String, Mutex>()
        private val lastRequest = java.util.concurrent.ConcurrentHashMap<String, Long>()
        private val blockedUntil = java.util.concurrent.ConcurrentHashMap<String, Long>()
    }
}
