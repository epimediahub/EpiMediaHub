package de.epimediahub.app.ui

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.view.KeyEvent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import de.epimediahub.app.R
import de.epimediahub.app.isAndroidTv
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume
import kotlin.math.sin

/** Replacement for the existing entry point; pairing and the license gate remain in control. */
@Composable
fun V070IntroScreen(accent: Color, onFinished: () -> Unit) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val latestFinished by rememberUpdatedState(onFinished)
    val sound = remember(context.applicationContext) { V121IntroSound(context.applicationContext) }
    var elapsed by remember { mutableLongStateOf(0L) }
    var finished by remember { mutableStateOf(false) }
    fun finish() {
        if (!finished) {
            finished = true
            sound.close()
            latestFinished()
        }
    }
    BackHandler { finish() }
    DisposableEffect(lifecycle, sound) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) finish()
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); sound.close() }
    }
    LaunchedEffect(sound, finished) {
        if (!finished) {
            // Local preparation is bounded; audio failure must never delay opening the app.
            sound.prepare()
            if (!finished) {
                val started = withFrameNanos { it }
                sound.start()
                while (elapsed < V121IntroTimeline.DURATION_MS && !finished) {
                    elapsed = ((withFrameNanos { it } - started) / 1_000_000L).coerceAtLeast(0L)
                }
                finish()
            }
        }
    }
    V121IntroContent(elapsed, accent, isAndroidTv(context), ::finish)
}

