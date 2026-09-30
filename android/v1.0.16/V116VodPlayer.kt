package de.epimediahub.app.ui

import android.view.ViewGroup
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.C
import androidx.media3.common.Metadata
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.ui.PlayerView
import de.epimediahub.app.data.*
import de.epimediahub.app.model.MediaEntry
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

internal object V116Playback {
    fun skip(player: Player, segment: V115Segment): Boolean {
        val duration = player.duration
        if (!player.isCurrentMediaItemSeekable || !V115SkipPolicy.valid(segment, duration)) return false
        player.seekTo(segment.endMs)
        // A skip action resumes even when the user paused to select the button.
        // Ordinary seek operations deliberately retain the current pause state.
        player.play()
        return true
    }
}

@androidx.annotation.OptIn(UnstableApi::class)
@Composable
internal fun V116VodPlayer(player: Player, item: MediaEntry, episodes: List<MediaEntry>, isTv: Boolean, error: String,
    onBack: () -> Unit, onEpisode: (MediaEntry) -> Unit, onAudioLanguage: (String) -> Unit, onSubtitleLanguage: (String) -> Unit) {
    val context = LocalContext.current
    val repository = remember(context.applicationContext) { V116SkipRepository(context) }
    val scope = rememberCoroutineScope()
    fun snapshot() = V115PlaybackUiState(
        positionMs = player.currentPosition.coerceAtLeast(0), durationMs = player.duration.takeIf { it > 0 } ?: 0,
        playWhenReady = player.playWhenReady, playing = player.isPlaying, ended = player.playbackState == Player.STATE_ENDED,
        buffering = player.playbackState == Player.STATE_BUFFERING, tracks = player.currentTracks,
        subtitlesDisabled = player.trackSelectionParameters.disabledTrackTypes.contains(C.TRACK_TYPE_TEXT)
    )
    var state by remember(player, item.resumeKey) { mutableStateOf(snapshot()) }
    var automatic by remember(item.resumeKey) { mutableStateOf<List<V115Segment>>(emptyList()) }
    var metadataChapters by remember(item.resumeKey) { mutableStateOf<List<V115Segment>>(emptyList()) }
    var disabled by remember(item.resumeKey) { mutableStateOf<Set<V115SegmentKind>>(emptySet()) }
    var revision by remember(item.resumeKey) { mutableIntStateOf(0) }
    var refresh by remember(item.resumeKey) { mutableIntStateOf(0) }
    var status by remember(item.resumeKey) { mutableStateOf("Zeitmarken werden geprüft …") }
    val drafts = remember(item.resumeKey) { mutableStateMapOf<V115SegmentKind, V116Draft>() }
    var resolving by remember(item.resumeKey) { mutableStateOf(false) }
    var loadingChoices by remember(item.resumeKey) { mutableStateOf(false) }
    var choices by remember(item.resumeKey) { mutableStateOf<List<V116TitleChoice>>(emptyList()) }
    val chapters = remember(state.tracks, state.durationMs, metadataChapters) { V116Chapters.read(state.tracks, state.durationMs) + metadataChapters }
    val segments = remember(item.resumeKey, state.durationMs, automatic, chapters, disabled, revision) { repository.merge(item, state.durationMs, automatic + chapters, disabled) }

    DisposableEffect(player, item.resumeKey) {
        val listener = object : Player.Listener {
            override fun onEvents(player: Player, events: Player.Events) { state = snapshot() }
            override fun onMetadata(metadata: Metadata) { metadataChapters = V116Chapters.read(metadata, player.duration) }
        }
        player.addListener(listener)
        onDispose { player.removeListener(listener) }
    }
    LaunchedEffect(player, item.resumeKey) { while (true) { state = snapshot(); delay(250L) } }
    LaunchedEffect(item.resumeKey) { while (true) { repository.presence(item); delay(25_000L) } }
    LaunchedEffect(item.resumeKey, state.durationMs / 1000, refresh) {
        automatic = emptyList(); disabled = emptySet()
        if (state.durationMs > 0) {
            val duration = state.durationMs
            val synchronized = repository.sync(item, duration)
            if (synchronized.isNotBlank()) status = synchronized
            repeat(2) { attempt ->
                val loaded = repository.load(item, duration)
                automatic = loaded.segments; disabled = loaded.disabled
                if (synchronized.isBlank()) status = loaded.status
                if (loaded.segments.isNotEmpty()) return@LaunchedEffect
                if (attempt == 0) delay(15_000L)
            }
        }
    }
    fun seekTo(position: Long) {
        if (!player.isCurrentMediaItemSeekable || player.duration <= 0) return
        player.seekTo(position.coerceIn(0, player.duration)); state = snapshot()
    }
    V115PlayerChrome(item, episodes, state, segments, isTv, error, onBack,
        onPlayPause = {
            if (player.playWhenReady && player.playbackState != Player.STATE_ENDED) player.pause()
            else { if (player.playbackState == Player.STATE_ENDED) player.seekTo(0); player.play() }
            state = snapshot()
        }, onSeekBy = { seekTo(player.currentPosition + it) }, onSeekTo = ::seekTo,
        onEpisode = onEpisode,
        onTrack = { choice ->
            V115Tracks.select(player, choice)
            if (choice.language.isNotBlank()) { if (choice.type == C.TRACK_TYPE_AUDIO) onAudioLanguage(choice.language) else onSubtitleLanguage(choice.language) }
            state = snapshot()
        }, onSubtitlesOff = { V115Tracks.subtitlesOff(player); onSubtitleLanguage("none"); state = snapshot() },
        onSkipSegment = { segment -> V116Playback.skip(player, segment); state = snapshot() },
        skipTools = { close ->
            if (resolving) V116IdentityDialog(choices, loadingChoices, isTv,
                onChoose = { choice -> repository.setIdentity(item, choice); resolving = false; status = "Zuordnung gespeichert · Zeitmarken werden neu geprüft"; refresh++ },
                onDismiss = { resolving = false })
            else V116SkipEditor(state.durationMs, { player.currentPosition }, segments, drafts, status, isTv, ::seekTo,
                onSave = { kind, start, end, off ->
                    if (repository.save(item, state.durationMs, kind, start, end, off)) {
                        revision++; status = "Auf diesem Gerät gespeichert"
                        scope.launch { status = repository.sync(item, state.durationMs) }
                    }
                }, onReset = { kind -> repository.reset(item, state.durationMs, kind); revision++; status = "Automatische Zeiten werden wieder verwendet" },
                onResolve = { resolving = true; loadingChoices = true; scope.launch { choices = repository.candidates(item); loadingChoices = false } },
                onDismiss = close)
        }
    ) { modifier ->
        AndroidView(factory = { ctx -> PlayerView(ctx).apply {
            this.player = player; useController = false; controllerAutoShow = false
            isFocusable = false; isFocusableInTouchMode = false; descendantFocusability = ViewGroup.FOCUS_BLOCK_DESCENDANTS; hideController()
        } }, update = { it.player = player }, modifier = modifier, onRelease = { it.player = null })
    }
}
