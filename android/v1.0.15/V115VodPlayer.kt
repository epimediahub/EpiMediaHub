package de.epimediahub.app.ui

import android.view.ViewGroup
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.C
import androidx.media3.common.Player
import androidx.media3.common.TrackSelectionParameters
import androidx.media3.common.util.UnstableApi
import androidx.media3.ui.PlayerView
import de.epimediahub.app.data.V115Segment
import de.epimediahub.app.data.V115SkipRepository
import de.epimediahub.app.model.MediaEntry
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull

@androidx.annotation.OptIn(UnstableApi::class)
@Composable
internal fun V115VodPlayer(player: Player, item: MediaEntry, episodes: List<MediaEntry>, isTv: Boolean, error: String,
    onBack: () -> Unit, onEpisode: (MediaEntry) -> Unit, onAudioLanguage: (String) -> Unit, onSubtitleLanguage: (String) -> Unit) {
    val context = LocalContext.current
    val repository = remember(context.applicationContext) { V115SkipRepository(context) }
    fun snapshot() = V115PlaybackUiState(
        positionMs = player.currentPosition.coerceAtLeast(0), durationMs = player.duration.takeIf { it > 0 } ?: 0,
        playWhenReady = player.playWhenReady, playing = player.isPlaying, ended = player.playbackState == Player.STATE_ENDED,
        buffering = player.playbackState == Player.STATE_BUFFERING, tracks = player.currentTracks,
        subtitlesDisabled = player.trackSelectionParameters.disabledTrackTypes.contains(C.TRACK_TYPE_TEXT)
    )
    var state by remember(player) { mutableStateOf(snapshot()) }
    var segments by remember(item.resumeKey) { mutableStateOf<List<V115Segment>>(emptyList()) }
    DisposableEffect(player) {
        val listener = object : Player.Listener {
            override fun onEvents(player: Player, events: Player.Events) { state = snapshot() }
        }
        player.addListener(listener)
        onDispose { player.removeListener(listener) }
    }
    LaunchedEffect(player) {
        while (true) { state = snapshot(); delay(250L) }
    }
    LaunchedEffect(item.resumeKey, state.durationMs / 1000) {
        segments = emptyList()
        if (state.durationMs > 0) {
            val duration = state.durationMs
            repeat(2) { attempt ->
                val loaded = withTimeoutOrNull(25_000L) { repository.load(item, duration) }.orEmpty()
                if (loaded.isNotEmpty()) { segments = loaded; return@LaunchedEffect }
                if (attempt == 0) delay(15_000L)
            }
        }
    }
    fun seekTo(position: Long) {
        if (!player.isCurrentMediaItemSeekable || player.duration <= 0) return
        player.seekTo(position.coerceIn(0, player.duration))
        state = snapshot()
    }
    V115PlayerChrome(item, episodes, state, segments, isTv, error, onBack,
        onPlayPause = {
            // playWhenReady also handles pausing while buffering; isPlaying does not.
            if (player.playWhenReady && player.playbackState != Player.STATE_ENDED) player.pause()
            else { if (player.playbackState == Player.STATE_ENDED) player.seekTo(0); player.play() }
            state = snapshot()
        },
        onSeekBy = { seekTo(player.currentPosition + it) }, onSeekTo = ::seekTo,
        onEpisode = onEpisode,
        onTrack = { choice ->
            V115Tracks.select(player, choice)
            if (choice.language.isNotBlank()) {
                if (choice.type == C.TRACK_TYPE_AUDIO) onAudioLanguage(choice.language) else onSubtitleLanguage(choice.language)
            }
            state = snapshot()
        },
        onSubtitlesOff = { V115Tracks.subtitlesOff(player); onSubtitleLanguage("none"); state = snapshot() }
    ) { modifier ->
        AndroidView(factory = { ctx ->
            PlayerView(ctx).apply {
                this.player = player
                useController = false
                controllerAutoShow = false
                isFocusable = false
                isFocusableInTouchMode = false
                descendantFocusability = ViewGroup.FOCUS_BLOCK_DESCENDANTS
                hideController()
                // SubtitleView remains active, independent of the disabled native controls.
            }
        }, update = { it.player = player }, modifier = modifier,
            onRelease = { it.player = null })
    }
}
