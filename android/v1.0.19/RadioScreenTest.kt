package de.epimediahub.app.ui

import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.*
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import de.epimediahub.app.data.*
import de.epimediahub.app.radio.RadioPlaybackState
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.LooperMode
import java.io.File

@OptIn(ExperimentalComposeUiApi::class, ExperimentalTestApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class RadioScreenTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var root: View
    private val station = RadioStation("one", "Radio Epi International", "https://radio.example/live", countryCode = "IT", languages = "italian,english", tags = "rock", codec = "MP3", bitrate = 128)
    private val second = station.copy(uuid = "two", name = "Radio Deutschland", countryCode = "DE", languages = "german", streamUrl = "https://radio.example/de")
    private val ui = mutableStateOf(RadioUiState(stations = listOf(station, second)))
    private val playback = mutableStateOf(RadioPlaybackState(station, "Artist – Song", true, ready = true, previous = true, next = true))
    private val selected = mutableListOf<String>()
    private var saved = 0; private var toggles = 0; private var next = 0; private var back = 0; private var stop = 0
    private val accent = Color(0xFF32B9EE)
    private fun screen(tv: Boolean = true) {
        compose.setContent {
            val mode = LocalInputModeManager.current; val view = LocalView.current
            SideEffect { mode.requestInputMode(InputMode.Keyboard); root = view }
            MaterialTheme(colorScheme = darkColorScheme()) {
                Box(Modifier.fillMaxSize().background(Color(0xFF315665))) {
                    RadioContent(ui.value, playback.value, tv, accent, RadioActions(
                        back = { back++ }, mode = { ui.value = ui.value.copy(mode = it) }, query = { ui.value = ui.value.copy(query = it) },
                        play = { selected += it.uuid }, favorite = { saved++; ui.value = ui.value.copy(favorites = listOf(it)) },
                        toggle = { toggles++ }, next = { next++ }, stop = { stop++ }))
                }
            }
        }
        settle()
    }
    private fun settle() { compose.waitForIdle(); compose.mainClock.advanceTimeBy(250); compose.waitForIdle() }
    private fun fits(vararg tags: String) {
        val viewport = compose.onNodeWithTag("radio-screen").getUnclippedBoundsInRoot()
        tags.forEach {
            compose.onNodeWithTag(it).assertIsDisplayed()
            val bounds = compose.onNodeWithTag(it).getUnclippedBoundsInRoot()
            assertTrue("$it must fit: $bounds in $viewport", bounds.left >= viewport.left && bounds.right <= viewport.right && bounds.top >= viewport.top && bounds.bottom <= viewport.bottom)
        }
    }
    private fun capture(name: String): Bitmap {
        lateinit var bitmap: Bitmap
        compose.runOnIdle { bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888); root.draw(Canvas(bitmap)) }
        File("build/reports/ui").mkdirs()
        File("build/reports/ui", name).outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        return bitmap
    }
    private fun iconsHaveContrast(bitmap: Bitmap, vararg tags: String) {
        val density = root.resources.displayMetrics.density
        tags.forEach { tag ->
            val bounds = compose.onNodeWithTag(tag).getUnclippedBoundsInRoot()
            val x = ((bounds.left.value + bounds.right.value) * .5f * density).toInt()
            val y = ((bounds.top.value + bounds.bottom.value) * .5f * density).toInt()
            val radius = (8 * density).toInt()
            var bright = 0
            for (px in x - radius..x + radius) for (py in y - radius..y + radius) {
                val color = bitmap.getPixel(px, py)
                if (android.graphics.Color.red(color) > 200 && android.graphics.Color.green(color) > 200 && android.graphics.Color.blue(color) > 200) bright++
            }
            assertTrue("$tag needs a readable light icon on the dark panel", bright >= 5)
        }
    }
    @Test fun homeRadioIsRoundAndDirectlyBesideThePlaylistShortcut() {
        var opened = 0
        compose.setContent {
            val mode = LocalInputModeManager.current
            SideEffect { mode.requestInputMode(InputMode.Keyboard) }
            MaterialTheme { RadioHomeActions(true, true, accent, {}, { opened++ }) }
        }
        settle()
        val playlist = compose.onNodeWithTag("home-playlist-switch")
        val radio = compose.onNodeWithTag("home-radio")
        val left = playlist.getUnclippedBoundsInRoot(); val right = radio.getUnclippedBoundsInRoot()
        assertEquals(right.right - right.left, right.bottom - right.top)
        assertTrue(right.left > left.right)
        playlist.performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        playlist.performKeyInput { keyDown(Key.DirectionRight); keyUp(Key.DirectionRight) }
        settle(); radio.assertIsFocused()
        radio.performKeyInput { keyDown(Key.Enter); keyUp(Key.Enter) }
        settle(); assertEquals(1, opened)
    }
    @Test fun radioRemainsAvailableWithOnlyOnePlaylist() {
        compose.setContent { MaterialTheme { RadioHomeActions(false, false, accent, {}, {}) } }
        compose.onNodeWithTag("home-radio").assertIsDisplayed()
        compose.onNodeWithTag("home-playlist-switch").assertDoesNotExist()
    }
    @Test fun tvPlayerAndFiltersFitWithoutHorizontalScrolling() {
        screen()
        fits("radio-back", "radio-country", "radio-language", "radio-category", "radio-search", "radio-player", "radio-previous", "radio-play-pause", "radio-next", "radio-stop")
        iconsHaveContrast(capture("radio-tv.png"), "radio-back", "radio-search", "radio-previous", "radio-play-pause", "radio-next", "radio-stop")
        compose.runOnIdle { assertTrue("Radio view must keep the screen awake", root.keepScreenOn) }
    }
    @Test @Config(sdk = [28], qualifiers = "w640dp-h360dp-land") fun mobilePlayerAndFiltersFitInLandscape() {
        screen(false)
        fits("radio-back", "radio-country", "radio-language", "radio-category", "radio-player", "radio-play-pause", "radio-next", "radio-stop")
        iconsHaveContrast(capture("radio-mobile.png"), "radio-back", "radio-search", "radio-play-pause", "radio-next", "radio-stop")
    }
    @Test fun countryPickerChangesCountryWithoutChangingTheLanguage() {
        ui.value = ui.value.copy(query = RadioQuery(language = "english"))
        screen()
        compose.onNodeWithTag("radio-country").performClick(); settle()
        compose.onNodeWithTag("radio-option-IT").performClick(); settle()
        assertEquals("IT", ui.value.query.countryCode); assertEquals("english", ui.value.query.language)
        compose.onNodeWithTag("radio-picker").assertDoesNotExist()
    }
    @Test fun stationSelectionAndFavoriteButtonHaveSeparateActions() {
        screen()
        compose.onNodeWithTag("radio-favorite-one").performClick(); settle()
        assertEquals(1, saved); assertTrue(selected.isEmpty())
        compose.onNodeWithTag("radio-station-one").performClick(); settle()
        assertEquals(listOf("one"), selected)
        compose.onNodeWithTag("radio-mode-favorites").performClick(); settle()
        compose.onNodeWithTag("radio-station-one").assertIsDisplayed()
        compose.onNodeWithTag("radio-station-two").assertDoesNotExist()
    }
    @Test fun remoteMediaKeysAndVisiblePlaybackButtonsWork() {
        screen()
        compose.onNodeWithTag("radio-play-pause").performClick()
        compose.onNodeWithTag("radio-next").performKeyInput { keyDown(Key.MediaNext); keyUp(Key.MediaNext) }
        settle(); assertEquals(1, toggles); assertEquals(1, next)
        compose.onNodeWithTag("radio-back").performClick(); assertEquals(1, stop); assertEquals(1, back)
    }
    @Test fun anUnavailableDirectoryLeavesFavoritesAndRetryAccessible() {
        ui.value = ui.value.copy(stations = emptyList(), error = "Senderverzeichnis gerade nicht erreichbar.", favorites = listOf(station))
        screen()
        compose.onNodeWithTag("radio-retry").assertIsDisplayed()
        compose.onNodeWithTag("radio-mode-favorites").performClick(); settle()
        compose.onNodeWithTag("radio-station-one").assertIsDisplayed()
    }
}
