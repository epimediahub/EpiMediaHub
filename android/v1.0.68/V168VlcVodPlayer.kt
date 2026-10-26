package de.epimediahub.app.ui

import android.net.Uri
import android.view.KeyEvent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import kotlinx.coroutines.delay
import org.videolan.libvlc.LibVLC
import org.videolan.libvlc.Media
import org.videolan.libvlc.MediaPlayer
import org.videolan.libvlc.util.VLCVideoLayout

/**
 * Isolated, explicitly selected compatibility test for VOD.
 * Never affects Live or automatic Media3 playback. It has its own native session
 * and does not attempt to reuse Media3's view or two simultaneous decoders.
 */
@Composable
internal fun V168VlcVodPlayer(
    vm: MainViewModel,
    item: MediaEntry,
    episodes: List<MediaEntry>,
    isTv: Boolean,
    url: String,
    userAgent: String,
    referer: String,
    onStandardPlayer: () -> Unit
) {
    val context = LocalContext.current
    val libVlc = remember(item.resumeKey) {
        LibVLC(context, arrayListOf("--network-caching=1800",
            "--no-mediacodec-audio", "--audio-replay-gain-mode=none"))
    }
    val player = remember(libVlc) { MediaPlayer(libVlc) }
    val focus = remember(item.resumeKey) { FocusRequester() }
    var position by remember(item.resumeKey) { mutableLongStateOf(0L) }
    var duration by remember(item.resumeKey) { mutableLongStateOf(0L) }
    var isPlaying by remember(item.resumeKey) { mutableStateOf(false) }
    var error by remember(item.resumeKey) { mutableStateOf("") }
    var controls by remember(item.resumeKey) { mutableStateOf(true) }
    fun save() {
        if (position > 0L && duration > 0L) vm.savePlayback(item, position, duration)
    }
    fun backToStandard() { save(); onStandardPlayer() }
    fun leave() { save(); vm.back() }
    fun seekBy(delta: Long) {
        if (player.isSeekable) {
            val current = player.time.coerceAtLeast(0L)
            val length = player.length.coerceAtLeast(0L)
            player.time = (current + delta).coerceIn(0L, if (length > 0L) length else Long.MAX_VALUE)
            position = player.time.coerceAtLeast(0L)
        }
        controls = true
    }
    fun togglePause() {
        if (player.isPlaying) player.pause() else player.play()
        controls = true
    }
    fun changeEpisode(offset: Int): Boolean {
        if (item.kind != MediaKind.EPISODE) return false
        val index = episodes.indexOfFirst { it.id == item.id }
        if (index < 0 || index + offset !in episodes.indices) return false
        save()
        vm.skipEpisode(item, episodes, offset)
        return true
    }

    DisposableEffect(player, url, userAgent, referer) {
        var closed = false
        val media = Media(libVlc, Uri.parse(url))
        try {
            media.addOption(":network-caching=1800")
            media.setHWDecoderEnabled(true, false)
            media.addOption(":no-mediacodec-dr")
            media.addOption(":no-mediacodec-audio")
            media.addOption(":http-user-agent=" + userAgent.ifBlank { "VLC/3.0.21 LibVLC/3.0.21" })
            if (referer.isNotBlank()) media.addOption(":http-referrer=" + referer)
            player.media = media
        } finally { media.release() }
        player.setEventListener { event ->
            if (!closed && event.type == MediaPlayer.Event.EncounteredError) {
                error = "VLC konnte diesen Film nicht abspielen. Menü: Standardplayer."
            }
        }
        runCatching { player.play() }.onFailure {
            error = "VLC konnte den Test-Stream nicht starten."
        }
        onDispose {
            closed = true
            save()
            player.setEventListener(null)
            runCatching { player.stop() }
            runCatching { player.detachViews() }
            runCatching { player.release() }
            runCatching { libVlc.release() }
        }
    }
    LaunchedEffect(player, item.resumeKey) {
        var resumed = false
        var lastSave = 0L
        while (true) {
            val length = player.length.coerceAtLeast(0L)
            if (!resumed && player.isSeekable && length > 0L) {
                resumed = true
                val resume = vm.resume(item)
                if (resume in 10_001L until length) player.time = resume
            }
            position = player.time.coerceAtLeast(0L)
            duration = length
            isPlaying = player.isPlaying
            if (position > 0 && duration > 0 && position - lastSave >= 8_000L) {
                vm.savePlayback(item, position, duration)
                lastSave = position
            }
            delay(500L)
        }
    }
    LaunchedEffect(item.resumeKey) { runCatching { focus.requestFocus() } }
    BackHandler { leave() }

    Box(Modifier.fillMaxSize().background(Color.Black)
        .onPreviewKeyEvent { event ->
            if (!isTv || event.nativeKeyEvent.action != KeyEvent.ACTION_DOWN) return@onPreviewKeyEvent false
            when (event.nativeKeyEvent.keyCode) {
                KeyEvent.KEYCODE_MENU, KeyEvent.KEYCODE_INFO -> {
                    if (event.nativeKeyEvent.repeatCount == 0) backToStandard()
                    true
                }
                KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_MEDIA_REWIND -> { seekBy(-10_000L); true }
                KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> { seekBy(10_000L); true }
                KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, KeyEvent.KEYCODE_MEDIA_PLAY, KeyEvent.KEYCODE_MEDIA_PAUSE -> {
                    if (event.nativeKeyEvent.repeatCount == 0) togglePause()
                    true
                }
                KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> {
                    if (event.nativeKeyEvent.repeatCount == 0) controls = !controls
                    true
                }
                KeyEvent.KEYCODE_MEDIA_NEXT, KeyEvent.KEYCODE_CHANNEL_UP -> changeEpisode(1)
                KeyEvent.KEYCODE_MEDIA_PREVIOUS, KeyEvent.KEYCODE_CHANNEL_DOWN -> changeEpisode(-1)
                else -> false
            }
        }.focusRequester(focus).focusable()
    ) {
        AndroidView(factory = { ctx ->
            VLCVideoLayout(ctx).also { player.attachViews(it, null, false, false) }
        }, modifier = Modifier.fillMaxSize())
        Surface(Modifier.align(Alignment.TopEnd).padding(12.dp),
            color = Color(0xBB101820)) {
            Text("VLC-TEST · Menü = Standardplayer", color = Color.White,
                fontSize = 12.sp, modifier = Modifier.padding(8.dp))
        }
        if (error.isNotBlank()) {
            Surface(Modifier.align(Alignment.Center), color = Color(0xDD222222)) {
                Text(error, color = Color.White, modifier = Modifier.padding(18.dp))
            }
        }
        if (controls) {
            Surface(Modifier.align(Alignment.BottomCenter).fillMaxWidth(),
                color = Color(0xE5111922)) {
                Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                    Text(item.name + "  ·  " + v168Time(position) + " / " + v168Time(duration),
                        color = Color.White, fontSize = 13.sp)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        TextButton(onClick = { seekBy(-10_000L) }) { Text("−10 s") }
                        TextButton(onClick = ::togglePause) { Text(if (isPlaying) "Pause" else "Weiter") }
                        TextButton(onClick = { seekBy(10_000L) }) { Text("+10 s") }
                        Spacer(Modifier.weight(1f))
                        TextButton(onClick = ::backToStandard) { Text("Standardplayer") }
                    }
                }
            }
        }
    }
}

private fun v168Time(ms: Long): String {
    val seconds = (ms.coerceAtLeast(0L) / 1000L)
    return "%02d:%02d:%02d".format(seconds / 3600, seconds / 60 % 60, seconds % 60)
}
