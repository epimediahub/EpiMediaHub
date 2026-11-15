package de.epimediahub.app.ui

import android.widget.FrameLayout
import androidx.activity.compose.BackHandler
import androidx.annotation.OptIn
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
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
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.PlayerView

@OptIn(UnstableApi::class)
@Composable
internal fun V106SmartTubePlayer(
    video: V100SmartTubeVideo,
    playback: V100SmartTubePlayback,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    var playbackError by remember(video.videoId, playback.url) { mutableStateOf("") }

    val playerResult = remember(context, video.videoId, playback.url) {
        runCatching {
            val http = DefaultHttpDataSource.Factory()
                .setUserAgent("EpiMediaHub/1.0.6")
                .setAllowCrossProtocolRedirects(true)
            val dataSource = DefaultDataSource.Factory(context, http)
            ExoPlayer.Builder(context)
                .setMediaSourceFactory(
                    DefaultMediaSourceFactory(context).setDataSourceFactory(dataSource)
                )
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

    BackHandler {
        runCatching { player?.stop() }
        onBack()
    }

    if (player != null) {
        DisposableEffect(player, video.videoId, playback.url) {
            val listener = object : Player.Listener {
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
    ) {
        if (player != null) {
            AndroidView(
                factory = {
                    try {
                        PlayerView(it).apply {
                            this.player = player
                            useController = true
                            controllerAutoShow = true
                            keepScreenOn = true
                            requestFocus()
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
