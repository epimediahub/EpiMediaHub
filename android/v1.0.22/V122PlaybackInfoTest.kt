package de.epimediahub.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.ExperimentalComposeUiApi
import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
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
import org.robolectric.shadows.ShadowDialog
import java.io.File

@OptIn(ExperimentalTestApi::class, ExperimentalComposeUiApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V122PlaybackInfoTest {
    @get:Rule val compose = createComposeRule()
    private val measured = V122PlaybackSnapshot(metadataFps = -1f, measuredFps = 24000f / 1001,
        contentFps = 24000f / 1001, outputHz = 50f, outputWidth = 3840, outputHeight = 2160,
        videoWidth = 1920, videoHeight = 1080, codec = "video/avc", decoder = "OMX.amlogic.avc.decoder.awesome",
        rendered = 1420, dropped = 7, bufferMs = 8240L, state = "Läuft", automatic = true,
        request = "23.976 Hz angefordert")

    private fun settle() { compose.waitForIdle(); compose.mainClock.advanceTimeBy(250L); compose.waitForIdle() }

    @Test fun tvInfoShowsActualOutputInsteadOfClaimingTheRequestedModeSucceeded() {
        var dismissed = 0
        compose.setContent { MaterialTheme { V122PlaybackInfoContent(measured, true, false, { dismissed++ }) } }
        settle()
        compose.onNodeWithText("3840 × 2160 · 50.000 Hz").assertIsDisplayed()
        compose.onNodeWithText("Bildrate und TV-Ausgabe passen nicht zusammen").assertIsDisplayed()
        compose.onNodeWithText("1420 ausgegeben · 7 ausgelassen").assertIsDisplayed()
        compose.onNodeWithTag("playback-info-close").assertIsFocused()
        // Draw the actual dialog with Robolectric's native Canvas. PixelCopy's window
        // redraw callback is not delivered by this headless test environment.
        compose.runOnIdle {
            val root = ShadowDialog.getLatestDialog().window!!.decorView
            val bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888)
            root.draw(Canvas(bitmap))
            val directory = File("build/reports/ui").apply { mkdirs() }
            File(directory, "v122-playback-info-tv.png").outputStream().use {
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
            }
            bitmap.recycle()
        }
        compose.onNodeWithTag("playback-info-close").performKeyInput { keyDown(Key.Enter); keyUp(Key.Enter) }
        assertEquals(1, dismissed)
    }

    @Test @Config(qualifiers = "w640dp-h360dp-land")
    fun closeAndEngineSwitchStayReachableOnSmallTvWindows() {
        var switched = 0
        var dismissed = 0
        compose.setContent { MaterialTheme {
            V122PlaybackInfoContent(measured.copy(speed = 1.25f), true, false, { dismissed++ }, { switched++ })
        } }
        settle()
        compose.onNodeWithTag("playback-info-close").assertIsDisplayed().assertIsFocused()
        compose.onNodeWithTag("playback-info-switch").assertIsDisplayed().performClick()
        assertEquals(1, dismissed)
        assertEquals(1, switched)
    }

    @Test fun compatibilityInfoDoesNotInventMedia3DecoderCounters() {
        compose.setContent { MaterialTheme { V122PlaybackInfoContent(measured, true, true, {}) } }
        settle()
        compose.onNodeWithText("VLC · Audio-Kompatibilität").assertIsDisplayed()
        compose.onNodeWithText("Bilder seit Decoderstart").assertDoesNotExist()
    }

    @Test fun vodSettingsOpenInfoWithoutReplacingTheVideo() {
        compose.setContent { MaterialTheme {
            V115PlayerChrome(MediaEntry("test", "Testfilm", MediaKind.MOVIE), emptyList(),
                V115PlaybackUiState(positionMs = 20_000L, durationMs = 120_000L), emptyList(), true, "",
                onBack = {}, onPlayPause = {}, onSeekBy = {}, onSeekTo = {}, onEpisode = {},
                onTrack = {}, onSubtitlesOff = {}) { Box(it) }
        } }
        settle()
        compose.onNodeWithTag("vod-audio").performClick()
        settle()
        compose.onNodeWithTag("vod-playback-info").performScrollTo().performClick()
        settle()
        compose.onNodeWithTag("playback-info").assertIsDisplayed()
        compose.onNodeWithTag("playback-info-close").performClick()
        settle()
        compose.onNodeWithTag("vod-audio").assertIsFocused()
    }
}
