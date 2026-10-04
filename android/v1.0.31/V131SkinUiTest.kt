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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import de.epimediahub.app.MainViewModel
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
@Config(sdk = [28], qualifiers = "de-rDE-w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V131SkinUiTest {
    @get:Rule val compose = createComposeRule()
    private fun vm(): MainViewModel {
        val app = RuntimeEnvironment.getApplication()
        app.getSharedPreferences("epimediahub", Context.MODE_PRIVATE).edit().clear().putString("menu_lang", "de").commit()
        val prefs = PrefsRepository(app); prefs.setFamilySkinsUnlocked(true)
        prefs.savePlaylists(listOf(PlaylistProfile("fixture", "EpiMediaHub", "", PlaylistType.M3U)))
        app.getSharedPreferences("v070_weather", Context.MODE_PRIVATE).edit().clear()
            .putString("language", "de").putString("location_key", "auto").putLong("time", System.currentTimeMillis())
            .putString("payload", """{"current_condition":[{"temp_C":"18","weatherCode":"116"}],"nearest_area":[{"areaName":[{"value":"Köln"}]}]}""").commit()
        return MainViewModel(app)
    }
    private fun settle() { compose.waitForIdle(); compose.mainClock.advanceTimeBy(500); compose.waitForIdle() }
    private fun capture(view: View, name: String) {
        lateinit var bitmap: Bitmap
        compose.runOnIdle { bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888); view.draw(Canvas(bitmap)) }
        File("build/reports/ui").mkdirs()
        File("build/reports/ui/$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }
    @Test fun remoteMovesSidewaysWithinTeamAndOkAppliesWithoutChangingTheTeam() {
        val vm = vm(); val team = vm.ui.value.themeCatalog!!.themes.getValue("f1_ferrari")
        V111MenuMemory.remember("themes-preview:formula_1", 0, team.id)
        lateinit var view: View
        compose.setContent {
            val input = LocalInputModeManager.current; val local = LocalView.current
            SideEffect { input.requestInputMode(InputMode.Keyboard); view = local }
            MaterialTheme { Column(Modifier.fillMaxSize().padding(24.dp)) { V131TeamCarousel(vm, team, vm.ui.collectAsState().value.themeId, true) } }
        }
        settle()
        compose.onNodeWithTag("skin-f1_ferrari").assertIsFocused().performKeyInput { pressKey(Key.DirectionRight) }
        settle(); compose.onNodeWithTag("skin-f1_ferrari__players").assertIsFocused()
            .performKeyInput { pressKey(Key.DirectionRight) }
        settle(); compose.onNodeWithTag("skin-f1_ferrari__legends").assertIsFocused()
        capture(view, "v131-team-carousel-tv")
        compose.onNodeWithTag("skin-f1_ferrari__legends").performKeyInput { pressKey(Key.Enter) }
        settle(); assertEquals("f1_ferrari__legends", vm.ui.value.themeId)
        compose.onNodeWithTag("skin-f1_ferrari__legends").performKeyInput { pressKey(Key.DirectionLeft) }
        settle(); compose.onNodeWithTag("skin-f1_ferrari__players").assertIsFocused()
    }
    @Test @Config(qualifiers = "de-rDE-w400dp-h800dp-port")
    fun phoneSwipeRevealsLegendsAndTouchApplies() {
        val vm = vm(); val team = vm.ui.value.themeCatalog!!.themes.getValue("nba_los_angeles_lakers")
        compose.setContent { MaterialTheme { Column { V131TeamCarousel(vm, team, vm.ui.collectAsState().value.themeId, false) } } }
        settle(); compose.onNodeWithTag("variants-" + team.id).performTouchInput { swipeLeft() }
        settle(); compose.onNodeWithTag("variants-" + team.id).performScrollToNode(hasTestTag("skin-" + team.id + "__legends"))
        compose.onNodeWithTag("skin-" + team.id + "__legends").assertIsDisplayed().performClick()
        settle(); assertEquals(team.id + "__legends", vm.ui.value.themeId)
    }
    @Test fun tvHomeRetainsSixReadableTilesWithNewVariants() {
        val vm = vm(); lateinit var view: View
        compose.setContent {
            val local = LocalView.current; SideEffect { view = local }
            val ui by vm.ui.collectAsState(); val theme = ui.themeCatalog!!.themes.getValue(ui.themeId)
            MaterialTheme { ThemeBackdrop(vm.themeRepo(), theme, ui.themeId) { V083HomeScreen(vm, true, color(theme.accent)) } }
        }
        for (id in listOf("f1_ferrari__players", "juventus__legends", "nba_los_angeles_lakers__legends", "nfl_kansas_city_chiefs__players")) {
            compose.runOnIdle { vm.selectTheme(id) }; settle()
            for (title in listOf("LIVE TV", "FILME", "SERIEN", "MEDIATHEK", "SMARTTUBE", "EINSTELLUNGEN")) compose.onNodeWithText(title).assertIsDisplayed()
            capture(view, "v131-home-" + id)
        }
    }
    @Test @Config(qualifiers = "de-rDE-w640dp-h360dp-land")
    fun landscapePhoneKeepsAllSixHomeTilesVisible() {
        val vm = vm()
        compose.setContent { MaterialTheme { V083HomeScreen(vm, false, Color.Cyan) } }
        settle()
        for (title in listOf("LIVE TV", "FILME", "SERIEN", "MEDIATHEK", "SMARTTUBE", "EINSTELLUNGEN")) compose.onNodeWithText(title).assertIsDisplayed()
    }
}
