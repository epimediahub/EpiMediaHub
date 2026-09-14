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
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind

@Composable
fun PlayerScreen(vm: MainViewModel, item: MediaEntry, episodeList: List<MediaEntry>, accent: Color, isTv: Boolean) {
    val context = LocalContext.current
    val u by vm.ui.collectAsState()
    val player = remember(item.id) { ExoPlayer.Builder(context).build() }
    var controls by remember { mutableStateOf(true) }

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

    fun seekBy(deltaMs: Long) {
        val duration = player.duration.takeIf { it > 0 } ?: Long.MAX_VALUE
        val target = (player.currentPosition + deltaMs).coerceAtLeast(0L).coerceAtMost(duration)
        player.seekTo(target)
        controls = true
    }

    fun togglePlayback() {
        if (player.isPlaying) player.pause() else player.play()
        controls = true
    }

    BackHandler { leave() }

    DisposableEffect(player, item.id) {
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
                if (state == Player.STATE_ENDED) save()
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
    val isEpisode = item.kind == MediaKind.EPISODE

    fun previousEpisode(): Boolean {
        if (!isEpisode || !prev) return false
        save()
        vm.skipEpisode(item, episodeList, -1)
        return true
    }

    fun nextEpisode(): Boolean {
        if (!isEpisode || !next) return false
        save()
        vm.skipEpisode(item, episodeList, 1)
        return true
    }

    Box(
        Modifier
            .fillMaxSize()
            .background(Color.Black)
            .onPreviewKeyEvent { e ->
                if (!isTv || e.nativeKeyEvent.action != KeyEvent.ACTION_DOWN) {
                    return@onPreviewKeyEvent false
                }
                when (e.nativeKeyEvent.keyCode) {
                    KeyEvent.KEYCODE_DPAD_LEFT -> if (isEpisode && prev) previousEpisode() else { seekBy(-10_000L); true }
                    KeyEvent.KEYCODE_DPAD_RIGHT -> if (isEpisode && next) nextEpisode() else { seekBy(10_000L); true }

                    KeyEvent.KEYCODE_1,
                    KeyEvent.KEYCODE_NUMPAD_1,
                    KeyEvent.KEYCODE_MEDIA_PREVIOUS,
                    KeyEvent.KEYCODE_CHANNEL_DOWN,
                    KeyEvent.KEYCODE_PAGE_DOWN -> previousEpisode()

                    KeyEvent.KEYCODE_3,
                    KeyEvent.KEYCODE_NUMPAD_3,
                    KeyEvent.KEYCODE_MEDIA_NEXT,
                    KeyEvent.KEYCODE_CHANNEL_UP,
                    KeyEvent.KEYCODE_PAGE_UP -> nextEpisode()

                    KeyEvent.KEYCODE_4,
                    KeyEvent.KEYCODE_NUMPAD_4 -> { seekBy(-10_000L); true }

                    KeyEvent.KEYCODE_6,
                    KeyEvent.KEYCODE_NUMPAD_6 -> { seekBy(10_000L); true }

                    KeyEvent.KEYCODE_5,
                    KeyEvent.KEYCODE_NUMPAD_5,
                    KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,
                    KeyEvent.KEYCODE_SPACE -> { togglePlayback(); true }

                    KeyEvent.KEYCODE_MEDIA_PLAY -> { player.play(); controls = true; true }
                    KeyEvent.KEYCODE_MEDIA_PAUSE -> { player.pause(); controls = true; true }
                    KeyEvent.KEYCODE_DPAD_UP -> { controls = true; false }
                    KeyEvent.KEYCODE_DPAD_DOWN -> { controls = false; false }
                    KeyEvent.KEYCODE_MENU -> { controls = true; true }
                    KeyEvent.KEYCODE_DPAD_CENTER,
                    KeyEvent.KEYCODE_ENTER -> { controls = !controls; false }
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
                }
            },
            update = { it.player = player },
            modifier = Modifier.fillMaxSize()
        )

        if (isEpisode && controls) {
            Row(
                Modifier.align(Alignment.TopCenter).padding(18.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                FilledTonalButton(
                    onClick = { previousEpisode() },
                    enabled = prev
                ) {
                    Icon(Icons.Default.SkipPrevious, null)
                    Spacer(Modifier.width(6.dp))
                    Text("Vorherige")
                }
                FilledTonalButton(
                    onClick = { nextEpisode() },
                    enabled = next
                ) {
                    Text("Nächste")
                    Spacer(Modifier.width(6.dp))
                    Icon(Icons.Default.SkipNext, null)
                }
            }
        }

        if (isTv && controls) {
            Surface(
                modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 14.dp),
                color = Color.Black.copy(alpha = .58f),
                shape = MaterialTheme.shapes.large
            ) {
                Text(
                    "←/→ Episode oder ±10 s   ·   1/3 Episode   ·   4/6 ±10 s   ·   5 Play/Pause",
                    color = Color.White.copy(alpha = .80f),
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                )
            }
        }
    }
}
