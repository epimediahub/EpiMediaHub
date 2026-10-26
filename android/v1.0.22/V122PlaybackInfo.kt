@file:OptIn(androidx.media3.common.util.UnstableApi::class, androidx.compose.ui.ExperimentalComposeUiApi::class)

package de.epimediahub.app.ui

import android.os.Build
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.delay
import java.lang.ref.WeakReference
import java.util.Locale

internal data class V122PlaybackSnapshot(
    val metadataFps: Float = 0f, val measuredFps: Float = 0f, val contentFps: Float = 0f,
    val speed: Float = 1f, val outputHz: Float = 0f, val outputWidth: Int = 0, val outputHeight: Int = 0,
    val videoWidth: Int = 0, val videoHeight: Int = 0, val codec: String = "",
    val decoder: String = "", val dropped: Int = 0, val rendered: Int = 0,
    val bufferMs: Long = 0L, val state: String = "Wird ermittelt", val automatic: Boolean = false,
    val request: String = "Wird ermittelt"
)

/** Main-thread only. Never retain an Activity, a player or its Surface after leaving playback. */
internal object V122ActiveVideo {
    private var active = WeakReference<V121VideoView>(null)
    fun bind(view: V121VideoView) { active = WeakReference(view) }
    fun clear(view: V121VideoView) { if (active.get() === view) active.clear() }
    fun snapshot(): V122PlaybackSnapshot? = active.get()?.playbackSnapshot()
}

internal fun v122Number(value: Float): String = String.format(Locale.ROOT, "%.3f", value)
private fun fps(value: Float) = if (V121FrameRatePolicy.valid(value)) "${v122Number(value)} fps" else "Nicht gemeldet"

@Composable
internal fun V122PlaybackInfoDialog(isTv: Boolean, onDismiss: () -> Unit,
    compatibility: Boolean = false, onSwitchPlayer: (() -> Unit)? = null) {
    val host = LocalView.current
    fun read(): V122PlaybackSnapshot {
        if (!compatibility) V122ActiveVideo.snapshot()?.let { return it }
        val mode = host.display?.mode
        return V122PlaybackSnapshot(outputHz = mode?.refreshRate ?: 0f,
            outputWidth = mode?.physicalWidth ?: 0, outputHeight = mode?.physicalHeight ?: 0,
            state = if (compatibility) "Kompatibilitätsplayer aktiv" else "Noch keine Videodaten",
            request = if (compatibility) "Vom Kompatibilitätsplayer gesteuert" else "Wird ermittelt")
    }
    var data by remember(compatibility) { mutableStateOf(read()) }
    LaunchedEffect(compatibility, host) {
        while (true) { data = read(); delay(1_000L) }
    }
    V122PlaybackInfoContent(data, isTv, compatibility, onDismiss, onSwitchPlayer)
}

@Composable
internal fun V122PlaybackInfoContent(data: V122PlaybackSnapshot, isTv: Boolean,
    compatibility: Boolean, onDismiss: () -> Unit, onSwitchPlayer: (() -> Unit)? = null) {
    val close = remember { FocusRequester() }
    // A dialog can be the first focusable TV content (e.g. Live TV after a touch launch).
    // Put the host into remote/keyboard mode as well as the dialog's own window.
    val hostInputMode = LocalInputModeManager.current
    LaunchedEffect(isTv) { if (isTv) hostInputMode.requestInputMode(InputMode.Keyboard) }
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        val inputMode = LocalInputModeManager.current
        val maxHeight = LocalConfiguration.current.screenHeightDp.dp * .92f
        Surface(Modifier.fillMaxWidth(if (isTv) .88f else .96f).widthIn(max = 920.dp).heightIn(max = maxHeight)
            .testTag("playback-info"), color = Color(0xFF101923), shape = RoundedCornerShape(14.dp),
            border = BorderStroke(1.dp, Color(0xFF397792))) {
            Column(Modifier.padding(if (isTv) 20.dp else 14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Wiedergabe-Info", color = Color.White, fontSize = if (isTv) 24.sp else 20.sp, fontWeight = FontWeight.Bold)
                Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    @Composable fun Info(label: String, value: String) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Text(label, Modifier.weight(.34f), color = Color(0xFFA4B7C8), fontSize = if (isTv) 15.sp else 13.sp)
                            Text(value, Modifier.weight(.66f), color = Color.White, fontSize = if (isTv) 15.sp else 13.sp)
                        }
                    }
                    Info("Player", if (compatibility) "VLC · Audio-Kompatibilität" else "Media3 · Standardplayer")
                    Info("TV-Ausgabe (System)", if (data.outputHz > 0f)
                        "${data.outputWidth} × ${data.outputHeight} · ${v122Number(data.outputHz)} Hz" else "Nicht verfügbar")
                    if (!compatibility) {
                        Info("Video", "${data.videoWidth} × ${data.videoHeight} · ${data.codec.ifBlank { "Wird ermittelt" }}")
                        Info("Bildrate im Stream", fps(data.metadataFps))
                        Info("Aus Bildzeitstempeln", if (data.measuredFps > 0f) fps(data.measuredFps) else "Noch keine stabile Messung")
                        val target = data.contentFps * data.speed
                        val cadence = when {
                            !V121FrameRatePolicy.valid(target) || data.outputHz <= 0f -> "Noch nicht bestimmbar"
                            V121FrameRatePolicy.cadenceError(data.outputHz, target) <= .012f -> "Gleichmäßiger Bildtakt möglich"
                            else -> "Bildrate und TV-Ausgabe passen nicht zusammen"
                        }
                        Info("Bildtakt", cadence)
                        Info("Anpassung", data.request)
                        Info("Decoder", data.decoder.ifBlank { "Wird ermittelt" })
                        Info("Bilder seit Decoderstart", "${data.rendered} ausgegeben · ${data.dropped} ausgelassen")
                        Info("Puffer / Wiedergabe", "${String.format(Locale.ROOT, "%.1f", data.bufferMs / 1000.0)} s · ${data.state}")
                        if (data.speed != 1f) Info("Tempo", "${v122Number(data.speed)}×")
                    } else {
                        Text("Bildzeitstempel und Decoderzähler sind im Standardplayer verfügbar.", color = Color.LightGray, fontSize = 14.sp)
                    }
                    Info("Gerät / App", "${Build.MANUFACTURER} ${Build.MODEL} · Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT}) · 1.0.22")
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    TextButton(onClick = onDismiss, modifier = Modifier.focusRequester(close).v114FocusRing().testTag("playback-info-close")) {
                        Text("Schließen", color = Color.White, fontSize = 16.sp)
                    }
                    if (onSwitchPlayer != null) TextButton(onClick = { onDismiss(); onSwitchPlayer() },
                        modifier = Modifier.v114FocusRing().testTag("playback-info-switch")) {
                        Text(if (compatibility) "Zum Standardplayer" else "Audio-Kompatibilität", color = Color(0xFF81D6F8), fontSize = 16.sp)
                    }
                }
            }
        }
        LaunchedEffect(Unit) {
            if (isTv) { inputMode.requestInputMode(InputMode.Keyboard); delay(100L); close.requestFocus() }
        }
    }
}
