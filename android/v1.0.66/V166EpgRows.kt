package de.epimediahub.app.data

import de.epimediahub.app.model.EpgItem
import org.json.JSONArray
import org.json.JSONObject
import android.util.Base64
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/**
 * Convert the real-world Xtream EPG variants to Unix seconds BEFORE the
 * "JETZT" check. Several panels return timestamps in milliseconds, no
 * timestamp at all, or start/end strings in either local time or UTC.
 * Never fabricate a current programme out of a future-only schedule.
 */
internal object V166EpgTimes {
    data class Window(val start: Long, val end: Long) {
        fun contains(now: Long): Boolean = start <= now && now < end
    }

    private fun epoch(text: String): Long? {
        val raw = text.trim().toDoubleOrNull()?.toLong() ?: return null
        val seconds = when {
            raw >= 100_000_000_000_000L -> raw / 1_000_000L
            raw >= 100_000_000_000L -> raw / 1_000L
            else -> raw
        }
        return seconds.takeIf { it in 946684800L..4102444800L }
    }

    private fun date(text: String, zone: TimeZone): Long? {
        val raw = text.trim()
        if (!Regex("^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}$").matches(raw)) return null
        val format = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).apply {
            isLenient = false
            timeZone = zone
        }
        return runCatching { format.parse(raw)?.time?.div(1000L) }.getOrNull()
    }

    fun window(
        startTimestamp: String, stopTimestamp: String,
        startText: String, endText: String, now: Long,
        deviceZone: TimeZone = TimeZone.getDefault()
    ): Window? {
        fun validated(a: Long?, b: Long?): Window? =
            if (a != null && b != null && b > a && b - a <= 7L * 24 * 3600) Window(a, b) else null

        val numeric = validated(epoch(startTimestamp).orElse { epoch(startText) },
            epoch(stopTimestamp).orElse { epoch(endText) })
        val utc = TimeZone.getTimeZone("UTC")
        val local = validated(date(startText, deviceZone), date(endText, deviceZone))
        val universal = validated(date(startText, utc), date(endText, utc))
        val choices = listOfNotNull(numeric, local, universal).distinct()
        // Time-stamped data is authoritative if it already describes NOW.
        // Prefer a valid calendar representation only when the numeric
        // fields would incorrectly classify the present programme as future.
        return choices.firstOrNull { it.contains(now) } ?: choices.firstOrNull()
    }

    private inline fun <T> T?.orElse(other: () -> T?): T? = this ?: other()
}

internal object V166EpgRows {
    private fun plainOrBase64(obj: JSONObject, key: String): String {
        val original = obj.optString(key).trim()
        if (original.isBlank()) return ""
        val compact = original.replace("\\s".toRegex(), "")
        if (compact.length < 4 || compact.length % 4 == 1 ||
            !Regex("^[A-Za-z0-9+/]*={0,2}$").matches(compact)) return original
        val bytes = runCatching { Base64.decode(compact, Base64.DEFAULT) }.getOrNull() ?: return original
        if (bytes.isEmpty()) return original
        val verified = Base64.encodeToString(bytes, Base64.NO_WRAP).trimEnd('=') == compact.trimEnd('=')
        if (!verified) return original
        val decoded = String(bytes, Charsets.UTF_8)
        return decoded.takeIf { '\uFFFD' !in it && it.none { char ->
            Character.isISOControl(char) && char != '\n' && char != '\r' && char != '\t'
        } } ?: original
    }

    internal fun parse(root: JSONObject, now: Long): List<EpgItem> {
        val rows = root.optJSONArray("epg_listings") ?: return emptyList()
        return parseRows(rows, now)
    }

    private fun parseRows(rows: JSONArray, now: Long): List<EpgItem> {
        val events = ArrayList<EpgItem>(minOf(rows.length(), 256))
        for (i in 0 until minOf(rows.length(), 256)) {
            val row = rows.optJSONObject(i) ?: continue
            val title = plainOrBase64(row, "title").trim()
            if (title.isBlank()) continue
            val startTimestamp = row.optString("start_timestamp").ifBlank { row.optString("start_ts") }
            val stopTimestamp = row.optString("stop_timestamp").ifBlank {
                row.optString("end_timestamp").ifBlank { row.optString("stop_ts") }
            }
            val startText = row.optString("start")
            val endText = row.optString("end").ifBlank { row.optString("stop") }
            val window = V166EpgTimes.window(startTimestamp, stopTimestamp,
                startText, endText, now) ?: continue
            events.add(EpgItem(title, plainOrBase64(row, "description"),
                window.start, window.end))
        }
        return events.distinctBy { it.start to it.title }.sortedBy { it.start }
    }
}
