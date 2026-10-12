package de.epimediahub.app.ui

import android.net.Uri
import android.view.KeyEvent
import android.view.ViewGroup
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.media3.common.AudioAttributes
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import de.epimediahub.app.R
import de.epimediahub.app.isAndroidTv
import kotlinx.coroutines.delay

/** The approved V5 picture and sound are played together from the APK, offline. */
@OptIn(UnstableApi::class)
@Composable
internal fun V161IntroVideoScreen(accent: Color, onFinished: () -> Unit) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val latestFinished by rememberUpdatedState(onFinished)
    val introPlayer = remember(context.applicationContext) {
        ExoPlayer.Builder(context.applicationContext).build().apply {
            repeatMode = Player.REPEAT_MODE_OFF
            setAudioAttributes(AudioAttributes.DEFAULT, true)
        }
    }
    val focus = remember { FocusRequester() }
    val interaction = remember { MutableInteractionSource() }
    var finished by remember { mutableStateOf(false) }
    fun finish() {
        if (!finished) {
            finished = true
            runCatching { introPlayer.stop() }
            latestFinished()
        }
    }
    BackHandler { finish() }
    DisposableEffect(introPlayer, lifecycle) {
        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) finish()
            }
            override fun onPlayerError(error: PlaybackException) { finish() }
        }
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) finish()
        }
        introPlayer.addListener(listener)
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            introPlayer.removeListener(listener)
            introPlayer.release()
        }
    }
    LaunchedEffect(introPlayer) {
        runCatching { focus.requestFocus() }
        try {
            introPlayer.setMediaItem(MediaItem.fromUri(Uri.parse(
                "android.resource://${context.packageName}/${R.raw.epimedia_intro_v5}")))
            introPlayer.prepare()
            introPlayer.playWhenReady = true
        } catch (_: Exception) { finish() }
        // A device decoder failure must not strand the user on the launch screen.
        delay(20_000L)
        finish()
    }
    Box(Modifier.fillMaxSize().background(Color.Black).testTag("cinematic-intro")
        .focusRequester(focus).onPreviewKeyEvent { event ->
            val key = event.nativeKeyEvent
            if (key.keyCode in listOf(KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER,
                    KeyEvent.KEYCODE_NUMPAD_ENTER, KeyEvent.KEYCODE_SPACE,
                    KeyEvent.KEYCODE_ESCAPE, KeyEvent.KEYCODE_BACK)) {
                if (key.action == KeyEvent.ACTION_DOWN && key.repeatCount == 0) finish()
                true
            } else false
        }.focusable()
        .clickable(interactionSource = interaction, indication = null,
            onClickLabel = "Intro überspringen", onClick = ::finish)) {
        AndroidView(factory = { viewContext ->
            PlayerView(viewContext).apply {
                useController = false
                controllerAutoShow = false
                resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                setEnableComposeSurfaceSyncWorkaround(true)
                isFocusable = false
                isFocusableInTouchMode = false
                descendantFocusability = ViewGroup.FOCUS_BLOCK_DESCENDANTS
                keepScreenOn = true
                this.player = introPlayer
            }
        }, modifier = Modifier.fillMaxSize(), onRelease = { it.player = null })
        Text(if (isAndroidTv(context)) "OK zum Überspringen" else "Tippen zum Überspringen",
            color = Color.White.copy(alpha = .55f), fontSize = 11.sp,
            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 20.dp)
                .background(accent.copy(alpha = .12f)).padding(horizontal = 10.dp, vertical = 4.dp))
    }
}
