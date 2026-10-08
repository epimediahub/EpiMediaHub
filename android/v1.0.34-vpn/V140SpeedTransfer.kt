package de.epimediahub.app.vpn

import java.net.HttpURLConnection
import java.net.URL
import java.util.Timer
import java.util.TimerTask
import java.util.concurrent.CancellationException
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

/** Actual bounded HTTP transfers, independent of Android UI and VPN credentials. */
internal class V140SpeedTransfer {
    data class Sample(val bytes: Long, val nanos: Long) {
        val mbps: Double get() = bytes * 8_000.0 / nanos.coerceAtLeast(1L)
    }

    // Each click gets a new instance. A cancelled run can never be revived.
    private val cancelled = AtomicBoolean(false)
    private val active = AtomicReference<HttpURLConnection?>(null)
    fun isCancelled(): Boolean = cancelled.get()
    fun cancel() {
        cancelled.set(true)
        active.getAndSet(null)?.disconnect()
    }
    fun checkActive() {
        if (cancelled.get()) throw CancellationException("Messung abgebrochen")
    }

    private fun transfer(url: String, verify: () -> Unit,
                         body: (HttpURLConnection) -> Long): Sample {
        checkActive()
        verify()
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 8_000
        conn.readTimeout = 8_000
        conn.instanceFollowRedirects = false
        conn.useCaches = false
        conn.setRequestProperty("Cache-Control", "no-store")
        conn.setRequestProperty("Accept-Encoding", "identity")
        active.set(conn)
        val expired = AtomicBoolean(false)
        val timer = Timer("epimedia-speedtest-deadline", true)
        timer.schedule(object : TimerTask() {
            override fun run() { expired.set(true); conn.disconnect() }
        }, 45_000)
        try {
            checkActive() // Includes cancellation racing with active.set().
            val started = System.nanoTime()
            val bytes = body(conn)
            val elapsed = (System.nanoTime() - started).coerceAtLeast(1L)
            checkActive()
            check(!expired.get()) { "Zeitlimit für die Messung überschritten" }
            verify()
            return Sample(bytes, elapsed)
        } catch (e: Exception) {
            checkActive()
            check(!expired.get()) { "Zeitlimit für die Messung überschritten" }
            throw e
        } finally {
            timer.cancel()
            active.compareAndSet(conn, null)
            conn.disconnect()
        }
    }

    fun download(url: String, bytes: Int, verify: () -> Unit): Sample =
        transfer(url, verify) { conn ->
            check(conn.responseCode == 200) { "Download-Testserver: HTTP ${conn.responseCode}" }
            var received = 0L
            conn.inputStream.use { stream ->
                val buffer = ByteArray(64 * 1024)
                while (true) {
                    checkActive()
                    verify()
                    val n = stream.read(buffer)
                    if (n < 0) break
                    received += n
                    check(received <= bytes) { "Unerwartete Downloadgröße" }
                }
            }
            check(received == bytes.toLong()) { "Unvollständiger Download ($received / $bytes)" }
            received
        }

    fun upload(url: String, bytes: Int, verify: () -> Unit): Sample =
        transfer(url, verify) { conn ->
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/octet-stream")
            conn.setFixedLengthStreamingMode(bytes)
            conn.outputStream.use { stream ->
                val buffer = ByteArray(64 * 1024)
                var sent = 0
                while (sent < bytes) {
                    checkActive()
                    verify()
                    val n = minOf(buffer.size, bytes - sent)
                    stream.write(buffer, 0, n)
                    sent += n
                }
            }
            check(conn.responseCode in 200..299) { "Upload-Testserver: HTTP ${conn.responseCode}" }
            conn.inputStream.use { input ->
                val buffer = ByteArray(1024)
                var responseBytes = 0
                while (true) {
                    checkActive()
                    verify()
                    val n = input.read(buffer)
                    if (n < 0) break
                    responseBytes += n
                    check(responseBytes <= 64 * 1024) { "Unerwartete Upload-Antwort" }
                }
            }
            bytes.toLong()
        }
}
