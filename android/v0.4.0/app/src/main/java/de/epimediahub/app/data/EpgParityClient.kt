package de.epimediahub.app.data

import android.util.Base64
import de.epimediahub.app.model.EpgItem
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.PlaylistProfile
import de.epimediahub.app.model.PlaylistType
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

object EpgParityClient {
    private fun enc(value: String) = URLEncoder.encode(value, "UTF-8")

    private fun api(profile: PlaylistProfile, action: String = "", extra: String = ""): String {
        val actionPart = if (action.isBlank()) "" else "&action=$action"
        return "${profile.server}/player_api.php?username=${enc(profile.username)}&password=${enc(profile.password)}$actionPart$extra"
    }

    private fun text(url: String): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 10000
            readTimeout = 25000
            setRequestProperty("User-Agent", "EpiMediaHub-Android/0.4.0")
        }
        val code = connection.responseCode
        if (code !in 200..299) throw IllegalStateException("EPG HTTP $code")
        return connection.inputStream.bufferedReader().use { it.readText() }
    }

    private fun decoded(value: String): String {
        if (value.isBlank()) return ""
        return runCatching { String(Base64.decode(value, Base64.DEFAULT), Charsets.UTF_8) }
            .getOrDefault(value)
            .trim()
    }

    private fun parseArray(root: JSONObject): JSONArray =
        root.optJSONArray("epg_listings")
            ?: root.optJSONObject("epg")?.optJSONArray("epg_listings")
            ?: JSONArray()

    fun fullEpg(profile: PlaylistProfile, streamId: String): List<EpgItem> {
        if (profile.type != PlaylistType.XTREAM || streamId.isBlank()) return emptyList()
        val urls = listOf(
            api(profile, "get_simple_data_table", "&stream_id=${enc(streamId)}"),
            api(profile, "get_short_epg", "&stream_id=${enc(streamId)}&limit=100")
        )
        for (url in urls) {
            val list = runCatching {
                val root = JSONObject(text(url))
                val rows = parseArray(root)
                buildList {
                    for (i in 0 until rows.length()) {
                        val row = rows.optJSONObject(i) ?: continue
                        val start = row.optLong("start_timestamp", 0L).takeIf { it > 0L }
                            ?: parseDate(row.optString("start"))
                        val end = row.optLong("stop_timestamp", 0L).takeIf { it > 0L }
                            ?: parseDate(row.optString("end").ifBlank { row.optString("stop") })
                        if (start <= 0L || end <= start) continue
                        val title = decoded(row.optString("title")).ifBlank { row.optString("title") }
                        val description = decoded(row.optString("description")).ifBlank { row.optString("description") }
                        add(EpgItem(title.ifBlank { "Sendung" }, description, start, end))
                    }
                }.distinctBy { Triple(it.start, it.end, it.title) }.sortedBy { it.start }
            }.getOrDefault(emptyList())
            if (list.isNotEmpty()) return list
        }
        return emptyList()
    }

    fun catchupAvailable(profile: PlaylistProfile, channel: MediaEntry, event: EpgItem): Boolean {
        if (profile.type != PlaylistType.XTREAM || !channel.tvArchive || channel.tvArchiveDurationDays <= 0) return false
        val now = System.currentTimeMillis() / 1000L
        if (event.start <= 0L || event.end > now + 300L) return false
        val oldest = now - channel.tvArchiveDurationDays.toLong() * 86400L - 7200L
        return event.start >= oldest
    }

    fun catchupUrl(profile: PlaylistProfile, channel: MediaEntry, event: EpgItem): String {
        if (!catchupAvailable(profile, channel, event)) return ""
        val duration = ((maxOf(event.start + 60L, event.end) - event.start + 59L) / 60L).coerceAtLeast(1L)
        val offset = serverUtcOffset(profile)
        val stampMs = (event.start + (offset ?: 0L)) * 1000L
        val format = SimpleDateFormat("yyyy-MM-dd:HH-mm", Locale.US).apply {
            timeZone = TimeZone.getTimeZone(if (offset == null) TimeZone.getDefault().id else "UTC")
        }
        val startText = format.format(Date(stampMs))
        val ext = if (profile.output.equals("m3u8", true)) "m3u8" else "ts"
        return "${profile.server.trimEnd('/')}/timeshift/${enc(profile.username)}/${enc(profile.password)}/$duration/$startText/${enc(channel.id)}.$ext"
    }

    private fun serverUtcOffset(profile: PlaylistProfile): Long? = runCatching {
        val root = JSONObject(text(api(profile)))
        val server = root.optJSONObject("server_info") ?: return@runCatching null
        val timestamp = server.optLong("timestamp_now", 0L)
        val timeNow = server.optString("time_now")
        if (timestamp <= 0L || timeNow.length < 19) return@runCatching null
        val format = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }
        val shown = (format.parse(timeNow.substring(0, 19))?.time ?: return@runCatching null) / 1000L
        (shown - timestamp).takeIf { kotlin.math.abs(it) <= 15L * 3600L }
    }.getOrNull()

    private fun parseDate(value: String): Long {
        if (value.isBlank()) return 0L
        val formats = listOf("yyyy-MM-dd HH:mm:ss", "yyyyMMddHHmmss Z", "yyyyMMddHHmmssZ", "yyyyMMddHHmmss")
        for (pattern in formats) {
            val parsed = runCatching { SimpleDateFormat(pattern, Locale.US).parse(value.trim())?.time ?: 0L }.getOrDefault(0L)
            if (parsed > 0L) return parsed / 1000L
        }
        return 0L
    }
}
