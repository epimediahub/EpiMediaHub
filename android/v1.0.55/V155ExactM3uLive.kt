package de.epimediahub.app.data

import android.os.Build
import android.os.SystemClock
import android.util.Log
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap

/**
 * Non-Fire TV beta fallback for providers whose API supplies generated live URLs
 * but whose own authenticated get.php M3U advertises different per-channel URLs.
 *
 * Never downloads an M3U into a JSON tree or an unbounded String; parses one line
 * at a time. Bounded by elapsed time, scanned characters and lines. Only direct
 * authenticated playlist URLs are read, and logs never contain channel IDs,
 * account IDs, URLs, credentials or redirect locations.
 */
internal object V155ExactM3uLive {
    private const val MAX_LINES = 100_000
    private const val MAX_CHARS = 16_000_000L
    private const val SCAN_MS = 3_500L
    private const val COOLDOWN_MS = 90_000L
    private val retryAfter = ConcurrentHashMap<String, Long>()

    fun nonFireTvDevice(): Boolean {
        val brand = Build.BRAND.orEmpty().lowercase(Locale.ROOT)
        val maker = Build.MANUFACTURER.orEmpty().lowercase(Locale.ROOT)
        return brand != "amazon" && maker != "amazon"
    }

    /** Match by exact stream id, not display name or a partial path suffix. */
    internal fun matches(url: String, streamId: String): Boolean {
        if (streamId.isBlank() || streamId.length > 96) return false
        val uri = try { URI(url.trim()) } catch (_: Exception) { return false }
        if (uri.scheme?.lowercase(Locale.ROOT) !in setOf("http", "https")) return false
        if (uri.host.isNullOrBlank()) return false
        val query = uri.rawQuery.orEmpty()
        for (part in query.split('&')) {
            val name = part.substringBefore('=')
            val value = part.substringAfter('=', "")
            if (name in setOf("stream_id", "stream", "id") && value == streamId) return true
        }
        val name = uri.rawPath.orEmpty().substringAfterLast('/')
        val withoutExtension = name.substringBeforeLast('.', name)
        return name == streamId || withoutExtension == streamId
    }

    /** Publicly testable pure reader: constant-memory scan for one stream. */
    internal fun find(
        reader: BufferedReader,
        streamId: String,
        nowMs: () -> Long = SystemClock::elapsedRealtime
    ): String? {
        if (streamId.isBlank()) return null
        val started = nowMs()
        var chars = 0L
        for (i in 0 until MAX_LINES) {
            if (nowMs() - started > SCAN_MS || chars >= MAX_CHARS) return null
            val line = reader.readLine() ?: return null
            chars += line.length + 1
            if (line.length > 4096 || line.length < 8 || !line.startsWith("http", true)) continue
            if (matches(line, streamId)) return line.trim()
        }
        return null
    }

    /**
     * Called from XtreamClient.preparePlaybackItem on Dispatchers.IO only.
     * On failure, return null and keep legacy candidate handling unchanged.
     */
    fun resolve(m3uUrl: String, streamId: String, profileKey: String): String? {
        val now = SystemClock.elapsedRealtime()
        if (retryAfter[profileKey]?.let { now < it } == true) return null
        if (!m3uUrl.startsWith("http://", true) && !m3uUrl.startsWith("https://", true)) return null
        var target = URL(m3uUrl)
        var result: String? = null
        try {
            for (hop in 0..3) {
                if (target.protocol !in setOf("http", "https")) break
                val connection = (target.openConnection() as HttpURLConnection).apply {
                    instanceFollowRedirects = false
                    connectTimeout = 2_500
                    readTimeout = 3_500
                    setRequestProperty("User-Agent", "VLC/3.0.21 LibVLC/3.0.21")
                    setRequestProperty("Accept", "*/*")
                }
                var next: URL? = null
                try {
                    val code = connection.responseCode
                    if (code in setOf(301, 302, 303, 307, 308)) {
                        val location = connection.getHeaderField("Location")
                        if (!location.isNullOrBlank()) next = URL(target, location)
                    } else if (code in 200..299) {
                        result = connection.inputStream.bufferedReader(Charsets.UTF_8).use {
                            find(it, streamId)
                        }
                    }
                } finally {
                    connection.disconnect()
                }
                if (next != null) {
                    target = next
                } else {
                    break
                }
            }
        } catch (_: Exception) {
            // Provider unavailability must not be presented as a successful URL.
        }
        // No raw URL, profile key or stream id ever reaches logs.
        Log.i("EpiV155", if (result == null) "exact_m3u=unavailable" else "exact_m3u=resolved")
        if (result == null) retryAfter[profileKey] = now + COOLDOWN_MS
        return result
    }
}
