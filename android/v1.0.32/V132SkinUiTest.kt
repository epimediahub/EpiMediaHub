package de.epimediahub.app.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.data.PrefsRepository
import de.epimediahub.app.data.V132PlaylistExpiryRepository
import de.epimediahub.app.model.PlaylistProfile
import de.epimediahub.app.model.PlaylistType
import org.json.JSONObject
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

@OptIn(ExperimentalTestApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "de-rDE-w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V132SkinUiTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var view: View
    private fun fixture(): MainViewModel {
        val app = RuntimeEnvironment.getApplication()
        app.getSharedPreferences("epimediahub", Context.MODE_PRIVATE).edit().clear().putString("menu_lang", "de").commit()
        val prefs = PrefsRepository(app); prefs.setFamilySkinsUnlocked(true)
        val profile = PlaylistProfile("v132-fixture", "IPTV THE BEST", "", PlaylistType.XTREAM, "https://provider.invalid", "fixture", "fixture")
        prefs.savePlaylists(listOf(profile))
        app.getSharedPreferences("v132_playlist_expiry", Context.MODE_PRIVATE).edit().clear()
            .putString(V132PlaylistExpiryRepository.identity(profile), JSONObject().put("until", 1_800_000_000_000L)
                .put("unlimited", false).put("nextCheck", System.currentTimeMillis()+3_600_000).toString()).commit()
        app.getSharedPreferences("v070_weather", Context.MODE_PRIVATE).edit().clear()
            .putString("language", "de").putString("location_key", "auto").putLong("time", System.currentTimeMillis())
            .putString("payload", """{"current_condition":[{"temp_C":"18","weatherCode":"116"}],"nearest_area":[{"areaName":[{"value":"Köln"}]}]}""").commit()
        return MainViewModel(app)
    }
    private fun home(vm: MainViewModel, isTv: Boolean) {
        compose.setContent {
            val local = LocalView.current; SideEffect { view = local }
            val ui by vm.ui.collectAsState(); val theme = ui.themeCatalog!!.themes.getValue(ui.themeId)
            MaterialTheme { ThemeBackdrop(vm.themeRepo(), theme, ui.themeId) { V083HomeScreen(vm, isTv, color(theme.accent)) } }
        }
    }
    private fun settle(id: String) {
        compose.waitForIdle(); compose.mainClock.advanceTimeBy(500); compose.waitForIdle()
        val app = RuntimeEnvironment.getApplication(); val targets = V131SkinArtwork.variant(app, id)!!.portraits.map { it.asset }
        compose.waitUntil(timeoutMillis = 15_000) {
            val keys = V131SkinArtwork.imageLoader(app).memoryCache?.keys.orEmpty().map { it.key }
            targets.all { asset -> keys.any { it.contains(asset) } }
        }
        compose.waitForIdle()
    }
    private fun verifyAndCapture(id: String, layout: String) {
        for (title in listOf("LIVE TV", "FILME", "SERIEN", "MEDIATHEK", "SMARTTUBE", "EINSTELLUNGEN"))
            compose.onNodeWithText(title).assertIsDisplayed()
        compose.onNodeWithTag("playlist-expiry").assertIsDisplayed().assertTextEquals("Gültig bis 15.01.2027")
        val tile = compose.onNodeWithText("LIVE TV").fetchSemanticsNode().boundsInRoot
        for (index in 0..1) {
            val bounds = compose.onNodeWithTag("portrait-$id-$index").assertIsDisplayed().fetchSemanticsNode().boundsInRoot
            assertTrue("Face area above tiles: $id / $index / $layout", bounds.top+bounds.height*.23f < tile.top)
            val window = V131SkinArtwork.variant(RuntimeEnvironment.getApplication(), id)!!.portraits[index].window
            assertEquals("Only the reviewed upper body is visible", window.aspectRatio, bounds.width/bounds.height, .03f)
        }
        lateinit var bitmap: Bitmap
        compose.runOnIdle { bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888); view.draw(Canvas(bitmap)) }
        File("build/reports/ui").mkdirs()
        File("build/reports/ui/v132-$layout-$id.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) }
        bitmap.recycle()
    }
    @Test fun tvSkinsKeepFacesAboveAllSixTilesAndShowExpiry() {
        val vm = fixture(); home(vm,true)
        for (id in listOf("juventus__players", "inter__players", "national_it__players", "barcelona__legends", "real_madrid__legends",
            "atletico__players", "national_tr__players", "f1_mercedes__legends", "f1_aston_martin__legends", "f1_mclaren__legends",
            "f1_alpine__legends", "f1_racing_bulls__legends", "f1_audi__legends", "nba_los_angeles_lakers__legends")) {
            compose.runOnIdle { vm.selectTheme(id) }; settle(id); verifyAndCapture(id,"tv")
        }
    }
    @Test @Config(qualifiers = "de-rDE-w400dp-h800dp-port")
    fun portraitPhoneShowsArdaAndExpiryWithoutSourceBleed() {
        val vm = fixture(); vm.selectTheme("national_tr__players"); home(vm,false)
        settle("national_tr__players"); verifyAndCapture("national_tr__players","phone-portrait")
    }
    @Test @Config(qualifiers = "de-rDE-w640dp-h360dp-land")
    fun landscapePhoneKeepsAllSixTilesAndTheExpiryVisible() {
        val vm = fixture(); vm.selectTheme("inter__players"); home(vm,false)
        settle("inter__players"); verifyAndCapture("inter__players","phone-landscape")
    }
}
