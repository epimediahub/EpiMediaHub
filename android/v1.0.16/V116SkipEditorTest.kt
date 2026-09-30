package de.epimediahub.app.ui

import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.media3.common.Player
import de.epimediahub.app.data.V115Segment
import de.epimediahub.app.data.V115SegmentKind
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.LooperMode
import java.lang.reflect.Proxy
import java.io.File

@OptIn(ExperimentalTestApi::class, ExperimentalComposeUiApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V116SkipEditorTest {
    @get:Rule val compose = createComposeRule()
    private fun settle() { compose.waitForIdle(); compose.mainClock.advanceTimeBy(250); compose.waitForIdle() }
    private fun screenshot(name: String) {
        // SDK 28's Robolectric does not drive PixelCopy redraw callbacks.
        // Draw the actual dialog window, including its visible focus ring.
        lateinit var bitmap: Bitmap
        compose.runOnIdle {
            val windows = Class.forName("android.view.WindowManagerGlobal")
            val global = windows.getMethod("getInstance").invoke(null)
            @Suppress("UNCHECKED_CAST")
            val roots = windows.getDeclaredField("mViews").apply { isAccessible = true }.get(global) as List<View>
            val root = roots.last()
            bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888)
            root.draw(Canvas(bitmap))
        }
        File("build/reports/ui").mkdirs()
        File("build/reports/ui", name).outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    @Test fun skipExplicitlySeeksThenResumesAPausedOrBufferingPlayer() {
        val calls = mutableListOf<String>()
        val player = Proxy.newProxyInstance(Player::class.java.classLoader, arrayOf(Player::class.java)) { _, method, args ->
            when (method.name) {
                "getDuration" -> 2_400_000L
                "isCurrentMediaItemSeekable" -> true
                "seekTo" -> { calls += "seek:${args!![0]}"; null }
                "play" -> { calls += "play"; null }
                else -> throw IllegalStateException(method.name)
            }
        } as Player
        assertTrue(V116Playback.skip(player, V115Segment(V115SegmentKind.INTRO, 30_000, 90_000, "Own", true, 1.0)))
        assertEquals(listOf("seek:90000", "play"), calls)
        calls.clear()
        assertFalse(V116Playback.skip(player, V115Segment(V115SegmentKind.INTRO, 30_000, 2_500_000, "Bad", true, 1.0)))
        assertTrue(calls.isEmpty())
    }

    @Test fun remoteCanCaptureBothBoundariesAndSaveOnlyAValidRange() {
        var position = 30_000L
        val saved = mutableListOf<V116Draft>()
        val drafts = mutableStateMapOf<V115SegmentKind, V116Draft>()
        compose.setContent { MaterialTheme { V116SkipEditor(2_400_000, { position }, emptyList(), drafts, "", true,
            onSeek = { position = it }, onSave = { _, start, end, _ -> saved += V116Draft(start, end) }, onReset = {}, onResolve = {}, onDismiss = {}) } }
        settle()
        compose.onNodeWithTag("mark-type-INTRO").assertIsFocused()
        screenshot("v116-tv-skip-editor.png")
        compose.onNodeWithTag("mark-save").performScrollTo().assertIsNotEnabled()
        compose.onNodeWithTag("mark-start").performScrollTo().performClick(); settle()
        compose.runOnIdle { position = 90_000L }
        compose.onNodeWithTag("mark-end").performScrollTo().performClick(); settle()
        screenshot("v116-tv-skip-editor-marked.png")
        compose.onNodeWithTag("mark-save").performScrollTo().assertIsEnabled().performClick(); settle()
        assertEquals(listOf(V116Draft(30_000, 90_000)), saved)
    }

    @Test fun closingTheEditorPreservesDraftAndReturnsFocusToTheToolsButton() {
        val item = MediaEntry("1", "Folge", MediaKind.EPISODE, categoryId = "Serie", seriesId = "1", season = 1, episode = 1)
        val drafts = mutableStateMapOf<V115SegmentKind, V116Draft>()
        var ordinarySeeks = 0; var skipCalls = 0
        compose.setContent {
            val mode = LocalInputModeManager.current; SideEffect { mode.requestInputMode(InputMode.Keyboard) }
            MaterialTheme {
                V115PlayerChrome(item, emptyList(), V115PlaybackUiState(positionMs = 40_000, durationMs = 2_400_000, playWhenReady = false),
                    listOf(V115Segment(V115SegmentKind.INTRO, 30_000, 90_000, "Own", true, 1.0)), true, "", {}, {}, {}, { ordinarySeeks++ }, {}, {}, {},
                    onSkipSegment = { skipCalls++ }, skipTools = { close -> V116SkipEditor(2_400_000, { 40_000L }, emptyList(), drafts, "", true, {}, { _, _, _, _ -> }, {}, {}, close) }
                ) { Box(it) }
            }
        }
        settle()
        compose.onNodeWithTag("vod-skip-intro").performClick(); settle()
        assertEquals(1, skipCalls); assertEquals(0, ordinarySeeks)
        compose.onNodeWithTag("vod-skip-tools").performScrollTo().performClick(); settle()
        compose.onNodeWithTag("mark-start").performScrollTo().performClick(); settle()
        compose.onNodeWithTag("mark-close").performScrollTo().performClick(); settle()
        compose.onNodeWithTag("vod-skip-tools").assertIsFocused()
        compose.onNodeWithTag("vod-skip-tools").performKeyInput { keyDown(Key.Enter); keyUp(Key.Enter) }; settle()
        assertEquals(40_000L, drafts[V115SegmentKind.INTRO]?.start)
        compose.onNodeWithTag("mark-range").assertTextContains("00:40", substring = true)
    }
}
