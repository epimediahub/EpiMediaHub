package de.epimediahub.app.vpn

import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject
import java.util.Timer
import java.util.TimerTask
import java.util.concurrent.CancellationException
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
import java.util.concurrent.ConcurrentHashMap

/**
 * Checks the bound VPN route at a fixed cadence rather than on every 64 KiB
 * read/write. A failed verification still aborts the HTTPS operation.
 *
 * Android's VPN-network pin remains attached; its onLost callback immediately
 * marks the session blocked. This only reduces redundant polling overhead.
 */
internal class V145RouteGuard(
    private val verify: () -> Unit,
    private val clockNanos: () -> Long = System::nanoTime
) {
    companion object { const val INTERVAL_NANOS: Long = 125_000_000L }
    private var lastVerifiedAt = clockNanos()

    fun checkIfDue() {
        val now = clockNanos()
        if (now < lastVerifiedAt || now - lastVerifiedAt >= INTERVAL_NANOS) {
            verify() // Always commit the timestamp after a successful validation.
            lastVerifiedAt = now
        }
    }

    fun force() {
        verify()
        lastVerifiedAt = clockNanos()
    }
}

/**
 * A remote test-server rejection is not equivalent to losing VPN routing.
 * Only this error class is eligible for a reduced-concurrency retry.
 */
internal class V146SpeedServerException(
    val httpStatus: Int, direction: String, val host: String
) : IllegalStateException("$direction-Testserver ($host): HTTP $httpStatus")

/** Actual bounded HTTP transfers, independent of Android UI and VPN credentials. */
internal class V140SpeedTransfer(initialSelfHostedToken: String? = null) {
    data class Sample(val bytes: Long, val nanos: Long) {
        val mbps: Double get() = bytes * 8_000.0 / nanos.coerceAtLeast(1L)
    }

    // Each click gets a new instance. A cancelled run can never be revived.
    private val selfHostedToken = AtomicReference<String?>(initialSelfHostedToken)
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

    /**
     * Issue a short-lived token via the pinned network route. It is used ONLY for
     * speedtest.epimediahub.com; never forward it to backup test providers.
     */
    fun openSelfHostedSession(verify: () -> Unit): String {
        var session = ""
        transfer("https://speedtest.epimediahub.com/v1/session", verify) { conn, _ ->
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.setFixedLengthStreamingMode(0)
            conn.outputStream.use { }
            val code = conn.responseCode
            if (code != 200) {
                throw V146SpeedServerException(code, "Sitzung", conn.url.host)
            }
            val body = conn.inputStream.bufferedReader().use { it.readText() }
            check(body.length in 1..4096) { "Ungültige Speedtest-Antwort" }
            val json = JSONObject(body)
            val issued = json.getString("session")
            check(Regex("[A-Za-z0-9_-]{32,128}").matches(issued)) {
                "Ungültiger Speedtest-Sitzungsschlüssel"
            }
            check(json.optInt("ttlSeconds") >= 60 && json.optInt("maxStreams") >= 4) {
                "Speedtest-Serverprotokoll ist nicht kompatibel"
            }
            session = issued
            body.length.toLong()
        }
        checkActive()
        verify()
        check(session.isNotEmpty()) { "Speedtest-Sitzung fehlt" }
        selfHostedToken.set(session)
        return session
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
        // Strict origin allowlist: prevents leaking the ephemeral session token
        // if a public backup provider is used. Redirects stay disabled.
        if (conn.url.protocol == "https" &&
            conn.url.host.equals("speedtest.epimediahub.com", ignoreCase = true)
        ) {
            selfHostedToken.get()?.let {
                conn.setRequestProperty("Authorization", "Bearer $it")
            }
        }
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
            val responseCode = conn.responseCode
            if (responseCode != 200) {
                throw V146SpeedServerException(responseCode, "Download", conn.url.host)
            }
            var received = 0L
            var lastReport = started
            val routeGuard = V145RouteGuard(verify)
            conn.inputStream.use { stream ->
                val buffer = ByteArray(64 * 1024)
                while (true) {
                    checkActive()
                    routeGuard.checkIfDue()
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
            routeGuard.force()
            check(received == bytes.toLong()) { "Unvollständiger Download ($received / $bytes)" }
            onSample(Sample(received, System.nanoTime() - started))
            received
        }

    /**
     * Alternate public HTTPS test file, e.g. Hetzner HEL1 100MB.bin.
     * Do not download the whole 100 MB into memory or into device storage.
     * A bounded range is requested; accept a server ignoring Range (HTTP 200)
     * but READ EXACTLY the specified number of bytes, then disconnect.
     */
    fun downloadFilePrefixLive(
        url: String, bytes: Int, verify: () -> Unit, onSample: (Sample) -> Unit
    ): Sample = downloadFileRangeLive(url, 0, bytes, verify, onSample)

    /**
     * Independent byte ranges avoid four requests for the identical file prefix.
     * Nonzero offsets require the server to honor HTTP Range (206).
     */
    fun downloadFileRangeLive(
        url: String, offset: Long, bytes: Int, verify: () -> Unit,
        onSample: (Sample) -> Unit
    ): Sample = transfer(url, verify) { conn, started ->
        require(bytes in 32..(64 * 1024 * 1024))
        require(offset >= 0 && offset + bytes <= 100_000_000L)
        conn.setRequestProperty("Range", "bytes=$offset-${offset + bytes - 1}")
        val responseCode = conn.responseCode
        if (responseCode != 200 && responseCode != 206) {
            throw V146SpeedServerException(responseCode, "Download", conn.url.host)
        }
        if (offset > 0L && responseCode != 206) {
            error("Testserver unterstützt keine Teilbereiche (HTTP Range)")
        }
        if (responseCode == 206) {
            val range = conn.getHeaderField("Content-Range").orEmpty()
            check(range.startsWith("bytes $offset-${offset + bytes - 1}/")) {
                "Testserver lieferte einen unerwarteten HTTP-Bereich"
            }
        }
        val length = conn.contentLengthLong
        check(length == -1L || length >= bytes) {
            "Testserver liefert zu wenige Daten"
        }
        val guard = V145RouteGuard(verify)
        var received = 0L
        var lastReport = started
        conn.inputStream.use { stream ->
            val buffer = ByteArray(64 * 1024)
            while (received < bytes.toLong()) {
                checkActive()
                guard.checkIfDue()
                val next = minOf(buffer.size.toLong(), bytes.toLong() - received).toInt()
                val count = stream.read(buffer, 0, next)
                check(count > 0) { "Alternativer Testserver: unvollständige Daten" }
                received += count
                val now = System.nanoTime()
                if (now - lastReport >= 200_000_000L) {
                    onSample(Sample(received, now - started))
                    lastReport = now
                }
            }
        }
        guard.force()
        val final = Sample(received, System.nanoTime() - started)
        onSample(final)
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
            val routeGuard = V145RouteGuard(verify)
            conn.outputStream.use { stream ->
                val buffer = ByteArray(64 * 1024)
                var sent = 0
                while (sent < bytes) {
                    checkActive()
                    routeGuard.checkIfDue()
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
            routeGuard.force()
            val responseCode = conn.responseCode
            if (responseCode !in 200..299) {
                throw V146SpeedServerException(responseCode, "Upload", conn.url.host)
            }
            conn.inputStream.use { input ->
                val buffer = ByteArray(1024)
                var responseBytes = 0
                while (true) {
                    checkActive()
                    routeGuard.checkIfDue()
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
