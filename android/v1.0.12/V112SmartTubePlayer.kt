package de.epimediahub.app.ui

import android.widget.FrameLayout
import androidx.activity.compose.BackHandler
import androidx.annotation.OptIn
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
internal fun V112SmartTubePlayer(
    video: V100SmartTubeVideo,
    playback: V100SmartTubePlayback,
    isTv: Boolean,
    accent: Color,
    onBack: () -> Unit,
    onEnded: () -> Unit,
    historyAccountKey: String,
    onProgress: (video: V100SmartTubeVideo, accountKey: String, positionMs: Long, durationMs: Long, ended: Boolean) -> Unit
) {
    val context = LocalContext.current
    val reportProgress by rememberUpdatedState(onProgress)
    val endPlayback by rememberUpdatedState(onEnded)
    var playbackError by remember(video.videoId, playback.url) { mutableStateOf("") }
    var controlsVisible by remember(video.videoId) { mutableStateOf(true) }
    var isPlaying by remember(video.videoId) { mutableStateOf(false) }
    var positionMs by remember(video.videoId) { mutableLongStateOf(0L) }
    val remoteFocusRequester = remember { FocusRequester() }

    val playerResult = remember(context, video.videoId, playback.url) {
        runCatching {
            val http = DefaultHttpDataSource.Factory()
                .setUserAgent("EpiMediaHub/1.0.12")
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
        var lastReportAt = System.currentTimeMillis()
        var watchedReported = false
        while (player != null) {
            positionMs = runCatching { player.currentPosition.coerceAtLeast(0L) }.getOrDefault(0L)
            val duration = player.duration.takeIf { it > 0L } ?: video.durationMs
            val now = System.currentTimeMillis()
            val watched = V112SmartTubeWatchRules.isWatched(video.live, positionMs, duration, false)
            if (player.isPlaying && (now - lastReportAt >= 30_000L || (watched && !watchedReported))) {
                reportProgress(video, historyAccountKey, positionMs, duration, false)
                lastReportAt = now
                watchedReported = watchedReported || watched
            }
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
                        reportProgress(video, historyAccountKey, player.currentPosition.coerceAtLeast(1L),
                            player.duration.takeIf { it > 0L } ?: video.durationMs, true)
                        endPlayback()
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
                runCatching {
                    reportProgress(video, historyAccountKey, player.currentPosition.coerceAtLeast(0L),
                        player.duration.takeIf { it > 0L } ?: video.durationMs, endDispatched)
                }
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
            // YouTube-TV-like control layer: large readable title, big transport
            // controls, full-width timeline and clearly visible elapsed/total time.
            Box(
                Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .height(if (isTv) 330.dp else 245.dp)
                    .background(
                        androidx.compose.ui.graphics.Brush.verticalGradient(
                            listOf(
                                Color.Transparent,
                                Color.Black.copy(alpha = .52f),
                                Color.Black.copy(alpha = .94f)
                            )
                        )
                    )
            )

            Row(
                modifier = Modifier.align(Alignment.Center),
                horizontalArrangement = Arrangement.spacedBy(if (isTv) 34.dp else 20.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                if (!video.live) {
                    V112PlayerControlBubble(
                        label = "−10",
                        subtitle = "Sek.",
                        isTv = isTv,
                        onClick = { seekBy(-10_000L) }
                    )
                }

                V112PlayerControlBubble(
                    label = if (isPlaying) "Ⅱ" else "▶",
                    subtitle = if (isPlaying) "Pause" else "Play",
                    isTv = isTv,
                    primary = true,
                    onClick = {
                        player?.let { active ->
                            if (active.isPlaying) active.pause() else active.play()
                        }
                        controlsVisible = true
                    }
                )

                if (!video.live) {
                    V112PlayerControlBubble(
                        label = "+10",
                        subtitle = "Sek.",
                        isTv = isTv,
                        onClick = { seekBy(10_000L) }
                    )
                }
            }

            Column(
                Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .padding(
                        start = if (isTv) 48.dp else 20.dp,
                        end = if (isTv) 48.dp else 20.dp,
                        bottom = if (isTv) 30.dp else 18.dp
                    )
            ) {
                Text(
                    video.title,
                    color = Color.White,
                    fontSize = if (isTv) 30.sp else 22.sp,
                    lineHeight = if (isTv) 35.sp else 27.sp,
                    fontWeight = FontWeight.Black,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )

                if (video.author.isNotBlank()) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        video.author,
                        color = Color.White.copy(alpha = .74f),
                        fontSize = if (isTv) 17.sp else 13.sp,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1
                    )
                }

                Spacer(Modifier.height(if (isTv) 18.dp else 12.dp))

                if (!video.live) {
                    val duration = player?.duration?.takeIf { it > 0L }
                    LinearProgressIndicator(
                        progress = {
                            if (duration == null) 0f
                            else (positionMs.toFloat() / duration.toFloat()).coerceIn(0f, 1f)
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(if (isTv) 9.dp else 6.dp),
                        color = accent,
                        trackColor = Color.White.copy(alpha = .26f)
                    )
                    Spacer(Modifier.height(if (isTv) 10.dp else 7.dp))
                    Row(
                        Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            v112FormatPlaybackTime(positionMs) + " / " +
                                v112FormatPlaybackTime(duration ?: 0L),
                            color = Color.White,
                            fontSize = if (isTv) 20.sp else 15.sp,
                            fontWeight = FontWeight.Black
                        )
                        Spacer(Modifier.weight(1f))
                        Text(
                            "◀ 10 Sek.    OK Play/Pause    10 Sek. ▶",
                            color = Color.White.copy(alpha = .76f),
                            fontSize = if (isTv) 15.sp else 11.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                    }
                } else {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Surface(
                            color = Color(0xFFE62117),
                            shape = MaterialTheme.shapes.small
                        ) {
                            Text(
                                "LIVE",
                                color = Color.White,
                                fontSize = if (isTv) 15.sp else 11.sp,
                                fontWeight = FontWeight.Black,
                                modifier = Modifier.padding(horizontal = 9.dp, vertical = 4.dp)
                            )
                        }
                        Spacer(Modifier.width(12.dp))
                        Text(
                            if (isPlaying) "OK · Pause" else "OK · Wiedergabe",
                            color = Color.White.copy(alpha = .82f),
                            fontSize = if (isTv) 17.sp else 12.sp,
                            fontWeight = FontWeight.Bold
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
private fun V112PlayerControlChip(
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

private fun v112PlayerTime(ms: Long): String {
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


@Composable
private fun V112PlayerControlBubble(
    label: String,
    subtitle: String,
    isTv: Boolean,
    primary: Boolean = false,
    onClick: () -> Unit
) {
    Surface(
        onClick = onClick,
        modifier = Modifier.size(if (isTv) 92.dp else 68.dp),
        color = if (primary) Color.White.copy(alpha = .97f) else Color.Black.copy(alpha = .68f),
        contentColor = if (primary) Color.Black else Color.White,
        shape = CircleShape,
        border = if (primary) null else BorderStroke(1.dp, Color.White.copy(alpha = .28f))
    ) {
        Column(
            Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text(
                label,
                fontSize = if (isTv) 30.sp else 22.sp,
                fontWeight = FontWeight.Black
            )
            Text(
                subtitle,
                fontSize = if (isTv) 11.sp else 9.sp,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

private fun v112FormatPlaybackTime(ms: Long): String {
    val totalSeconds = ms.coerceAtLeast(0L) / 1000L
    val seconds = totalSeconds % 60
    val minutes = (totalSeconds / 60) % 60
    val hours = totalSeconds / 3600
    return if (hours > 0) {
        "%d:%02d:%02d".format(hours, minutes, seconds)
    } else {
        "%d:%02d".format(minutes, seconds)
    }
}