@Composable
internal fun V121IntroContent(elapsedMs: Long, accent: Color, isTv: Boolean, onSkip: () -> Unit) {
    val focus = remember { FocusRequester() }
    val interaction = remember { MutableInteractionSource() }
    LaunchedEffect(Unit) { runCatching { focus.requestFocus() } }
    val world = V121IntroTimeline.worldAlpha(elapsedMs)
    val oneApp = V121IntroTimeline.appAlpha(elapsedMs)
    val logo = V121IntroTimeline.logoAlpha(elapsedMs)
    val pulse = V121IntroTimeline.pulse(elapsedMs)
    val scale = V121IntroTimeline.textScale(elapsedMs)
    BoxWithConstraints(
        Modifier.fillMaxSize().background(Color(0xFF02050B)).testTag("cinematic-intro")
            .focusRequester(focus).onPreviewKeyEvent { event ->
                val key = event.nativeKeyEvent
                if (key.keyCode in listOf(KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER,
                        KeyEvent.KEYCODE_SPACE, KeyEvent.KEYCODE_ESCAPE, KeyEvent.KEYCODE_BACK)) {
                    if (key.action == KeyEvent.ACTION_DOWN && key.repeatCount == 0) onSkip()
                    true
                } else false // Volume keys continue to change volume.
            }.focusable()
            .clickable(interactionSource = interaction, indication = null, onClickLabel = "Skip intro", onClick = onSkip),
        contentAlignment = Alignment.Center
    ) {
        val unit = minOf(maxWidth.value / 960f, maxHeight.value / 540f).coerceAtLeast(.25f)
        Canvas(Modifier.fillMaxSize()) {
            val pixels = unit * density
            val center = Offset(size.width * .5f, size.height * .50f)
            val radius = size.width * .52f
            drawRect(Brush.radialGradient(listOf(Color(0xFF0A1930), Color(0xFF02050B)), center, radius))
            drawCircle(Brush.radialGradient(listOf(accent.copy(alpha = .045f + .025f * pulse + .06f * logo),
                Color.Transparent), center, radius * .7f), radius * .7f, center)
            // Sparse, slow dust, no camera shake, flashing white frames or heavy blur layers.
            repeat(34) { i ->
                val x = ((i * 137.5078f) % 960f) / 960f * size.width
                val y = (((i * 71.71f) % 470f + 35f) / 540f * size.height) - elapsedMs * .0015f * pixels
                val shimmer = .045f + .055f * ((sin(elapsedMs / 2100f + i) + 1f) * .5f)
                drawCircle(Color(0xFFBAD9EF).copy(alpha = shimmer), (if (i % 5 == 0) 1.2f else .65f) * pixels, Offset(x, y))
            }
            if (logo > 0f) {
                val reveal = V121IntroTimeline.ease((elapsedMs - V121IntroTimeline.LOGO_START_MS).toFloat() / 650f)
                val width = size.width * (.16f + .52f * reveal)
                val glow = logo * (1f - reveal) * .55f + logo * .08f
                drawLine(Brush.horizontalGradient(listOf(Color.Transparent, accent.copy(alpha = glow), Color.Transparent),
                    center.x - width / 2, center.x + width / 2),
                    Offset(center.x - width / 2, center.y + 43f * pixels),
                    Offset(center.x + width / 2, center.y + 43f * pixels), 1.3f * pixels)
            }
            drawRect(Color.Black.copy(alpha = .65f), size = Size(size.width, size.height * .055f))
            drawRect(Color.Black.copy(alpha = .65f), Offset(0f, size.height * .945f), Size(size.width, size.height * .055f))
        }
        if (world > 0f) Text("The whole world\nof multimedia", color = Color(0xFFF1F5FC),
            fontSize = (48f * unit).sp, lineHeight = (64f * unit).sp, letterSpacing = (1.5f * unit).sp,
            fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Light, textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth(.88f).testTag("intro-world").graphicsLayer {
                alpha = world; scaleX = scale; scaleY = scale
            })
        if (oneApp > 0f) Text("One App", color = Color(0xFFF5F8FF), fontSize = (76f * unit).sp,
            letterSpacing = (3.5f * unit).sp, fontFamily = FontFamily.SansSerif, fontWeight = FontWeight.Medium,
            textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth(.84f).testTag("intro-one-app").graphicsLayer {
                alpha = oneApp; scaleX = scale; scaleY = scale
            })
        if (logo > 0f) Image(painterResource(R.drawable.brand_header), "EpiMediaHub",
            modifier = Modifier.width((690f * unit).dp).height((220f * unit).dp).testTag("intro-logo").graphicsLayer {
                alpha = logo; scaleX = V121IntroTimeline.logoScale(elapsedMs); scaleY = scaleX
            }, contentScale = ContentScale.Fit)
        Text(if (isTv) "PRESS OK TO SKIP" else "TAP TO SKIP", color = Color.White.copy(alpha = .34f),
            fontSize = (10f * unit).coerceAtLeast(9f).sp, letterSpacing = (2f * unit).sp,
            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = (43f * unit).dp))
    }
}

private class V121IntroSound(private val context: Context) {
    private var player: MediaPlayer? = null
    private var closed = false

    suspend fun prepare() {
        if (closed) return
        val prepared = withTimeoutOrNull(450L) {
            suspendCancellableCoroutine<Boolean> { continuation ->
                try {
                    val media = MediaPlayer()
                    player = media
                    media.setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
                    media.setVolume(.76f, .76f)
                    media.setOnPreparedListener { if (continuation.isActive) continuation.resume(true) }
                    media.setOnErrorListener { _, _, _ ->
                        if (continuation.isActive) continuation.resume(false)
                        true
                    }
                    continuation.invokeOnCancellation { close() }
                    context.resources.openRawResourceFd(R.raw.epimedia_intro_heartbeat_cinema).use { fd ->
                        media.setDataSource(fd.fileDescriptor, fd.startOffset, fd.length)
                    }
                    media.prepareAsync()
                } catch (_: Exception) {
                    if (continuation.isActive) continuation.resume(false)
                }
            }
        }
        if (prepared != true) close()
    }

    fun start() { if (!closed) runCatching { player?.start() } }
    fun close() {
        if (closed) return
        closed = true
        val current = player
        player = null
        runCatching { current?.setOnPreparedListener(null); current?.setOnErrorListener(null) }
        runCatching { current?.release() }
    }
}
