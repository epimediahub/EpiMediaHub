package de.epimediahub.app.vpn

import android.content.Context
import android.os.SystemClock
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.border
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
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
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
import java.util.Locale

/**
 * Real, finite HTTP throughput test. Cloudflare speed.cloudflare.com/__down and
 * /__up are public speed-test endpoints. No mock readings or credential uploads.
 * Requires the current playlist's route to remain verified throughout the test.
 */
internal object V140SpeedTest {
    data class Result(val route: String, val ip: String, val latencyMs: Long,
        val downloadMbps: Double, val uploadMbps: Double, val bytes: Long)

    private const val HOST = "https://speed.cloudflare.com"
    enum class Phase { IDLE, CHECKING, DOWNLOAD, UPLOAD, DONE }
    data class Live(val phase: Phase, val mbps: Double, val fraction: Float)

    private const val DOWNLOAD_BYTES = 24 * 1024 * 1024
    private const val UPLOAD_BYTES = 4 * 1024 * 1024

    private fun verifyRoute(context: Context, playlistId: String, vpn: Boolean,
                            transfer: V140SpeedTransfer) {
        transfer.checkActive()
        check(V134VpnSession.usesVpn(context, playlistId) == vpn) {
            "Playlist-Routing wurde geändert. Messung abgebrochen."
        }
        check(V134VpnSession.routeReady(context, playlistId, checkExit = false)) {
            "VPN-Verbindung nicht bestätigt. Kein automatischer Direkt-Fallback."
        }
    }

    fun measure(context: Context, playlistId: String, transfer: V140SpeedTransfer,
                progress: (String) -> Unit, live: (Live) -> Unit = {}): Result {
        val vpn = V134VpnSession.usesVpn(context, playlistId)
        live(Live(Phase.CHECKING, 0.0, 0f))
        verifyRoute(context, playlistId, vpn, transfer)
        val verify = { verifyRoute(context, playlistId, vpn, transfer) }
        val before = V134VpnSession.publicIpv4()
        check(if (vpn) before == "37.27.42.215" else before != "37.27.42.215") {
            "IP stimmt nicht mit dem gewählten Routing überein"
        }
        verifyRoute(context, playlistId, vpn, transfer)
        progress("HTTP-Latenz wird gemessen …")
        val latencyStart = SystemClock.elapsedRealtimeNanos()
        transfer.download("$HOST/__down?bytes=32", 32, verify)
        val latencyMs = ((SystemClock.elapsedRealtimeNanos() - latencyStart) / 1_000_000).coerceAtLeast(1L)

        live(Live(Phase.DOWNLOAD, 0.0, 0f))
        progress("Download wird live gemessen …")
        val down = transfer.download("$HOST/__down?bytes=$DOWNLOAD_BYTES", DOWNLOAD_BYTES, verify) { sample ->
            live(Live(Phase.DOWNLOAD, sample.mbps,
                (sample.bytes.toFloat() / DOWNLOAD_BYTES).coerceIn(0f, 1f)))
        }
        live(Live(Phase.UPLOAD, 0.0, 0f))
        progress("Upload wird live gemessen …")
        val up = transfer.upload("$HOST/__up", UPLOAD_BYTES, verify) { sample ->
            live(Live(Phase.UPLOAD, sample.mbps,
                (sample.bytes.toFloat() / UPLOAD_BYTES).coerceIn(0f, 1f)))
        }

        progress("VPN-Ausgang wird nochmals geprüft …")
        verifyRoute(context, playlistId, vpn, transfer)
        val after = V134VpnSession.publicIpv4()
        check(before == after) { "Öffentliche IP hat sich während des Tests geändert" }
        verifyRoute(context, playlistId, vpn, transfer)
        return Result(if (vpn) "VPN FINNLAND" else "DIREKT", after, latencyMs,
            down.mbps, up.mbps, down.bytes + up.bytes)
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
    var transfer by remember { mutableStateOf<V140SpeedTransfer?>(null) }
    val firstFocus = remember { FocusRequester() }
    val lifecycleOwner = LocalLifecycleOwner.current
    var job by remember { mutableStateOf<Job?>(null) }
    var startFocused by remember { mutableStateOf(false) }
    var cancelFocused by remember { mutableStateOf(false) }
    var backFocused by remember { mutableStateOf(false) }
    fun stop() {
        if (!busy) return
        transfer?.cancel()
        job?.cancel()
        // Keep start disabled until the old worker actually exits.
        status = "Messung abgebrochen."
    }
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) stop()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            transfer?.cancel()
            job?.cancel()
        }
    }
    LaunchedEffect(Unit) { if (playlistId != null) firstFocus.requestFocus() }
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
                    val current = V140SpeedTransfer()
                    transfer = current
                    busy = true
                    result = null
                    job = scope.launch {
                        try {
                            val measured = withContext(Dispatchers.IO) {
                                V140SpeedTest.measure(context, playlistId, current) { progress ->
                                    scope.launch {
                                        if (transfer === current && busy && !current.isCancelled()) status = progress
                                    }
                                }
                            }
                            if (!current.isCancelled()) {
                                result = measured
                                status = "Messung erfolgreich abgeschlossen."
                            }
                        } catch (e: CancellationException) {
                            status = "Messung abgebrochen."
                        } catch (e: Exception) {
                            status = if (current.isCancelled()) "Messung abgebrochen."
                                else "Fehler: ${e.message ?: "Netzwerk nicht verfügbar"}"
                        } finally { if (transfer === current) busy = false }
                    }
                }, enabled = !busy && playlistId != null, modifier = Modifier.focusRequester(firstFocus).testTag("speedtest-start")
                    .onFocusChanged { startFocused = it.hasFocus }
                    .border(BorderStroke(if (startFocused) 4.dp else 1.dp,
                        if (startFocused) Color.White else Color.Gray), RoundedCornerShape(12.dp))
            ) { Text(if (busy) "Messung läuft …" else "Speedtest starten") }
            if (busy) OutlinedButton(onClick = {
                stop()
                status = "Messung abgebrochen."
            }, modifier = Modifier.testTag("speedtest-cancel")
                .onFocusChanged { cancelFocused = it.hasFocus }
                .border(BorderStroke(if (cancelFocused) 4.dp else 1.dp,
                    if (cancelFocused) Color.White else Color.Gray), RoundedCornerShape(12.dp))) { Text("Abbrechen") }
            OutlinedButton(onClick = { stop(); onBack() },
                modifier = Modifier.testTag("speedtest-back")
                    .onFocusChanged { backFocused = it.hasFocus }
                    .border(BorderStroke(if (backFocused) 4.dp else 1.dp,
                        if (backFocused) Color.White else Color.Gray), RoundedCornerShape(12.dp))) { Text("Zurück") }
        }
        if (playlistId == null) Text("Zuerst eine Playlist auswählen.",
            color = Color(0xFFFFB4A9))
        Text("Ein Speedtest nutzt mobile Daten bzw. WLAN-Bandbreite und ist nicht " +
            "identisch mit der Geschwindigkeit eines IPTV-Servers. Kein automatischer Wechsel auf DIREKT.",
            color = Color.White.copy(.58f), fontSize = 12.sp)
    }
}
