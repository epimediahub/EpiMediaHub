package de.epimediahub.app.data

import de.epimediahub.app.model.MediaKind
import org.json.JSONObject
import java.text.ParsePosition
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/** Interpret upload / update dates provided by Xtream-compatible servers. */
internal object V158ProviderDates {
    private const val EARLIEST = 946684800L  // 2000-01-01
    private const val LATEST = 4102444800L   // 2100-01-01

    fun fromRow(item: JSONObject, kind: MediaKind): Long {
        // Series use last_modified for the latest added season/episode on many servers.
        // Movies commonly use "added". Fall back to the other supported fields.
        val fields = when (kind) {
            MediaKind.SERIES -> listOf("last_modified", "added", "date_added", "added_at", "created_at")
            MediaKind.MOVIE -> listOf("added", "date_added", "added_at", "created_at", "last_modified")
            else -> emptyList()
        }
        for (field in fields) {
            if (!item.has(field) || item.isNull(field)) continue
            val value = parse(item.optString(field))
            if (value > 0L) return value
        }
        return 0L
    }

    fun parse(raw: String): Long {
        val value = raw.trim()
        if (value.isEmpty() || value.lowercase(Locale.ROOT) in setOf("null", "none", "0", "-1")) return 0L
        val integer = value.toLongOrNull()
        if (integer != null) {
            val seconds = if (integer > 9999999999L) integer / 1000L else integer
            return seconds.takeIf { it in EARLIEST..LATEST } ?: 0L
        }
        val formats = listOf(
            "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
            "yyyy-MM-dd'T'HH:mm:ssXXX",
            "yyyy-MM-dd'T'HH:mm:ss.SSSX",
            "yyyy-MM-dd'T'HH:mm:ssX",
            "yyyy-MM-dd'T'HH:mm:ss.SSS",
            "yyyy-MM-dd'T'HH:mm:ss",
            "yyyy-MM-dd HH:mm:ss",
            "yyyy-MM-dd"
        )
        for (pattern in formats) {
            val parser = SimpleDateFormat(pattern, Locale.ROOT).apply {
                isLenient = false
                timeZone = TimeZone.getTimeZone("UTC")
            }
            val position = ParsePosition(0)
            val date = parser.parse(value, position)
            if (date != null && position.index == value.length) {
                val seconds = date.time / 1000L
                if (seconds in EARLIEST..LATEST) return seconds
            }
        }
        return 0L
    }
}
