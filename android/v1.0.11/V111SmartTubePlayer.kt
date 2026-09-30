package de.epimediahub.app.ui

import android.widget.FrameLayout
import androidx.activity.compose.BackHandler
import androidx.annotation.OptIn
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.dash.DashMediaSource
import androidx.media3.exoplayer.hls.HlsMediaSource
import androidx.media3.exoplayer.source.MediaSource
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.PlayerView
import kotlinx.coroutines.delay

@OptIn(UnstableApi::class)
@Composable
internal fun V111SmartTubePlayer(
    video: V100SmartTubeVideo,
    playback: V100SmartTubePlayback,
    accent: Color,
    onBack: () -> Unit,
    onEnded: () -> Unit
) {
    val context = LocalContext.current
    var playbackError by remember(video.videoId, playback.url) { mutableStateOf("") }
    var controlsVisible by remember(video.videoId) { mutableStateOf(true) }
    var isPlaying by remember(video.videoId) { mutableStateOf(false) }
    var positionMs by remember(video.videoId) { mutableLongStateOf(0L) }
    val remoteFocusRequester = remember { FocusRequester() }

    val playerResult = remember(context, video.videoId, playback.url) {
        runCatching {
            val http = DefaultHttpDataSource.Factory()
                .setUserAgent("EpiMediaHub/1.0.11")
                .setAllowCrossProtocolRedirects(true)
            val dataSource = DefaultDataSource.Factory(context, http)
            val loadControl = DefaultLoadControl.Builder()
                .setBufferDurationsMs(5_000, 30_000, 750, 1_250)
                .build()
            val sourceFactory: MediaSource.Factory = when (playback.extension.lowercase()) {
                "mpd" -> DashMediaSource.Factory(dataSource)
                "m3u8" -> HlsMediaSource.Factory(dataSource)
                else -> DefaultMediaSourceFactory(context).setDataSourceFactory(dataSource)
            }
            ExoPlayer.Builder(context)
                .setLoadControl(loadControl)
                .setMediaSourceFactory(sourceFactory)
                .build()
        }
    }
    val player = playerResult.getOrNull()
    val errorText = playbackError.ifBlank {
        playerResult.exceptionOrNull()?.let {
            "SmartTube-Player konnte nicht erstellt werden: " +
                (it.message ?: it.javaClass.simpleName).take(220)
        }.orEmpty()
    }


    fun seekBy(deltaMs: Long) {
        val active = player ?: return
        if (video.live) return
        val max = active.duration.takeIf { it > 0L } ?: Long.MAX_VALUE
        active.seekTo((active.currentPosition + deltaMs).coerceIn(0L, max))
        positionMs = active.currentPosition
        controlsVisible = true
    }

    LaunchedEffect(player, video.videoId) {
        if (player != null) {
            runCatching { remoteFocusRequester.requestFocus() }
        }
    }

    LaunchedEffect(player, video.videoId) {
        while (player != null) {
            positionMs = runCatching { player.currentPosition.coerceAtLeast(0L) }.getOrDefault(0L)
            delay(500L)
        }
    }

    LaunchedEffect(controlsVisible, isPlaying, video.videoId) {
        if (controlsVisible && isPlaying) {
            delay(4_500L)
            controlsVisible = false
        }
    }

    BackHandler {
        runCatching { player?.stop() }
        onBack()
    }

    if (player != null) {
        DisposableEffect(player, video.videoId, playback.url) {
            var endDispatched = false
            val listener = object : Player.Listener {
                override fun onIsPlayingChanged(playing: Boolean) {
                    isPlaying = playing
                    if (!playing) controlsVisible = true
                }

                override fun onPlaybackStateChanged(playbackState: Int) {
                    if (
                        playbackState == Player.STATE_ENDED &&
                        !video.live &&
                        !endDispatched
                    ) {
                        endDispatched = true
                        onEnded()
                    }
                }

                override fun onPlayerError(error: PlaybackException) {
                    playbackError = buildString {
                        append("SmartTube-Player: ")
                        append(error.errorCodeName)
                        error.cause?.message?.takeIf { it.isNotBlank() }?.let {
                            append(" · ")
                            append(it.take(220))
                        }
                    }
                }
            }
            player.addListener(listener)

            val mime = when (playback.extension.lowercase()) {
                "mpd" -> MimeTypes.APPLICATION_MPD
                "m3u8" -> MimeTypes.APPLICATION_M3U8
                "webm" -> MimeTypes.VIDEO_WEBM
                else -> null
            }

            runCatching {
                val item = MediaItem.Builder()
                    .setUri(playback.url)
                    .apply { if (mime != null) setMimeType(mime) }
                    .build()
                player.setMediaItem(item)
                player.prepare()
                player.playWhenReady = true
            }.onFailure {
                playbackError = "SmartTube-Player konnte nicht gestartet werden: " +
                    (it.message ?: it.javaClass.simpleName)
            }

            onDispose {
                runCatching { player.removeListener(listener) }
                runCatching { player.stop() }
                runCatching { player.release() }
            }
        }
    }

    Box(
        Modifier
            .fillMaxSize()
            .background(Color.Black)
            .focusRequester(remoteFocusRequester)
            .focusable()
            .onPreviewKeyEvent { event ->
                if (event.type != KeyEventType.KeyDown) {
                    false
                } else {
                    when (event.key) {
                        Key.DirectionCenter, Key.Enter, Key.NumPadEnter, Key.MediaPlayPause -> {
                            val active = player
                            if (active != null) {
                                if (active.isPlaying) active.pause() else active.play()
                                controlsVisible = true
                                true
                            } else false
                        }
                        Key.DirectionLeft -> {
                            if (!video.live && player != null) {
                                seekBy(-10_000L)
                                true
                            } else false
                        }
                        Key.DirectionRight -> {
                            if (!video.live && player != null) {
                                seekBy(10_000L)
                                true
                            } else false
                        }
                        Key.DirectionUp, Key.DirectionDown -> {
                            controlsVisible = true
                            true
                        }
                        else -> false
                    }
                }
            }
    ) {
        if (player != null) {
            AndroidView(
                factory = {
                    try {
                        PlayerView(it).apply {
                            this.player = player
                            useController = false
                            controllerAutoShow = false
                            keepScreenOn = true
                            isFocusable = false
                            isFocusableInTouchMode = false
                        }
                    } catch (error: Exception) {
                        runCatching { player.stop() }
                        playbackError = "SmartTube-Playeransicht konnte nicht geöffnet werden: " +
                            (error.message ?: error.javaClass.simpleName).take(220)
                        FrameLayout(it)
                    }
                },
                update = { (it as? PlayerView)?.player = player },
                onRelease = { (it as? PlayerView)?.player = null },
                modifier = Modifier.fillMaxSize()
            )
        }

        if (controlsVisible && errorText.isBlank()) {
            val durationMs = player?.duration?.takeIf { it > 0L }
            val progress = if (durationMs != null) {
                (positionMs.toFloat() / durationMs.toFloat()).coerceIn(0f, 1f)
            } else 0f

            Box(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .height(270.dp)
                    .background(
                        androidx.compose.ui.graphics.Brush.verticalGradient(
                            listOf(
                                Color.Transparent,
                                Color.Black.copy(alpha = .56f),
                                Color.Black.copy(alpha = .92f),
                                Color.Black
                            )
                        )
                    )
            ) {
                Column(
                    modifier = Modifier
                        .align(Alignment.BottomStart)
                        .fillMaxWidth()
                        .padding(start = 54.dp, end = 54.dp, bottom = 28.dp)
                ) {
                    Text(
                        video.title,
                        color = Color.White,
                        fontSize = 28.sp,
                        fontWeight = androidx.compose.ui.text.font.FontWeight.Black,
                        maxLines = 2
                    )
                    if (video.author.isNotBlank()) {
                        Spacer(Modifier.height(5.dp))
                        Text(
                            video.author,
                            color = Color.White.copy(alpha = .72f),
                            fontSize = 16.sp,
                            fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold,
                            maxLines = 1
                        )
                    }

                    Spacer(Modifier.height(18.dp))

                    if (!video.live && durationMs != null) {
                        LinearProgressIndicator(
                            progress = { progress },
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(7.dp),
                            color = accent,
                            trackColor = Color.White.copy(alpha = .28f)
                        )
                        Spacer(Modifier.height(9.dp))
                        Row(
                            Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                "${v111PlayerTime(positionMs)} / ${v111PlayerTime(durationMs)}",
                                color = Color.White,
                                fontSize = 17.sp,
                                fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
                            )
                            Spacer(Modifier.weight(1f))
                            Text(
                                "Links/Rechts · 10 Sekunden",
                                color = Color.White.copy(alpha = .62f),
                                fontSize = 14.sp
                            )
                        }
                    } else {
                        Surface(
                            color = Color(0xFFC60000),
                            shape = MaterialTheme.shapes.small
                        ) {
                            Text(
                                "LIVE",
                                color = Color.White,
                                fontSize = 13.sp,
                                fontWeight = androidx.compose.ui.text.font.FontWeight.Black,
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp)
                            )
                        }
                    }

                    Spacer(Modifier.height(14.dp))

                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(14.dp)
                    ) {
                        if (!video.live) {
                            V111PlayerControlChip("↶", "10 SEK.", accent)
                        }
                        V111PlayerControlChip(
                            if (isPlaying) "Ⅱ" else "▶",
                            if (isPlaying) "PAUSE" else "PLAY",
                            accent,
                            primary = true
                        )
                        if (!video.live) {
                            V111PlayerControlChip("↷", "10 SEK.", accent)
                        }
                        Spacer(Modifier.width(8.dp))
                        Text(
                            "OK · Play/Pause",
                            color = Color.White.copy(alpha = .72f),
                            fontSize = 15.sp,
                            fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold
                        )
                    }
                }
            }
        }

        if (errorText.isNotBlank()) {
            Surface(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(24.dp),
                color = Color(0xEA181B22),
                shape = MaterialTheme.shapes.medium
            ) {
                Column(Modifier.padding(horizontal = 18.dp, vertical = 14.dp)) {
                    Text(errorText, color = Color.White)
                    TextButton(onClick = onBack) {
                        Text("Zurück zu SmartTube", color = Color.White)
                    }
                }
            }
        }
    }
}


