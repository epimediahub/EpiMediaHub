package de.epimediahub.app.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.Screen
import de.epimediahub.app.data.PrefsRepository
import de.epimediahub.app.model.*
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.LooperMode
import java.io.File

@OptIn(ExperimentalTestApi::class, ExperimentalComposeUiApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V129UiRegressionTest {
    @get:Rule val compose = createComposeRule()
    private fun settle() { compose.waitForIdle(); compose.mainClock.advanceTimeBy(300); compose.waitForIdle() }
    private fun capture(view: View, name: String) {
        lateinit var bitmap: Bitmap
        compose.runOnIdle { bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888); view.draw(Canvas(bitmap)) }
        File("build/reports/ui").mkdirs()
        File("build/reports/ui/$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }
    @Test fun remoteCanReachAdultToggleWithoutPinAndOpenSetup() {
        val app = RuntimeEnvironment.getApplication()
        app.getSharedPreferences("epi_parental_v128", Context.MODE_PRIVATE).edit().clear().commit()
        app.getSharedPreferences("epimediahub", Context.MODE_PRIVATE).edit().clear().commit()
        PrefsRepository(app).savePlaylists(listOf(PlaylistProfile("fixture", "Fixture", "", PlaylistType.M3U)))
        val vm = MainViewModel(app); vm.navigate(Screen.ParentalSettings)
        compose.setContent {
            val input = LocalInputModeManager.current
            SideEffect { input.requestInputMode(InputMode.Keyboard) }
            MaterialTheme { V128ParentalSettingsScreen(vm, Color.Cyan) }
        }
        settle()
        compose.onNodeWithTag("parental-setup").assertIsFocused().performKeyInput { pressKey(Key.DirectionDown) }
        settle()
        compose.onNodeWithTag("parental-toggle-18+-Inhalte sperren").assertIsFocused().assertIsEnabled()
            .performKeyInput { pressKey(Key.Enter) }
        settle()
        compose.onNodeWithText("Neue PIN festlegen").assertIsDisplayed()
        compose.onNodeWithTag("pin-key-1").assertIsFocused()
    }
    @Test fun chooserIsReachableByRemoteAndKidsHasAutomaticCategories() {
        var picked = ""
        lateinit var view: View
        compose.setContent {
            val local = LocalView.current
            val input = LocalInputModeManager.current
            SideEffect { view = local; input.requestInputMode(InputMode.Keyboard) }
            MaterialTheme { V129ModeChooser(true, { picked = "normal" }, { picked = "kids" }, {}) }
        }
        settle()
        compose.onNodeWithTag("smarttube-normal").assertIsFocused().performKeyInput { pressKey(Key.DirectionDown) }
        settle()
        compose.onNodeWithTag("smarttube-kids").assertIsFocused()
        capture(view, "v129-smarttube-chooser-tv")
        compose.onNodeWithTag("smarttube-kids").performKeyInput { pressKey(Key.Enter) }
        settle(); assertEquals("kids", picked)
    }
    @Test fun automaticKidsFeedHasThumbnailsCategoriesAndNoGeneralSearch() {
        lateinit var view: View
        var parents = false
        val rows = listOf(V100SmartTubeRow("Serien", listOf(V100SmartTubeVideo("aaaaaaaaaaa", "Abenteuer im Sternenland", "", "", "", 60000, false))),
            V100SmartTubeRow("Lernen", listOf(V100SmartTubeVideo("bbbbbbbbbbb", "Die Welt der Tiere", "", "", "", 60000, false))))
        compose.setContent {
            val local = LocalView.current
            SideEffect { view = local }
            MaterialTheme { V129KidsScreen(true, { parents = true }, load = { Result.success(rows) }) }
        }
        settle()
        compose.onNodeWithText("SmartTube KIDS").assertIsDisplayed()
        compose.onNodeWithTag("kids-video-aaaaaaaaaaa").assertIsDisplayed()
        compose.onNodeWithText("Anmelden").assertDoesNotExist()
        compose.onNodeWithText("Suche").assertDoesNotExist()
        capture(view, "v129-kids-tv")
        compose.onNodeWithTag("kids-parents").performClick(); settle(); assertTrue(parents)
    }
    @Test @Config(qualifiers = "w640dp-h360dp-land")
    fun failedKidsCatalogueOffersRetryWithoutNormalContent() {
        var requests = 0
        compose.setContent { MaterialTheme { V129KidsScreen(false, {}, load = { requests++; Result.failure(IllegalStateException("offline")) }) } }
        settle()
        compose.onNodeWithText("Noch einmal versuchen").assertIsDisplayed().performClick(); settle()
        assertEquals(2, requests)
        compose.onNodeWithText("Anmelden").assertDoesNotExist()
        compose.onNodeWithText("Suche").assertDoesNotExist()
    }
}
