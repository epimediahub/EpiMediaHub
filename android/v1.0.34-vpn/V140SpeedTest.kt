package de.epimediahub.app.vpn

import android.content.Context
import android.os.SystemClock
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Real, finite HTTP throughput test. Cloudflare speed.cloudflare.com/__down and
 * /__up are public speed-test endpoints. No mock readings or credential uploads.
 * Requires the current playlist's route to remain verified throughout the test.
 */
internal object V140SpeedTest {
    data class Result(val route: String, val ip: String, val latencyMs: Long,
        val downloadMbps: Double, val uploadMbps: Double, val bytes: Long)

    private const val HOST = "https://speed.cloudflare.com"
    private const val DOWNLOAD_BYTES = 8 * 1024 * 1024
    private const val UPLOAD_BYTES = 2 * 1024 * 1024
    private const val CHUNK = 64 * 1024

    private fun verifyRoute(context: Context, playlistId: String, vpn: Boolean,
                            cancelled: AtomicBoolean) {
        if (cancelled.get()) throw CancellationException("Messung abgebrochen")
        check(V134VpnSession.mode(context, playlistId) == vpn) {
            "Playlist-Routing wurde geändert. Messung abgebrochen."
        }
        check(V134VpnSession.routeReady(context, playlistId)) {
            "VPN-Verbindung nicht bestätigt. Kein automatischer Direkt-Fallback."
        }
    }

    private fun connection(url: String): HttpURLConnection {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 8_000
        conn.readTimeout = 8_000
        conn.instanceFollowRedirects = false
        conn.useCaches = false
        conn.setRequestProperty("Cache-Control", "no-store")
        return conn
    }

    private fun download(context: Context, playlistId: String, vpn: Boolean,
                         cancelled: AtomicBoolean, bytes: Int): Pair<Long, Long> {
        verifyRoute(context, playlistId, vpn, cancelled)
        val conn = connection("$HOST/__down?bytes=$bytes")
        try {
            val started = SystemClock.elapsedRealtimeNanos()
            check(conn.responseCode == 200) { "Download-Testserver: HTTP ${conn.responseCode}" }
            var received = 0L
            conn.inputStream.use { stream ->
                val buffer = ByteArray(CHUNK)
                while (true) {
                    verifyRoute(context, playlistId, vpn, cancelled)
                    val n = stream.read(buffer)
                    if (n < 0) break
                    received += n
                    check(received <= bytes.toLong()) { "Unerwartete Downloadgröße" }
                }
            }
            check(received == bytes.toLong()) { "Unvollständiger Download ($received / $bytes)" }
            val elapsed = (SystemClock.elapsedRealtimeNanos() - started).coerceAtLeast(1L)
            verifyRoute(context, playlistId, vpn, cancelled)
            return received to elapsed
        } finally { conn.disconnect() }
    }

    private fun upload(context: Context, playlistId: String, vpn: Boolean,
                       cancelled: AtomicBoolean): Pair<Long, Long> {
        verifyRoute(context, playlistId, vpn, cancelled)
        val conn = connection("$HOST/__up")
        try {
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/octet-stream")
            conn.setFixedLengthStreamingMode(UPLOAD_BYTES)
            val started = SystemClock.elapsedRealtimeNanos()
            conn.outputStream.use { stream ->
                val buffer = ByteArray(CHUNK) // empty bytes, never VPN keys or user media
                var sent = 0
                while (sent < UPLOAD_BYTES) {
                    verifyRoute(context, playlistId, vpn, cancelled)
                    val n = minOf(buffer.size, UPLOAD_BYTES - sent)
                    stream.write(buffer, 0, n)
                    sent += n
                }
                stream.flush()
            }
            check(conn.responseCode in 200..299) { "Upload-Testserver: HTTP ${conn.responseCode}" }
            conn.inputStream.use { input ->
                val buffer = ByteArray(256)
                while (input.read(buffer) != -1) { /* drain server response */ }
            }
            val elapsed = (SystemClock.elapsedRealtimeNanos() - started).coerceAtLeast(1L)
            verifyRoute(context, playlistId, vpn, cancelled)
            return UPLOAD_BYTES.toLong() to elapsed
        } finally { conn.disconnect() }
    }

    fun measure(context: Context, playlistId: String, cancelled: AtomicBoolean,
                progress: (String) -> Unit): Result {
        val vpn = V134VpnSession.mode(context, playlistId)
        verifyRoute(context, playlistId, vpn, cancelled)
        val before = V134VpnSession.publicIpv4()
        check(if (vpn) before == "37.27.42.215" else before != "37.27.42.215") {
            "IP stimmt nicht mit dem gewählten Routing überein"
        }
        verifyRoute(context, playlistId, vpn, cancelled)
        progress("HTTP-Latenz wird gemessen …")
        // Small transaction including HTTPS setup: not an ICMP ping.
        val latencyStart = SystemClock.elapsedRealtimeNanos()
        download(context, playlistId, vpn, cancelled, 32)
        val latencyMs = ((SystemClock.elapsedRealtimeNanos() - latencyStart) / 1_000_000).coerceAtLeast(1L)
        progress("Download: 8 MiB über aktive Verbindung …")
        val (received, downloadTime) = download(context, playlistId, vpn, cancelled, DOWNLOAD_BYTES)
        progress("Upload: 2 MiB über aktive Verbindung …")
        val (sent, uploadTime) = upload(context, playlistId, vpn, cancelled)
        progress("Öffentliche IP wird abschließend geprüft …")
        verifyRoute(context, playlistId, vpn, cancelled)
        val after = V134VpnSession.publicIpv4()
        check(before == after) { "Öffentliche IP hat sich während des Tests geändert" }
        verifyRoute(context, playlistId, vpn, cancelled)
        return Result(if (vpn) "VPN FINNLAND" else "DIREKT", after, latencyMs,
            received * 8_000.0 / downloadTime, sent * 8_000.0 / uploadTime, received + sent)
    }
}

