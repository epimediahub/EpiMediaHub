package de.epimediahub.app.ui

import android.view.KeyEvent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.SkipNext
import androidx.compose.material.icons.filled.SkipPrevious
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.common.TrackSelectionParameters
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind

@Composable
fun PlayerScreen(vm: MainViewModel, item: MediaEntry, episodeList: List<MediaEntry>, accent: Color, isTv: Boolean) {
    val context = LocalContext.current
    val u by vm.ui.collectAsState()

    val loadControl = remember(item.kind) {
        val live = item.kind == MediaKind.LIVE
        DefaultLoadControl.Builder()
            .setBufferDurationsMs(
                if (live) 8_000 else 18_000,
                if (live) 30_000 else 90_000,
                if (live) 2_500 else 3_000,
                if (live) 5_000 else 6_000
            )
            .setPrioritizeTimeOverSizeThresholds(true)
            .build()
    }

    val player = remember(item.resumeKey) {
        ExoPlayer.Builder(context)
            .setLoadControl(loadControl)
            .build()
    }
    var controls by remember { mutableStateOf(true) }
    var buffering by remember(item.resumeKey) { mutableStateOf(false) }

    fun save() {
        runCatching {
            vm.savePlayback(item, player.currentPosition, player.duration.takeIf { it > 0 } ?: 0)
        }
    }

    fun leave() {
        save()
        player.release()
        vm.back()
    }

    BackHandler { leave() }

    DisposableEffect(player, item.resumeKey) {
        val params = TrackSelectionParameters.Builder(context)
            .setPreferredAudioLanguage(u.preferredAudioLanguage)
            .apply {
                if (u.preferredSubtitleLanguage == "none") {
                    setTrackTypeDisabled(C.TRACK_TYPE_TEXT, true)
                } else {
                    setPreferredTextLanguage(u.preferredSubtitleLanguage)
                }
            }
            .build()
        player.trackSelectionParameters = params
        player.setMediaItem(MediaItem.fromUri(item.streamUrl))
        player.prepare()

        val resume = vm.resume(item)
        if (resume > 10_000 && item.kind != MediaKind.LIVE) player.seekTo(resume)
        player.playWhenReady = true

        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                buffering = state == Player.STATE_BUFFERING
                if (state == Player.STATE_ENDED) save()
            }

            override fun onIsLoadingChanged(isLoading: Boolean) {
                if (!isLoading && player.playbackState == Player.STATE_READY) buffering = false
            }
        }
        player.addListener(listener)
        onDispose {
            save()
            player.removeListener(listener)
            player.release()
        }
    }

    val idx = episodeList.indexOfFirst { it.id == item.id }
    val prev = idx > 0
    val next = idx >= 0 && idx < episodeList.lastIndex

    Box(
        Modifier
            .fillMaxSize()
            .background(Color.Black)
            .onPreviewKeyEvent { e ->
                if (!isTv || e.nativeKeyEvent.action != KeyEvent.ACTION_DOWN) return@onPreviewKeyEvent false
                when (e.nativeKeyEvent.keyCode) {
                    KeyEvent.KEYCODE_DPAD_LEFT -> if (prev) {
                        save(); player.release(); vm.skipEpisode(item, episodeList, -1); true
                    } else false
                    KeyEvent.KEYCODE_DPAD_RIGHT -> if (next) {
                        save(); player.release(); vm.skipEpisode(item, episodeList, 1); true
                    } else false
                    KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> {
                        controls = !controls
                        false
                    }
                    else -> false
                }
            }
            .focusable()
    ) {
        AndroidView(
            factory = {
                PlayerView(it).apply {
                    this.player = player
                    useController = true
                    controllerAutoShow = true
                    keepScreenOn = true
                }
            },
            update = { it.player = player },
            modifier = Modifier.fillMaxSize()
        )

        if (buffering) {
            Surface(
                modifier = Modifier.align(Alignment.Center),
                color = Color.Black.copy(alpha = .58f),
                shape = MaterialTheme.shapes.large
            ) {
                Row(
                    Modifier.padding(horizontal = 20.dp, vertical = 14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    CircularProgressIndicator(modifier = Modifier.size(26.dp), color = accent, strokeWidth = 3.dp)
                    Text("Stream wird gepuffert …")
                }
            }
        }

        if (item.kind == MediaKind.EPISODE && controls) {
            Row(
                Modifier.align(Alignment.TopCenter).padding(18.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                FilledTonalButton(
                    onClick = { if (prev) { save(); player.release(); vm.skipEpisode(item, episodeList, -1) } },
                    enabled = prev
                ) {
                    Icon(Icons.Default.SkipPrevious, null)
                    Spacer(Modifier.width(6.dp))
                    Text("Vorherige")
                }
                FilledTonalButton(
                    onClick = { if (next) { save(); player.release(); vm.skipEpisode(item, episodeList, 1) } },
                    enabled = next
                ) {
                    Text("Nächste")
                    Spacer(Modifier.width(6.dp))
                    Icon(Icons.Default.SkipNext, null)
                }
            }
        }
    }
}
