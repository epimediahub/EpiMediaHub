package de.epimediahub.app.vpn

import android.content.Context
import android.os.SystemClock
import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.border
import androidx.compose.foundation.background
import androidx.compose.foundation.clip
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
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
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.min

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

/**
 * Full-screen TV-friendly instrument cluster, fed solely by actual byte counts.
 * The animated needle never invents measurements and never opens a network route.
 */
@Composable
private fun V143SpeedGauge(speedMbps: Double, stage: V140SpeedTest.Phase,
                           tint: Color, isTv: Boolean) {
    val safeSpeed = speedMbps.coerceIn(0.0, 10_000.0).toFloat()
    val animated by animateFloatAsState(
        targetValue = safeSpeed, animationSpec = tween(durationMillis = 230),
        label = "genuine-network-throughput"
    )
    val ceiling = when {
        animated <= 100f -> 100f
        animated <= 250f -> 250f
        animated <= 500f -> 500f
        animated <= 1000f -> 1000f
        else -> 2500f
    }
    val fraction = (animated / ceiling).coerceIn(0f, 1f)
    val dialHeight = if (isTv) 186.dp else 156.dp
    Column(horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.fillMaxWidth().testTag("speedtest-live-gauge")) {
        Box(Modifier.fillMaxWidth().height(dialHeight)) {
            Canvas(Modifier.fillMaxSize()) {
                val radius = min(size.width * .41f, size.height * .65f)
                val center = Offset(size.width * .5f, size.height * .67f)
                val topLeft = Offset(center.x - radius, center.y - radius)
                val bounds = Size(radius * 2, radius * 2)
                val thickness = if (isTv) 15.dp.toPx() else 12.dp.toPx()
                drawArc(Color(0xFF293951), 150f, 240f, false, topLeft, bounds,
                    style = Stroke(width = thickness, cap = StrokeCap.Round))
                if (fraction > 0f) {
                    drawArc(tint, 150f, 240f * fraction, false, topLeft, bounds,
                        style = Stroke(width = thickness, cap = StrokeCap.Round))
                }
                for (mark in 0..12) {
                    val angle = Math.toRadians((150f + mark * 20f).toDouble())
                    val inner = radius * if (mark % 3 == 0) .75f else .81f
                    val outer = radius * .88f
                    drawLine(
                        color = if (mark * (1f / 12f) <= fraction) tint
                            else Color(0xFF65758A),
                        start = Offset(center.x + cos(angle).toFloat() * inner,
                            center.y + sin(angle).toFloat() * inner),
                        end = Offset(center.x + cos(angle).toFloat() * outer,
                            center.y + sin(angle).toFloat() * outer),
                        strokeWidth = if (mark % 3 == 0) 2.5.dp.toPx() else 1.5.dp.toPx(),
                        cap = StrokeCap.Round
                    )
                }
                val angle = Math.toRadians((150f + 240f * fraction).toDouble())
                val needle = Offset(center.x + cos(angle).toFloat() * radius * .70f,
                    center.y + sin(angle).toFloat() * radius * .70f)
                drawLine(color = Color.White.copy(alpha = .85f), start = center, end = needle,
                    strokeWidth = 3.dp.toPx(), cap = StrokeCap.Round)
                drawCircle(tint, radius = 6.dp.toPx(), center = center)
                drawCircle(Color.White, radius = 2.5.dp.toPx(), center = center)
            }
            Text("0", color = Color(0xFF9EADC3),
                fontSize = 13.sp, modifier = Modifier.align(Alignment.BottomStart)
                    .padding(start = if (isTv) 38.dp else 16.dp))
            Text(String.format(Locale.GERMANY, "%.0f", ceiling),
                color = Color(0xFF9EADC3), fontSize = 13.sp,
                modifier = Modifier.align(Alignment.BottomEnd)
                    .padding(end = if (isTv) 38.dp else 16.dp))
        }
        Text(
            if (stage == V140SpeedTest.Phase.CHECKING) "VERBINDUNG PRÜFEN"
            else if (stage == V140SpeedTest.Phase.DOWNLOAD) "LIVE DOWNLOAD"
            else if (stage == V140SpeedTest.Phase.UPLOAD) "LIVE UPLOAD"
            else if (stage == V140SpeedTest.Phase.DONE) "LETZTE MESSUNG"
            else "BEREIT ZUM TEST",
            color = tint.copy(alpha = .85f), fontWeight = FontWeight.Bold, fontSize = 14.sp
        )
        Row(verticalAlignment = Alignment.Bottom,
            horizontalArrangement = Arrangement.Center,
            modifier = Modifier.testTag("speedtest-live-mbps")) {
            Text(String.format(Locale.GERMANY, "%.1f", animated),
                color = Color.White, fontSize = if (isTv) 56.sp else 43.sp,
                fontWeight = FontWeight.Black)
            Text("Mbit/s", color = Color(0xFFB7CAE1), fontSize = 18.sp,
                modifier = Modifier.padding(bottom = 11.dp, start = 9.dp))
        }
    }
}

