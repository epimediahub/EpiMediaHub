package de.epimediahub.app.data

import android.os.SystemClock
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors

/**
 * v1.0.56: Build one bounded in-memory ID->URL index per XTREAM playlist.
 *
 * v1.0.55 re-downloaded/scanned get.php for EVERY channel switch. The first
 * lookup may still take several seconds; later lookups in the same playlist
 * are pure map reads (no HTTP). Non-Amazon LIVE only, caller on Dispatchers.IO.
 *
 * No disk cache; URLs may embed passwords or expiring access tokens.
 */
internal object V156ExactM3uCache {
    private const val TTL_MS = 300_000L
    private const val RETRY_AFTER_MS = 90_000L
    private const val MAX_PROFILES = 2
    private const val MAX_LINES = 100_000
    private const val MAX_READ_CHARS = 16_000_000L
    private const val MAX_INDEX_CHARS = 5_000_000L
    private const val MAX_ITEMS = 30_000
    private const val SCAN_MS = 3_500L

    private data class Snapshot(val urls: Map<String, String>, val loadedAt: Long)
    private val snapshots = ConcurrentHashMap<String, Snapshot>()
    private val locks = ConcurrentHashMap<String, Any>()
    private val retryAfter = ConcurrentHashMap<String, Long>()
    private val inFlight = ConcurrentHashMap.newKeySet<String>()
    private val warmExecutor = Executors.newSingleThreadExecutor { task ->
        Thread(task, "EpiExactM3uWarmup").apply { isDaemon = true }
    }

    private fun fresh(key: String, now: Long): Snapshot? =
        snapshots[key]?.takeIf { now >= it.loadedAt && now - it.loadedAt < TTL_MS }

    /**
     * Prefetch while Live catalogue is showing; one worker regardless of how
     * many category navigations occur. Never block list scrolling.
     */
    fun warm(profileKey: String, url: String) {
        val now = SystemClock.elapsedRealtime()
        if (fresh(profileKey, now) != null || retryAfter[profileKey]?.let { now < it } == true) return
        if (!inFlight.add(profileKey)) return
        warmExecutor.execute {
            try { loadOnce(profileKey, url) }
            finally { inFlight.remove(profileKey) }
        }
    }

    /** Called by XtreamClient.preparePlaybackItem from its existing IO context. */
    fun resolve(profileKey: String, url: String, streamId: String): String? {
        if (streamId.isBlank()) return null
        val now = SystemClock.elapsedRealtime()
        fresh(profileKey, now)?.let { return it.urls[streamId] }
        if (retryAfter[profileKey]?.let { now < it } == true) return null
        return loadOnce(profileKey, url)?.urls?.get(streamId)
    }

    private fun loadOnce(profileKey: String, url: String): Snapshot? {
        // A channel switch waiting for background warm-up shares the SAME
        // request/scan. Never issue one get.php request per channel.
        val lock = locks.computeIfAbsent(profileKey) { Any() }
        synchronized(lock) {
            val now = SystemClock.elapsedRealtime()
            fresh(profileKey, now)?.let { return it }
            if (retryAfter[profileKey]?.let { now < it } == true) return null

            val index = try { downloadIndex(url) } catch (_: Exception) { null }
            if (index.isNullOrEmpty()) {
                retryAfter[profileKey] = SystemClock.elapsedRealtime() + RETRY_AFTER_MS
                return null
            }
            val snapshot = Snapshot(index, SystemClock.elapsedRealtime())
            snapshots[profileKey] = snapshot
            retryAfter.remove(profileKey)
            // Explicit max number of provider indices retained.
            while (snapshots.size > MAX_PROFILES) {
                val oldest = snapshots.entries.minByOrNull { it.value.loadedAt } ?: break
                snapshots.remove(oldest.key, oldest.value)
            }
            return snapshot
        }
    }

    private fun downloadIndex(m3uUrl: String): Map<String, String>? {
        if (!m3uUrl.startsWith("http://", true) &&
            !m3uUrl.startsWith("https://", true)) return null
        var target = URL(m3uUrl)
        val deadline = SystemClock.elapsedRealtime() + 6_000L
        repeat(4) {
            if (target.protocol !in setOf("http", "https") ||
                SystemClock.elapsedRealtime() >= deadline) return null
            val connection = (target.openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = false
                connectTimeout = 2_000
                readTimeout = 3_000
                setRequestProperty("User-Agent", "VLC/3.0.21 LibVLC/3.0.21")
                setRequestProperty("Accept", "*/*")
            }
            var redirect: URL? = null
            try {
                val code = connection.responseCode
                if (code in setOf(301, 302, 303, 307, 308)) {
                    connection.getHeaderField("Location")
                        ?.takeIf { it.isNotBlank() }
                        ?.let { redirect = URL(target, it) }
                } else if (code in 200..299) {
                    return connection.inputStream.bufferedReader(Charsets.UTF_8).use {
                        index(it, deadline)
                    }
                }
            } finally {
                connection.disconnect()
            }
            if (redirect == null) return null
            target = redirect!!
        }
        return null
    }

    /** Bounded parsing; only the IDs and their URLs are retained. */
    internal fun index(
        reader: BufferedReader,
        deadlineMs: Long = Long.MAX_VALUE,
        nowMs: () -> Long = SystemClock::elapsedRealtime
    ): Map<String, String> {
        val result = HashMap<String, String>()
        val started = nowMs()
        var readChars = 0L
        var indexedChars = 0L
        repeat(MAX_LINES) {
            if (nowMs() - started >= SCAN_MS || nowMs() >= deadlineMs ||
                readChars >= MAX_READ_CHARS || result.size >= MAX_ITEMS ||
                indexedChars >= MAX_INDEX_CHARS) return result

            val line = reader.readLine() ?: return result
            readChars += line.length + 1L
            if (line.length < 10 || line.length > 4096 || !line.startsWith("http", true)) return@repeat

            val streamId = streamId(line) ?: return@repeat
            val trimmed = line.trim()
            if (indexedChars + trimmed.length > MAX_INDEX_CHARS) return result
            if (!result.containsKey(streamId)) {
                result[streamId] = trimmed
                indexedChars += trimmed.length
            }
        }
        return result
    }

    /** Same identity rules as the v1.0.55 exact stream finder. */
    internal fun streamId(raw: String): String? {
        val uri = try { URI(raw.trim()) } catch (_: Exception) { return null }
        if (uri.scheme?.lowercase(Locale.ROOT) !in setOf("http", "https") ||
            uri.host.isNullOrBlank()) return null

        for (param in uri.rawQuery.orEmpty().split('&')) {
            val name = param.substringBefore('=')
            if (name in setOf("stream_id", "stream", "id")) {
                val value = param.substringAfter('=', "")
                return value.takeIf { it.isNotBlank() && it.length <= 96 }
            }
        }
        val finalName = uri.rawPath.orEmpty().substringAfterLast('/')
        val id = finalName.substringBeforeLast('.', finalName)
        return id.takeIf { it.isNotBlank() && it.length <= 96 }
    }
}
