@file:OptIn(androidx.compose.ui.ExperimentalComposeUiApi::class)

package de.epimediahub.app.ui

import android.view.KeyEvent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.media3.common.C
import androidx.media3.common.Tracks
import de.epimediahub.app.data.V115Segment
import de.epimediahub.app.data.V115SegmentKind
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import kotlinx.coroutines.delay

internal data class V115PlaybackUiState(
    val positionMs: Long = 0, val durationMs: Long = 0, val playWhenReady: Boolean = true,
    val playing: Boolean = false, val ended: Boolean = false, val buffering: Boolean = false,
    val tracks: Tracks = Tracks.EMPTY, val subtitlesDisabled: Boolean = false
)

internal fun v115OrderedEpisodes(item: MediaEntry, episodes: List<MediaEntry>): List<MediaEntry> = episodes
    .filter { it.kind == MediaKind.EPISODE && (item.seriesId.isBlank() || it.seriesId == item.seriesId) &&
        (item.sourceProfileId.isBlank() || it.sourceProfileId == item.sourceProfileId) }
    .distinctBy { it.resumeKey }.sortedWith(compareBy<MediaEntry> { it.season }.thenBy { it.episode }.thenBy { it.name })

@Composable
internal fun V115PlayerChrome(
    item: MediaEntry, episodes: List<MediaEntry>, state: V115PlaybackUiState,
    segments: List<V115Segment>, isTv: Boolean, error: String,
    onBack: () -> Unit, onPlayPause: () -> Unit, onSeekBy: (Long) -> Unit, onSeekTo: (Long) -> Unit,
    onEpisode: (MediaEntry) -> Unit, onTrack: (V115TrackChoice) -> Unit, onSubtitlesOff: () -> Unit,
    video: @Composable (Modifier) -> Unit
) {
    val inputMode = LocalInputModeManager.current
    val rootFocus = remember(item.resumeKey) { FocusRequester() }
    val playFocus = remember(item.resumeKey) { FocusRequester() }
    val audioFocus = remember(item.resumeKey) { FocusRequester() }
    val episodesFocus = remember(item.resumeKey) { FocusRequester() }
    val nextFocus = remember(item.resumeKey) { FocusRequester() }
    var controls by remember(item.resumeKey) { mutableStateOf(true) }
    var dialog by remember(item.resumeKey) { mutableStateOf<String?>(null) }
    var rootFocused by remember { mutableStateOf(false) }
    var consumeCenterUp by remember { mutableStateOf(false) }
    var interaction by remember(item.resumeKey) { mutableIntStateOf(0) }
    var restore by remember(item.resumeKey) { mutableStateOf("play") }
    var cancelledNext by remember(item.resumeKey) { mutableStateOf(false) }
    var countdown by remember(item.resumeKey) { mutableIntStateOf(10) }
    var advanced by remember(item.resumeKey) { mutableStateOf(false) }
    var dragPosition by remember(item.resumeKey) { mutableStateOf<Long?>(null) }
    var selectedSeason by remember(item.resumeKey) { mutableIntStateOf(item.season) }
    val episodeStates = remember(item.resumeKey) { mutableMapOf<Int, LazyListState>() }
    val ordered = remember(item.resumeKey, episodes) { v115OrderedEpisodes(item, episodes) }
    val currentIndex = ordered.indexOfFirst { it.resumeKey == item.resumeKey }
    val next = ordered.getOrNull(currentIndex + 1).takeIf { currentIndex >= 0 }
    val previous = ordered.getOrNull(currentIndex - 1)
    val episodeCallback by rememberUpdatedState(onEpisode)
    val active = segments.filter { it.active(state.positionMs) }
    val red = Color(0xFFE50914)

    fun touch() { controls = true; interaction++ }
    fun show() { restore = "play"; touch() }
    fun closeDialog() { dialog = null; touch() }

    LaunchedEffect(controls, state.playing, state.ended, interaction, dialog) {
        if (controls && state.playing && !state.ended && dialog == null) {
            delay(5_000L)
            controls = false
        }
    }
    LaunchedEffect(controls, dialog, restore, isTv) {
        if (isTv && dialog == null) {
            val target = if (!controls) rootFocus else when (restore) {
                "audio" -> audioFocus; "episodes" -> episodesFocus; "next" -> nextFocus; else -> playFocus
            }
            inputMode.requestInputMode(InputMode.Keyboard)
            delay(110L) // Wait for AndroidView/dialog layout and focus nodes to attach.
            runCatching { target.requestFocus() }
        }
    }
    LaunchedEffect(state.ended, next?.resumeKey, cancelledNext) {
        if (state.ended) { restore = if (next != null) "next" else "play"; controls = true }
        if (!state.ended || next == null || cancelledNext || advanced) return@LaunchedEffect
        // A countdown starts only after Media3 reports a fully ended episode.
        // An estimated credit offset cannot interrupt the episode's story.
        countdown = 10
        while (countdown > 0) { delay(1_000L); countdown-- }
        advanced = true
        episodeCallback(next)
    }
    BackHandler {
        when {
            dialog != null -> closeDialog()
            state.ended && next != null && !cancelledNext -> { cancelledNext = true; touch() }
            controls -> controls = false
            else -> onBack()
        }
    }

    Box(
        Modifier.fillMaxSize().background(Color.Black).testTag("vod-player")
            .focusRequester(rootFocus).onFocusChanged { rootFocused = it.isFocused }
            .onPreviewKeyEvent { event ->
                val native = event.nativeKeyEvent
                val code = native.keyCode
                val center = code == KeyEvent.KEYCODE_DPAD_CENTER || code == KeyEvent.KEYCODE_ENTER
                val mediaKey = code in listOf(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, KeyEvent.KEYCODE_MEDIA_PAUSE, KeyEvent.KEYCODE_MEDIA_PLAY, KeyEvent.KEYCODE_SPACE)
                if (native.action == KeyEvent.ACTION_UP) {
                    if (center && consumeCenterUp) { consumeCenterUp = false; true } else mediaKey
                } else if (native.action != KeyEvent.ACTION_DOWN || dialog != null) false
                else {
                    interaction++
                    when {
                        mediaKey -> {
                            if (native.repeatCount == 0 && (code !in listOf(KeyEvent.KEYCODE_MEDIA_PAUSE, KeyEvent.KEYCODE_MEDIA_PLAY) ||
                                (code == KeyEvent.KEYCODE_MEDIA_PAUSE && state.playWhenReady) || (code == KeyEvent.KEYCODE_MEDIA_PLAY && !state.playWhenReady))) onPlayPause()
                            show(); true
                        }
                        !isTv -> false
                        center && (!controls || rootFocused) -> {
                            if (native.repeatCount == 0) { if (!controls) onPlayPause(); show() }
                            consumeCenterUp = true; true
                        }
                        code == KeyEvent.KEYCODE_MEDIA_NEXT || code == KeyEvent.KEYCODE_PAGE_UP || code == KeyEvent.KEYCODE_CHANNEL_UP -> {
                            if (native.repeatCount == 0) next?.let(onEpisode); true
                        }
                        code == KeyEvent.KEYCODE_MEDIA_PREVIOUS || code == KeyEvent.KEYCODE_PAGE_DOWN || code == KeyEvent.KEYCODE_CHANNEL_DOWN -> {
                            if (native.repeatCount == 0) previous?.let(onEpisode); true
                        }
                        code == KeyEvent.KEYCODE_MEDIA_REWIND -> { onSeekBy(-10_000L); show(); true }
                        code == KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> { onSeekBy(10_000L); show(); true }
                        code == KeyEvent.KEYCODE_MENU -> { restore = "audio"; touch(); dialog = "audio"; true }
                        code in listOf(KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN) && (!controls || rootFocused) -> { show(); true }
                        code == KeyEvent.KEYCODE_DPAD_LEFT && !controls -> { onSeekBy(-10_000L); show(); true }
                        code == KeyEvent.KEYCODE_DPAD_RIGHT && !controls -> { onSeekBy(10_000L); show(); true }
                        else -> false // Focused buttons receive OK and all navigation keys.
                    }
                }
            }.focusable(isTv)
    ) {
        video(Modifier.fillMaxSize())
        if (!isTv) Box(Modifier.fillMaxSize().clickable { controls = !controls; interaction++ }.testTag("vod-touch-surface"))
        if (state.buffering && !state.ended) CircularProgressIndicator(Modifier.align(Alignment.Center).size(44.dp), color = Color.White)
        if (controls) {
            Row(
                Modifier.align(Alignment.TopCenter).fillMaxWidth()
                    .background(Brush.verticalGradient(listOf(Color.Black.copy(alpha = .88f), Color.Transparent)))
                    .padding(horizontal = if (isTv) 30.dp else 16.dp, vertical = if (isTv) 24.dp else 16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(onClick = onBack, modifier = Modifier.size(52.dp).v114FocusRing().testTag("vod-back")) {
                    Icon(Icons.Default.ArrowBack, "Zurück", tint = Color.White, modifier = Modifier.size(28.dp))
                }
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) {
                    Text(if (item.kind == MediaKind.EPISODE) item.categoryId.ifBlank { "Serie" } else item.name,
                        color = Color.White, fontSize = if (isTv) 30.sp else 23.sp, fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    if (item.kind == MediaKind.EPISODE) Text("Staffel ${item.season} · Folge ${item.episode} · ${item.name}",
                        color = Color.White.copy(alpha = .85f), fontSize = if (isTv) 18.sp else 15.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
                if (!state.playWhenReady && !state.ended) Text("PAUSE", color = Color.White, fontSize = if (isTv) 18.sp else 14.sp, fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(start = 12.dp).testTag("vod-paused"))
            }
        }
        Column(
            Modifier.align(Alignment.BottomCenter).fillMaxWidth()
                .then(if (controls || state.ended) Modifier.background(Brush.verticalGradient(listOf(Color.Transparent, Color.Black.copy(alpha = .95f)))) else Modifier)
                .padding(horizontal = if (isTv) 34.dp else 16.dp, vertical = if (isTv) 24.dp else 14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            if (active.isNotEmpty() && !state.ended) Row(Modifier.align(Alignment.End).horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                active.forEach { segment ->
                    Button(onClick = { onSeekTo(segment.endMs); touch() },
                        modifier = Modifier.heightIn(min = if (isTv) 56.dp else 48.dp).v114FocusRing().testTag("vod-skip-${segment.kind.name.lowercase()}"),
                        colors = ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = Color.Black), shape = RoundedCornerShape(6.dp)) {
                        Text(segment.kind.label, fontSize = if (isTv) 19.sp else 16.sp, fontWeight = FontWeight.Bold)
                    }
                }
                if (!controls && next != null && active.any { it.kind == V115SegmentKind.OUTRO }) {
                    Button(onClick = { onEpisode(next) }, modifier = Modifier.heightIn(min = 56.dp).v114FocusRing().testTag("vod-outro-next"),
                        colors = ButtonDefaults.buttonColors(containerColor = red), shape = RoundedCornerShape(6.dp)) { Text("Nächste Folge", fontSize = 19.sp) }
                }
            }
            if (state.ended && next != null) Surface(color = Color(0xEE161616), shape = RoundedCornerShape(8.dp), modifier = Modifier.fillMaxWidth().testTag("vod-next-card")) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(if (cancelledNext) "Als Nächstes" else "Nächste Folge in $countdown Sekunden", color = Color.White, fontSize = if (isTv) 22.sp else 17.sp, fontWeight = FontWeight.Bold)
                        Text("Staffel ${next.season} · Folge ${next.episode} · ${next.name}", color = Color.LightGray, fontSize = if (isTv) 17.sp else 14.sp, maxLines = 2)
                    }
                    if (!cancelledNext) TextButton(onClick = { cancelledNext = true; touch() }, modifier = Modifier.v114FocusRing().testTag("vod-cancel-next")) { Text("Abbrechen", color = Color.White, fontSize = if (isTv) 18.sp else 15.sp) }
                }
            }
            if (controls) {
                val duration = state.durationMs.coerceAtLeast(0L)
                val position = (dragPosition ?: state.positionMs).coerceIn(0, duration.takeIf { it > 0 } ?: Long.MAX_VALUE)
                Slider(value = position.toFloat(), valueRange = 0f..duration.coerceAtLeast(1L).toFloat(), enabled = duration > 0,
                    onValueChange = { dragPosition = it.toLong(); touch() },
                    onValueChangeFinished = { dragPosition?.let(onSeekTo); dragPosition = null; touch() },
                    colors = SliderDefaults.colors(thumbColor = red, activeTrackColor = red, inactiveTrackColor = Color.White.copy(alpha = .35f)),
                    modifier = Modifier.fillMaxWidth().height(42.dp).v114FocusRing().testTag("vod-timeline")
                        .onPreviewKeyEvent {
                            if (it.nativeKeyEvent.action == KeyEvent.ACTION_DOWN && it.nativeKeyEvent.keyCode in listOf(KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT)) {
                                onSeekBy(if (it.nativeKeyEvent.keyCode == KeyEvent.KEYCODE_DPAD_LEFT) -10_000 else 10_000); touch(); true
                            } else false
                        })
                Row(Modifier.fillMaxWidth().semantics { stateDescription = "$position/$duration" }.testTag("vod-time")) {
                    Text(V093FormatTime(position), color = Color.White, fontSize = if (isTv) 19.sp else 15.sp)
                    Spacer(Modifier.weight(1f))
                    Text(if (duration > 0) "−${V093FormatTime((duration - position).coerceAtLeast(0))}" else "Laufzeit wird geladen",
                        color = Color.White.copy(alpha = .85f), fontSize = if (isTv) 19.sp else 15.sp)
                }
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).testTag("vod-actions"),
                    horizontalArrangement = Arrangement.spacedBy(if (isTv) 14.dp else 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = { onPlayPause(); touch() }, modifier = Modifier.size(if (isTv) 62.dp else 52.dp).focusRequester(playFocus).v114FocusRing().testTag("vod-play-pause")) {
                        Icon(if (state.playWhenReady && !state.ended) Icons.Default.Pause else Icons.Default.PlayArrow, if (state.playWhenReady && !state.ended) "Pausieren" else "Abspielen", tint = Color.White, modifier = Modifier.size(if (isTv) 40.dp else 32.dp))
                    }
                    IconButton(onClick = { onSeekBy(-10_000); touch() }, modifier = Modifier.size(54.dp).v114FocusRing().testTag("vod-rewind")) { Icon(Icons.Default.Replay10, "10 Sekunden zurück", tint = Color.White, modifier = Modifier.size(32.dp)) }
                    IconButton(onClick = { onSeekBy(10_000); touch() }, modifier = Modifier.size(54.dp).v114FocusRing().testTag("vod-forward")) { Icon(Icons.Default.Forward10, "10 Sekunden vor", tint = Color.White, modifier = Modifier.size(32.dp)) }
                    TextButton(onClick = { restore = "audio"; dialog = "audio"; touch() },
                        modifier = Modifier.heightIn(min = 54.dp).focusRequester(audioFocus).v114FocusRing().testTag("vod-audio")) {
                        Icon(Icons.Default.Subtitles, null, tint = Color.White); Spacer(Modifier.width(8.dp))
                        Text("Audio & Untertitel", color = Color.White, fontSize = if (isTv) 18.sp else 15.sp)
                    }
                    if (ordered.isNotEmpty()) TextButton(onClick = { restore = "episodes"; dialog = "episodes"; touch() },
                        modifier = Modifier.heightIn(min = 54.dp).focusRequester(episodesFocus).v114FocusRing().testTag("vod-episodes")) {
                        Icon(Icons.Default.VideoLibrary, null, tint = Color.White); Spacer(Modifier.width(8.dp)); Text("Folgen", color = Color.White, fontSize = if (isTv) 18.sp else 15.sp)
                    }
                    if (next != null) Button(onClick = { cancelledNext = true; onEpisode(next) },
                        modifier = Modifier.heightIn(min = 54.dp).focusRequester(nextFocus).v114FocusRing().testTag("vod-next"),
                        shape = RoundedCornerShape(6.dp), colors = ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = Color.Black)) {
                        Icon(Icons.Default.SkipNext, null); Spacer(Modifier.width(6.dp)); Text("Nächste Folge", fontWeight = FontWeight.Bold, fontSize = if (isTv) 18.sp else 15.sp)
                    }
                }
            }
            if (error.isNotBlank()) Text(error, color = Color.White, fontSize = if (isTv) 18.sp else 15.sp,
                modifier = Modifier.fillMaxWidth().background(Color(0xE52C1010), RoundedCornerShape(8.dp)).padding(14.dp))
        }
        if (dialog == "audio") V115TrackDialog(state, isTv, ::closeDialog,
            onTrack = { onTrack(it); closeDialog() }, onOff = { onSubtitlesOff(); closeDialog() })
        if (dialog == "episodes") {
            val seasonEpisodes = ordered.filter { it.season == selectedSeason }
            val listState = episodeStates.getOrPut(selectedSeason) {
                LazyListState(seasonEpisodes.indexOfFirst { it.resumeKey == item.resumeKey }.coerceAtLeast(0), 0)
            }
            V115EpisodeDialog(item, ordered, selectedSeason, listState, isTv, ::closeDialog,
                onSeason = { selectedSeason = it }, onEpisode = { cancelledNext = true; dialog = null; onEpisode(it) })
        }
    }
}