@Composable
private fun V143SpeedMetric(title: String, speed: Double?, tint: Color, isTv: Boolean) {
    Surface(modifier = Modifier.fillMaxWidth(), color = Color(0xFF172A43),
        shape = RoundedCornerShape(14.dp),
        border = BorderStroke(1.dp, Color.White.copy(alpha = .10f))) {
        Column(Modifier.padding(horizontal = 20.dp, vertical = if (isTv) 14.dp else 11.dp),
            verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(title, color = Color(0xFFC3D2E4), fontSize = 13.sp,
                fontWeight = FontWeight.Bold)
            Row(verticalAlignment = Alignment.Bottom) {
                Text(if (speed == null) "—" else
                    String.format(Locale.GERMANY, "%.1f", speed),
                    color = tint, fontSize = if (isTv) 27.sp else 23.sp,
                    fontWeight = FontWeight.Bold)
                if (speed != null) Text(" Mbit/s", color = Color.White.copy(alpha = .75f),
                    fontSize = 13.sp, modifier = Modifier.padding(bottom = 5.dp))
            }
        }
    }
}

@Composable
internal fun V140SpeedTestScreen(context: Context, playlistId: String?, isTv: Boolean,
                                 accent: Color, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val lifecycleOwner = LocalLifecycleOwner.current
    val firstFocus = remember { FocusRequester() }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("Bereit für den Live-Speedtest.") }
    var result by remember { mutableStateOf<V140SpeedTest.Result?>(null) }
    var phase by remember { mutableStateOf(V140SpeedTest.Phase.IDLE) }
    var speed by remember { mutableStateOf(0.0) }
    var completed by remember { mutableFloatStateOf(0f) }
    var downloadResult by remember { mutableStateOf<Double?>(null) }
    var uploadResult by remember { mutableStateOf<Double?>(null) }
    var transfer by remember { mutableStateOf<V140SpeedTransfer?>(null) }
    var job by remember { mutableStateOf<Job?>(null) }
    var startFocused by remember { mutableStateOf(false) }
    var cancelFocused by remember { mutableStateOf(false) }
    var backFocused by remember { mutableStateOf(false) }
    val routeViaVpn = playlistId != null && V134VpnSession.usesVpn(context, playlistId)
    val liveTint = if (phase == V140SpeedTest.Phase.UPLOAD) Color(0xFFFFC46A)
        else Color(0xFF4EDCFF)
    val failed = status.startsWith("Fehler") || status.contains("abgebrochen")

    fun stop() {
        if (!busy) return
        transfer?.cancel()
        job?.cancel()
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
        Modifier.fillMaxSize()
            .background(Brush.verticalGradient(listOf(Color(0xFF061221), Color(0xFF0C2137),
                Color(0xFF08111E))))
            .verticalScroll(rememberScrollState())
            .padding(horizontal = if (isTv) 48.dp else 18.dp,
                vertical = if (isTv) 20.dp else 14.dp)
            .testTag("speedtest-screen"),
        verticalArrangement = Arrangement.spacedBy(if (isTv) 13.dp else 11.dp)
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            Column {
                Text("E P I M E D I A H U B   /   N E T W O R K",
                    fontSize = 11.sp, color = Color(0xFF83A3C6),
                    fontWeight = FontWeight.Bold)
                Text("SPEEDTEST", fontSize = if (isTv) 30.sp else 24.sp,
                    color = Color.White, fontWeight = FontWeight.Black)
            }
            Surface(shape = RoundedCornerShape(50),
                color = if (routeViaVpn) Color(0xFF153B42) else Color(0xFF243347),
                border = BorderStroke(1.dp, if (routeViaVpn) Color(0xFF39DDBF)
                    else Color(0xFF7895B4))) {
                Text(if (routeViaVpn) "● VPN FINNLAND" else "● DIREKT",
                    modifier = Modifier.padding(horizontal = 15.dp, vertical = 9.dp),
                    color = if (routeViaVpn) Color(0xFF65E8D0) else Color.White,
                    fontSize = 13.sp, fontWeight = FontWeight.Bold)
            }
        }

        Surface(Modifier.fillMaxWidth(), color = Color(0xFF101F34),
            shape = RoundedCornerShape(24.dp),
            border = BorderStroke(1.dp, Color(0xFF304660))) {
            Column(Modifier.padding(if (isTv) 22.dp else 15.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(
                    when (phase) {
                        V140SpeedTest.Phase.CHECKING -> "● Netzwerk und öffentliche IP werden geprüft"
                        V140SpeedTest.Phase.DOWNLOAD -> "↓  DOWNLOAD LÄUFT"
                        V140SpeedTest.Phase.UPLOAD -> "↑  UPLOAD LÄUFT"
                        V140SpeedTest.Phase.DONE -> "✓  TEST ERFOLGREICH ABGESCHLOSSEN"
                        else -> "BEREIT  •  ECHTE DATENÜBERTRAGUNG"
                    },
                    color = liveTint, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                if (isTv) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                        Box(Modifier.weight(1.2f)) {
                            V143SpeedGauge(speed, phase, liveTint, isTv)
                        }
                        Column(Modifier.weight(.85f),
                            verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            V143SpeedMetric("↓  DOWNLOAD",
                                downloadResult ?: if (phase == V140SpeedTest.Phase.DOWNLOAD) speed else null,
                                Color(0xFF4EDCFF), isTv)
                            V143SpeedMetric("↑  UPLOAD",
                                uploadResult ?: if (phase == V140SpeedTest.Phase.UPLOAD) speed else null,
                                Color(0xFFFFC46A), isTv)
                            Text(result?.let { "HTTP-Latenz ${it.latencyMs} ms  •  ${it.bytes / 1_048_576} MiB" }
                                ?: "HTTP-Test • 24 MiB Down / 4 MiB Up",
                                color = Color(0xFFB3C4D9), fontSize = 13.sp)
                        }
                    }
                } else {
                    V143SpeedGauge(speed, phase, liveTint, isTv)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Box(Modifier.weight(1f)) {
                            V143SpeedMetric("↓  DOWNLOAD",
                                downloadResult ?: if (phase == V140SpeedTest.Phase.DOWNLOAD) speed else null,
                                Color(0xFF4EDCFF), isTv)
                        }
                        Box(Modifier.weight(1f)) {
                            V143SpeedMetric("↑  UPLOAD",
                                uploadResult ?: if (phase == V140SpeedTest.Phase.UPLOAD) speed else null,
                                Color(0xFFFFC46A), isTv)
                        }
                    }
                }
                Box(Modifier.fillMaxWidth().height(6.dp)
                    .clip(RoundedCornerShape(4.dp)).background(Color(0xFF30425A))) {
                    Box(Modifier.fillMaxWidth(completed.coerceIn(0f, 1f)).fillMaxHeight()
                        .background(liveTint))
                }
                Text(status, color = if (failed) Color(0xFFFFAFA9) else Color(0xFFDCE7F4),
                    fontSize = if (isTv) 15.sp else 13.sp)
                result?.let {
                    Text("AUSGANG  ${it.route}   •   IP  ${it.ip}",
                        color = Color(0xFF86E8D4), fontWeight = FontWeight.Bold,
                        fontSize = if (isTv) 15.sp else 13.sp)
                }
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(
                onClick = {
                    if (busy || playlistId == null) return@Button
                    val current = V140SpeedTransfer()
                    transfer = current
                    busy = true
                    status = "Verbindung wird geprüft …"
                    result = null
                    downloadResult = null
                    uploadResult = null
                    speed = 0.0
                    completed = 0f
                    phase = V140SpeedTest.Phase.CHECKING
                    job = scope.launch {
                        try {
                            val measured = withContext(Dispatchers.IO) {
                                V140SpeedTest.measure(context, playlistId, current, { message ->
                                    scope.launch {
                                        if (transfer === current && busy && !current.isCancelled())
                                            status = message
                                    }
                                }, { live ->
                                    scope.launch {
                                        if (transfer === current && busy && !current.isCancelled()
                                            && phase != V140SpeedTest.Phase.DONE) {
                                            if (phase == V140SpeedTest.Phase.DOWNLOAD &&
                                                live.phase == V140SpeedTest.Phase.UPLOAD)
                                                downloadResult = speed
                                            phase = live.phase
                                            speed = live.mbps.coerceAtLeast(0.0)
                                            completed = live.fraction
                                        }
                                    }
                                })
                            }
                            if (!current.isCancelled()) {
                                downloadResult = measured.downloadMbps
                                uploadResult = measured.uploadMbps
                                result = measured
                                phase = V140SpeedTest.Phase.DONE
                                completed = 1f
                                speed = measured.downloadMbps
                                status = "Messung erfolgreich abgeschlossen."
                            }
                        } catch (e: CancellationException) {
                            status = "Messung abgebrochen."
                        } catch (e: Exception) {
                            status = if (current.isCancelled()) "Messung abgebrochen."
                                else "Fehler: ${e.message ?: "Netzwerk nicht verfügbar"}"
                        } finally { if (transfer === current) busy = false }
                    }
                },
                enabled = !busy && playlistId != null,
                modifier = Modifier.focusRequester(firstFocus).testTag("speedtest-start")
                    .onFocusChanged { startFocused = it.hasFocus }
                    .border(BorderStroke(if (startFocused) 4.dp else 1.dp,
                        if (startFocused) Color.White else Color.Gray),
                        RoundedCornerShape(12.dp))
            ) { Text(if (busy) "MESSUNG LÄUFT" else "▶  SPEEDTEST STARTEN") }
            if (busy) OutlinedButton(
                onClick = { stop() },
                modifier = Modifier.testTag("speedtest-cancel")
                    .onFocusChanged { cancelFocused = it.hasFocus }
                    .border(BorderStroke(if (cancelFocused) 4.dp else 1.dp,
                        if (cancelFocused) Color.White else Color.Gray), RoundedCornerShape(12.dp))
            ) { Text("Abbrechen") }
            OutlinedButton(
                onClick = { stop(); onBack() },
                modifier = Modifier.testTag("speedtest-back")
                    .onFocusChanged { backFocused = it.hasFocus }
                    .border(BorderStroke(if (backFocused) 4.dp else 1.dp,
                        if (backFocused) Color.White else Color.Gray), RoundedCornerShape(12.dp))
            ) { Text("Zurück") }
        }
        if (playlistId == null)
            Text("Bitte zuerst eine Playlist auswählen.", color = Color(0xFFFFAFA9))
        Text("Live-Messung über Cloudflare · HTTPS-Latenz inklusive TLS, kein ICMP-Ping. " +
            "Ohne bestätigte VPN-Route kein ungeschützter Fallback. " +
            "Speedtest-Werte entsprechen nicht zwingend der Geschwindigkeit eines IPTV-Anbieters.",
            color = Color(0xFF8BA0B9), fontSize = 12.sp)
    }
}
