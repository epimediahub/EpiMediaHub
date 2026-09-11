package de.epimediahub.app.data

import android.util.Base64
import de.epimediahub.app.model.*
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

class XtreamClient(private val p: PlaylistProfile) {
    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")
    private fun api(action: String, extra: String = "") =
        "${p.server}/player_api.php?username=${enc(p.username)}&password=${enc(p.password)}&action=$action$extra"

    private fun text(url: String): String {
        val c = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 10000
            readTimeout = 25000
            setRequestProperty("User-Agent", "EpiMediaHub-Android/0.3.3")
        }
        return try {
            val code = c.responseCode
            if (code !in 200..299) error("Xtream HTTP $code")
            c.inputStream.bufferedReader().use { it.readText() }
        } finally {
            c.disconnect()
        }
    }

    private fun array(url: String) = JSONArray(text(url))

    fun categories(kind: MediaKind): List<MediaCategory> {
        val action = when (kind) {
            MediaKind.LIVE -> "get_live_categories"
            MediaKind.MOVIE -> "get_vod_categories"
            MediaKind.SERIES -> "get_series_categories"
            else -> return emptyList()
        }
        val a = array(api(action))
        return buildList {
            for (i in 0 until a.length()) {
                val o = a.optJSONObject(i) ?: continue
                add(MediaCategory(o.optString("category_id"), o.optString("category_name", "Andere")))
            }
        }
    }

    fun entries(kind: MediaKind, categoryId: String? = null): List<MediaEntry> {
        val action = when (kind) {
            MediaKind.LIVE -> "get_live_streams"
            MediaKind.MOVIE -> "get_vod_streams"
            MediaKind.SERIES -> "get_series"
            else -> return emptyList()
        }
        val extra = if (categoryId.isNullOrBlank()) "" else "&category_id=${enc(categoryId)}"
        val a = array(api(action, extra))
        return buildList {
            for (i in 0 until a.length()) {
                val o = a.optJSONObject(i) ?: continue
                when (kind) {
                    MediaKind.LIVE -> {
                        val id = o.optString("stream_id")
                        add(
                            MediaEntry(
                                id = id,
                                name = o.optString("name"),
                                kind = kind,
                                categoryId = o.optString("category_id"),
                                image = o.optString("stream_icon"),
                                rating = o.optString("rating"),
                                streamUrl = "${p.server}/live/${enc(p.username)}/${enc(p.password)}/$id.${p.output}",
                                epgId = o.optString("epg_channel_id")
                            )
                        )
                    }
                    MediaKind.MOVIE -> {
                        val id = o.optString("stream_id")
                        val ext = o.optString("container_extension", "mp4")
                        val release = firstNonBlank(o.optString("releaseDate"), o.optString("releasedate"))
                        add(
                            MediaEntry(
                                id = id,
                                name = o.optString("name"),
                                kind = kind,
                                categoryId = o.optString("category_id"),
                                image = o.optString("stream_icon"),
                                rating = o.optString("rating"),
                                plot = o.optString("plot"),
                                streamUrl = "${p.server}/movie/${enc(p.username)}/${enc(p.password)}/$id.$ext",
                                extension = ext,
                                year = firstNonBlank(o.optString("year"), release.take(4)),
                                duration = firstNonBlank(o.optString("duration"), o.optString("episode_run_time")),
                                cast = o.optString("cast"),
                                director = o.optString("director"),
                                genre = o.optString("genre"),
                                releaseDate = release
                            )
                        )
                    }
                    MediaKind.SERIES -> {
                        val id = o.optString("series_id")
                        val release = firstNonBlank(o.optString("releaseDate"), o.optString("releasedate"))
                        add(
                            MediaEntry(
                                id = id,
                                name = o.optString("name"),
                                kind = kind,
                                categoryId = o.optString("category_id"),
                                image = o.optString("cover"),
                                rating = o.optString("rating"),
                                plot = o.optString("plot"),
                                seriesId = id,
                                year = firstNonBlank(o.optString("year"), release.take(4)),
                                duration = firstNonBlank(o.optString("episode_run_time"), o.optString("duration")),
                                cast = o.optString("cast"),
                                director = o.optString("director"),
                                genre = o.optString("genre"),
                                releaseDate = release
                            )
                        )
                    }
                    else -> Unit
                }
            }
        }
    }

    fun details(item: MediaEntry): MediaEntry {
        return when (item.kind) {
            MediaKind.MOVIE -> vodDetails(item)
            MediaKind.SERIES -> seriesDetails(item)
            else -> item
        }
    }

    private fun vodDetails(item: MediaEntry): MediaEntry {
        val root = JSONObject(text(api("get_vod_info", "&vod_id=${enc(item.id)}")))
        val info = root.optJSONObject("info") ?: JSONObject()
        val movie = root.optJSONObject("movie_data") ?: JSONObject()
        val release = firstNonBlank(
            info.optString("releasedate"),
            info.optString("releaseDate"),
            item.releaseDate
        )
        val image = firstNonBlank(
            info.optString("movie_image"),
            info.optString("cover_big"),
            item.image
        )
        return item.copy(
            name = firstNonBlank(movie.optString("name"), info.optString("name"), item.name),
            image = image,
            rating = firstNonBlank(info.optString("rating"), item.rating),
            plot = firstNonBlank(info.optString("plot"), info.optString("description"), item.plot),
            year = firstNonBlank(info.optString("year"), release.take(4), item.year),
            duration = normalizeDuration(firstNonBlank(info.optString("duration"), info.optString("episode_run_time"), item.duration)),
            cast = firstNonBlank(info.optString("cast"), item.cast),
            director = firstNonBlank(info.optString("director"), item.director),
            genre = firstNonBlank(info.optString("genre"), item.genre),
            releaseDate = release
        )
    }

    private fun seriesDetails(item: MediaEntry): MediaEntry {
        val id = if (item.seriesId.isNotBlank()) item.seriesId else item.id
        val root = JSONObject(text(api("get_series_info", "&series_id=${enc(id)}")))
        val info = root.optJSONObject("info") ?: JSONObject()
        val release = firstNonBlank(
            info.optString("releaseDate"),
            info.optString("releasedate"),
            item.releaseDate
        )
        return item.copy(
            name = firstNonBlank(info.optString("name"), item.name),
            image = firstNonBlank(info.optString("cover"), item.image),
            rating = firstNonBlank(info.optString("rating"), item.rating),
            plot = firstNonBlank(info.optString("plot"), item.plot),
            year = firstNonBlank(info.optString("year"), release.take(4), item.year),
            duration = normalizeDuration(firstNonBlank(info.optString("episode_run_time"), info.optString("duration"), item.duration)),
            cast = firstNonBlank(info.optString("cast"), item.cast),
            director = firstNonBlank(info.optString("director"), item.director),
            genre = firstNonBlank(info.optString("genre"), item.genre),
            releaseDate = release
        )
    }

    fun episodes(seriesId: String): List<MediaEntry> {
        val root = JSONObject(text(api("get_series_info", "&series_id=${enc(seriesId)}")))
        val eps = root.optJSONObject("episodes") ?: return emptyList()
        val seriesInfo = root.optJSONObject("info") ?: JSONObject()
        val out = mutableListOf<MediaEntry>()
        eps.keys().asSequence().toList().sortedBy { it.toIntOrNull() ?: 999 }.forEach { seasonKey ->
            val a = eps.optJSONArray(seasonKey) ?: return@forEach
            for (i in 0 until a.length()) {
                val o = a.optJSONObject(i) ?: continue
                val info = o.optJSONObject("info") ?: JSONObject()
                val id = o.optString("id")
                val ext = o.optString("container_extension", "mp4")
                out += MediaEntry(
                    id = id,
                    name = o.optString("title", "Episode ${o.optInt("episode_num", i + 1)}"),
                    kind = MediaKind.EPISODE,
                    image = firstNonBlank(info.optString("movie_image"), seriesInfo.optString("cover")),
                    rating = info.optString("rating"),
                    plot = info.optString("plot"),
                    streamUrl = "${p.server}/series/${enc(p.username)}/${enc(p.password)}/$id.$ext",
                    extension = ext,
                    seriesId = seriesId,
                    season = seasonKey.toIntOrNull() ?: 0,
                    episode = o.optInt("episode_num", i + 1),
                    duration = normalizeDuration(firstNonBlank(info.optString("duration"), seriesInfo.optString("episode_run_time"))),
                    releaseDate = info.optString("releasedate")
                )
            }
        }
        return out
    }

    fun shortEpg(streamId: String): List<EpgItem> {
        val root = JSONObject(text(api("get_short_epg", "&stream_id=${enc(streamId)}&limit=4")))
        val a = root.optJSONArray("epg_listings") ?: return emptyList()
        fun b64(o: JSONObject, k: String) = runCatching {
            String(Base64.decode(o.optString(k), Base64.DEFAULT))
        }.getOrDefault(o.optString(k))
        return buildList {
            for (i in 0 until a.length()) {
                val o = a.optJSONObject(i) ?: continue
                add(
                    EpgItem(
                        b64(o, "title"),
                        b64(o, "description"),
                        o.optLong("start_timestamp"),
                        o.optLong("stop_timestamp")
                    )
                )
            }
        }
    }

    private fun firstNonBlank(vararg values: String): String =
        values.firstOrNull { it.isNotBlank() && it != "null" }?.trim().orEmpty()

    private fun normalizeDuration(raw: String): String {
        val s = raw.trim()
        if (s.isBlank() || s == "0" || s == "null") return ""
        if (s.contains(":")) return s
        val n = s.toIntOrNull() ?: return s
        return "$n Min."
    }
}
