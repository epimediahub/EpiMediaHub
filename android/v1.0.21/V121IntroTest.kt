package de.epimediahub.app.ui

import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.LooperMode
import java.io.File

@OptIn(ExperimentalTestApi::class, ExperimentalComposeUiApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V121IntroTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var root: View
    private val elapsed = mutableLongStateOf(700L)
    private var skipped = 0

    private fun screen(tv: Boolean = true) {
        compose.setContent {
            val input = LocalInputModeManager.current
            val view = LocalView.current
            SideEffect { root = view; input.requestInputMode(InputMode.Keyboard) }
            MaterialTheme { V121IntroContent(elapsed.longValue, Color(0xFF32B9EE), tv) { skipped++ } }
        }
        compose.waitForIdle()
    }

    private fun at(time: Long) { compose.runOnIdle { elapsed.longValue = time }; compose.waitForIdle() }

    private fun capture(name: String) {
        compose.runOnIdle {
            val bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888)
            root.draw(Canvas(bitmap))
            val directory = File("build/reports/ui").apply { mkdirs() }
            File(directory, name).outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        }
    }

    /** Produce a review video from the actual Compose scene, using its shipped timeline. */
    @Test fun renderIntroPreviewFrames() {
        screen()
        val directory = File("build/intro-preview/frames").apply { mkdirs() }
        val count = (V121IntroTimeline.DURATION_MS * 60 / 1000).toInt()
        for (frame in 0 until count) {
            at(frame * 1000L / 60L)
            compose.runOnIdle {
                val bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888)
                root.draw(Canvas(bitmap))
                File(directory, "frame-%04d.png".format(frame)).outputStream().use {
                    bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
                }
                bitmap.recycle()
            }
        }
        assertEquals(348, directory.listFiles { _, name -> name.endsWith(".png") }!!.size)
    }

    @Test fun englishWorldThenOneAppThenOriginalLogoAppearInOrder() {
        screen()
        compose.onNodeWithText("The whole world\nof multimedia", useUnmergedTree = true).assertIsDisplayed()
        compose.onNodeWithTag("intro-one-app", useUnmergedTree = true).assertDoesNotExist()
        compose.onNodeWithTag("intro-logo", useUnmergedTree = true).assertDoesNotExist()
        capture("v121-intro-world-tv.png")
        at(2500)
        compose.onNodeWithText("One App", useUnmergedTree = true).assertIsDisplayed()
        compose.onNodeWithTag("intro-world", useUnmergedTree = true).assertDoesNotExist()
        capture("v121-intro-one-app-tv.png")
        at(4400)
        compose.onNodeWithContentDescription("EpiMediaHub", useUnmergedTree = true).assertIsDisplayed()
        compose.onNodeWithTag("intro-one-app", useUnmergedTree = true).assertDoesNotExist()
        capture("v121-intro-logo-tv.png")
    }

    @Test fun okSkipsButVolumeDoesNotDismissTheIntro() {
        screen()
        compose.onNodeWithTag("cinematic-intro").performKeyInput { keyDown(Key.VolumeUp); keyUp(Key.VolumeUp) }
        assertEquals(0, skipped)
        compose.onNodeWithTag("cinematic-intro").performKeyInput { keyDown(Key.Enter); keyUp(Key.Enter) }
        assertEquals(1, skipped)
    }

    @Test @Config(qualifiers = "w640dp-h360dp-land")
    fun phoneTextAndLogoStayInsideTheViewportAndTapSkips() {
        screen(false)
        val viewport = compose.onNodeWithTag("cinematic-intro").getUnclippedBoundsInRoot()
        for ((time, tag) in listOf(460L to "intro-world", 2380L to "intro-one-app", 4500L to "intro-logo")) {
            at(time)
            val bounds = compose.onNodeWithTag(tag, useUnmergedTree = true).getUnclippedBoundsInRoot()
            assertTrue(bounds.left >= viewport.left && bounds.right <= viewport.right)
            assertTrue(bounds.top >= viewport.top && bounds.bottom <= viewport.bottom)
        }
        capture("v121-intro-logo-phone.png")
        compose.onNodeWithTag("cinematic-intro").performTouchInput { click() }
        assertEquals(1, skipped)
    }

    @Test fun pulsesAreSubtleAndScenesDoNotOverlap() {
        for (ms in 0L..V121IntroTimeline.DURATION_MS step 10L) {
            val alphas = listOf(V121IntroTimeline.worldAlpha(ms), V121IntroTimeline.appAlpha(ms), V121IntroTimeline.logoAlpha(ms))
            assertTrue(alphas.all { it in 0f..1f })
            assertTrue(alphas.count { it > 0f } <= 1)
            assertTrue(V121IntroTimeline.textScale(ms) in 1f..1.025f)
        }
        assertEquals(0f, V121IntroTimeline.logoAlpha(V121IntroTimeline.DURATION_MS), .0001f)
    }
}