/** Small, focusable shortcut beside the existing Radio and Playlist actions. */
@Composable
internal fun V140SpeedShortcutButton(accent: Color, isTv: Boolean, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    Surface(
        modifier = Modifier.size(if (isTv) 44.dp else 40.dp)
            .onFocusChanged { focused = it.hasFocus }
            .semantics { contentDescription = "Speedtest" }
            .testTag("home-speedtest")
            .clickable(role = Role.Button, onClick = onClick),
        color = if (focused) accent else Color(0xF51A222C),
        contentColor = Color.White,
        shape = CircleShape,
        border = BorderStroke(if (focused) 3.dp else 1.dp,
            if (focused) Color.White else Color.White.copy(.3f))
    ) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("⇅", fontSize = if (isTv) 25.sp else 22.sp, fontWeight = FontWeight.Black)
        }
    }
}

@Composable
internal fun V140SpeedTestScreen(context: Context, playlistId: String?, isTv: Boolean,
                                 accent: Color, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("Bereit. Misst die aktuell ausgewählte Netzwerkroute.") }
    var result by remember { mutableStateOf<V140SpeedTest.Result?>(null) }
    val cancelled = remember { AtomicBoolean(false) }
    var job by remember { mutableStateOf<Job?>(null) }
    fun stop() {
        cancelled.set(true)
        job?.cancel()
        busy = false
    }
    BackHandler { stop(); onBack() }
    Column(
        Modifier.fillMaxSize().background(Color(0xFF07111D))
            .verticalScroll(rememberScrollState())
            .padding(horizontal = if (isTv) 48.dp else 18.dp, vertical = if (isTv) 28.dp else 12.dp)
            .testTag("speedtest-screen"),
        verticalArrangement = Arrangement.spacedBy(20.dp)
    ) {
        Text("NETZWERK · SPEEDTEST", color = Color.White, fontSize = if (isTv) 28.sp else 20.sp,
            fontWeight = FontWeight.Black)
        Text("Echte Messung über speed.cloudflare.com: 8 MiB Download + 2 MiB Upload. " +
            "Die HTTP-Latenz beinhaltet TLS-Aufbau und ist kein ICMP-Ping.",
            color = Color.White.copy(.74f), fontSize = if (isTv) 17.sp else 14.sp)
        Text(status, color = if (status.contains("Fehler") || status.contains("abgebrochen"))
            Color(0xFFFFB4A9) else accent, fontSize = if (isTv) 19.sp else 15.sp)
        result?.let {
            Text("Verbindung: ${it.route}   •   Öffentliche IP: ${it.ip}",
                color = Color.White, fontWeight = FontWeight.Bold)
            Text(String.format(Locale.GERMANY, "↓  %.1f Mbit/s     ↑  %.1f Mbit/s",
                it.downloadMbps, it.uploadMbps), color = accent,
                fontSize = if (isTv) 35.sp else 25.sp, fontWeight = FontWeight.Black)
            Text("HTTP-Latenz: ${it.latencyMs} ms   •   Daten: ${it.bytes / 1_048_576} MiB",
                color = Color.White.copy(.8f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(
                onClick = {
                    if (busy || playlistId == null) return@Button
                    cancelled.set(false)
                    busy = true
                    result = null
                    job = scope.launch {
                        try {
                            val measured = withContext(Dispatchers.IO) {
                                V140SpeedTest.measure(context, playlistId, cancelled) { progress ->
                                    // Compose state must be updated on the UI dispatcher.
                                    // Progress is informational; never modify routing from this screen.
                                    status = progress
                                }
                            }
                            if (!cancelled.get()) {
                                result = measured
                                status = "Messung erfolgreich abgeschlossen."
                            }
                        } catch (e: CancellationException) {
                            status = "Messung abgebrochen."
                        } catch (e: Exception) {
                            status = "Fehler: ${e.message ?: "Netzwerk nicht verfügbar"}"
                        } finally { busy = false }
                    }
                }, enabled = !busy && playlistId != null, modifier = Modifier.testTag("speedtest-start")
            ) { Text(if (busy) "Messung läuft …" else "Speedtest starten") }
            if (busy) OutlinedButton(onClick = {
                stop()
                status = "Messung abgebrochen."
            }, modifier = Modifier.testTag("speedtest-cancel")) { Text("Abbrechen") }
            OutlinedButton(onClick = { stop(); onBack() },
                modifier = Modifier.testTag("speedtest-back")) { Text("Zurück") }
        }
        if (playlistId == null) Text("Zuerst eine Playlist auswählen.",
            color = Color(0xFFFFB4A9))
        Text("Ein Speedtest nutzt mobile Daten bzw. WLAN-Bandbreite und ist nicht " +
            "identisch mit der Geschwindigkeit eines IPTV-Servers. Kein automatischer Wechsel auf DIREKT.",
            color = Color.White.copy(.58f), fontSize = 12.sp)
    }
}
