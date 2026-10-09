package de.epimediahub.app.vpn

import java.net.HttpURLConnection
import java.net.URL
import java.util.Timer
import java.util.TimerTask
import java.util.concurrent.CancellationException
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import java.util.concurrent.ConcurrentHashMap

/** Actual bounded HTTP transfers, independent of Android UI and VPN credentials. */
internal class V140SpeedTransfer {
    data class Sample(val bytes: Long, val nanos: Long) {
        val mbps: Double get() = bytes * 8_000.0 / nanos.coerceAtLeast(1L)
    }

    // Each click gets a new instance. A cancelled run can never be revived.
    private val cancelled = AtomicBoolean(false)
    private val active = AtomicReference<HttpURLConnection?>(null)
    // Multi-stream benchmarks have independent sockets; cancelling a test must
    // disconnect every worker rather than leaving an unprotected request alive.
    private val children = ConcurrentHashMap.newKeySet<V140SpeedTransfer>()
    fun isCancelled(): Boolean = cancelled.get()
    fun registerWorker(worker: V140SpeedTransfer) {
        checkActive()
        children.add(worker)
        if (isCancelled()) {
            worker.cancel()
            checkActive()
        }
    }
    fun unregisterWorker(worker: V140SpeedTransfer) { children.remove(worker) }
    fun cancel() {
        cancelled.set(true)
        active.getAndSet(null)?.disconnect()
        children.forEach { it.cancel() }
    }
    fun checkActive() {
        if (cancelled.get()) throw CancellationException("Messung abgebrochen")
    }

    private fun transfer(url: String, verify: () -> Unit,
                         body: (HttpURLConnection, Long) -> Long): Sample {
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
            val bytes = body(conn, started)
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

    /**
     * Real throughput samples emitted from received/sent byte counts, throttled
     * to protect low-powered TV sticks from excessive Compose recomposition.
     * Verifying the selected route remains a separate, mandatory check.
     */
    /** Keep the existing route-verification call signature unambiguous. */
    fun download(url: String, bytes: Int, verify: () -> Unit): Sample =
        downloadLive(url, bytes, verify) {}

    /** Live sample callback is deliberately a distinct API for Kotlin trailing lambdas. */
    fun downloadLive(url: String, bytes: Int, verify: () -> Unit,
                     onSample: (Sample) -> Unit): Sample =
        transfer(url, verify) { conn, started ->
            check(conn.responseCode == 200) { "Download-Testserver: HTTP ${conn.responseCode}" }
            var received = 0L
            var lastReport = started
            conn.inputStream.use { stream ->
                val buffer = ByteArray(64 * 1024)
                while (true) {
                    checkActive()
                    verify()
                    val n = stream.read(buffer)
                    if (n < 0) break
                    received += n
                    check(received <= bytes) { "Unerwartete Downloadgröße" }
                    val now = System.nanoTime()
                    if (now - lastReport >= 200_000_000L) {
                        onSample(Sample(received, now - started))
                        lastReport = now
                    }
                }
            }
            check(received == bytes.toLong()) { "Unvollständiger Download ($received / $bytes)" }
            onSample(Sample(received, System.nanoTime() - started))
            received
        }

    fun upload(url: String, bytes: Int, verify: () -> Unit): Sample =
        uploadLive(url, bytes, verify) {}

    fun uploadLive(url: String, bytes: Int, verify: () -> Unit,
                   onSample: (Sample) -> Unit): Sample =
        transfer(url, verify) { conn, started ->
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/octet-stream")
            conn.setFixedLengthStreamingMode(bytes)
            var lastReport = started
            conn.outputStream.use { stream ->
                val buffer = ByteArray(64 * 1024)
                var sent = 0
                while (sent < bytes) {
                    checkActive()
                    verify()
                    val n = minOf(buffer.size, bytes - sent)
                    stream.write(buffer, 0, n)
                    sent += n
                    val now = System.nanoTime()
                    if (now - lastReport >= 200_000_000L) {
                        onSample(Sample(sent.toLong(), now - started))
                        lastReport = now
                    }
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
            onSample(Sample(bytes.toLong(), System.nanoTime() - started))
            bytes.toLong()
        }
}