@Composable
private fun V111PlayerControlChip(
    symbol: String,
    label: String,
    accent: Color,
    primary: Boolean = false
) {
    Surface(
        color = if (primary) Color.White else Color.White.copy(alpha = .12f),
        shape = androidx.compose.foundation.shape.RoundedCornerShape(22.dp),
        border = if (primary) null else androidx.compose.foundation.BorderStroke(
            1.dp,
            Color.White.copy(alpha = .18f)
        )
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 15.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                symbol,
                color = if (primary) Color.Black else accent,
                fontSize = 20.sp,
                fontWeight = androidx.compose.ui.text.font.FontWeight.Black
            )
            Spacer(Modifier.width(7.dp))
            Text(
                label,
                color = if (primary) Color.Black else Color.White,
                fontSize = 12.sp,
                fontWeight = androidx.compose.ui.text.font.FontWeight.Black
            )
        }
    }
}

private fun v111PlayerTime(ms: Long): String {
    val total = (ms.coerceAtLeast(0L) / 1000L)
    val hours = total / 3600L
    val minutes = (total % 3600L) / 60L
    val seconds = total % 60L
    return if (hours > 0L) {
        "%d:%02d:%02d".format(hours, minutes, seconds)
    } else {
        "%d:%02d".format(minutes, seconds)
    }
}
