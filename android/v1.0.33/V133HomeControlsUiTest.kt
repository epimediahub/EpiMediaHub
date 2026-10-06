package de.epimediahub.app.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.semantics.SemanticsActions
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

@OptIn(ExperimentalComposeUiApi::class, ExperimentalTestApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "de-rDE-w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V133HomeControlsUiTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var view: View

    private fun home(tv: Boolean, themeId: String = "napoli__legends", playlists: Int = 2): MainViewModel {
        val app = RuntimeEnvironment.getApplication()
        app.getSharedPreferences("epimediahub",Context.MODE_PRIVATE).edit().clear().putString("menu_lang","de").commit()
        val prefs = PrefsRepository(app); prefs.setFamilySkinsUnlocked(true)
        val profiles = (1..playlists).map {
            PlaylistProfile("v133-$it","IPTV THE BEST","",PlaylistType.XTREAM,"https://provider.invalid","fixture","fixture")
        }
        prefs.savePlaylists(profiles); prefs.activePlaylistId = profiles.first().id
        app.getSharedPreferences("v132_playlist_expiry",Context.MODE_PRIVATE).edit().clear()
            .putString(V132PlaylistExpiryRepository.identity(profiles.first()),JSONObject().put("until",1_800_000_000_000L)
                .put("unlimited",false).put("nextCheck",System.currentTimeMillis()+3_600_000).toString()).commit()
        app.getSharedPreferences("v070_weather",Context.MODE_PRIVATE).edit().clear()
            .putString("language","de").putString("location_key","auto").putLong("time",System.currentTimeMillis())
            .putString("payload","""{"current_condition":[{"temp_C":"18","weatherCode":"116"}],"nearest_area":[{"areaName":[{"value":"Köln"}]}]}""").commit()
        val vm = MainViewModel(app); vm.selectTheme(themeId)
        compose.setContent {
            val localView = LocalView.current; val input = LocalInputModeManager.current
            SideEffect { view = localView; input.requestInputMode(InputMode.Keyboard) }
            val ui by vm.ui.collectAsState(); val theme = ui.themeCatalog!!.themes.getValue(ui.themeId)
            MaterialTheme { ThemeBackdrop(vm.themeRepo(),theme,ui.themeId) { V083HomeScreen(vm,tv,color(theme.accent)) } }
        }
        settle()
        return vm
    }

    private fun settle() { compose.waitForIdle(); compose.mainClock.advanceTimeBy(300); compose.waitForIdle() }
    private fun overlaps(a: Rect,b: Rect): Boolean = a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom

    private fun unobstructed(id: String, hasSwitch: Boolean = true) {
        val toolbar = compose.onNodeWithTag("home-center-toolbar").assertIsDisplayed().fetchSemanticsNode().boundsInRoot
        val tags = if (hasSwitch) listOf("home-radio","home-playlist-switch") else listOf("home-radio")
        for (tag in tags) {
            val button = compose.onNodeWithTag(tag).assertIsDisplayed().fetchSemanticsNode().boundsInRoot
            assertTrue("$tag must fit inside the central toolbar",button.left >= toolbar.left && button.right <= toolbar.right
                && button.top >= toolbar.top && button.bottom <= toolbar.bottom)
            for (index in 0..1) {
                val portrait = compose.onNodeWithTag("portrait-$id-$index").assertIsDisplayed().fetchSemanticsNode().boundsInRoot
                assertFalse("$tag must not cover any part of portrait $id / $index",overlaps(button,portrait))
            }
        }
        compose.onNodeWithText("IPTV THE BEST").assertIsDisplayed()
        compose.onNodeWithTag("playlist-expiry").assertIsDisplayed().assertTextEquals("Gültig bis 15.01.2027")
        for (title in listOf("LIVE TV","FILME","SERIEN","MEDIATHEK","SMARTTUBE","EINSTELLUNGEN"))
            compose.onNodeWithText(title).assertIsDisplayed()
    }

    private fun capture(id: String,layout: String) {
        val app = RuntimeEnvironment.getApplication()
        val assets = V131SkinArtwork.variant(app,id)!!.portraits.map { it.asset }
        compose.waitUntil(timeoutMillis=15_000) {
            val keys = V131SkinArtwork.imageLoader(app).memoryCache?.keys.orEmpty().map { it.key }
            assets.all { asset -> keys.any { it.contains(asset) } }
        }
        compose.waitForIdle()
        lateinit var bitmap: Bitmap
        compose.runOnIdle { bitmap=Bitmap.createBitmap(view.width,view.height,Bitmap.Config.ARGB_8888); view.draw(Canvas(bitmap)) }
        File("build/reports/ui").mkdirs()
        File("build/reports/ui/v133-$layout-$id.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG,100,it) }
        bitmap.recycle()
    }

    @Test fun tvShortcutsDoNotOverlapAnyPlayerOrDriverVariant() {
        val vm = home(true)
        val ids = V131SkinArtwork.load(RuntimeEnvironment.getApplication()).values.flatten()
            .filter { it.portraits.size == 2 }.map { it.id }.distinct()
        assertTrue("All sports teams must be exercised",ids.size >= 250)
        for (id in ids) {
            compose.runOnIdle { vm.selectTheme(id) }; settle(); unobstructed(id)
        }
    }

    @Test fun tvSnapshotsKeepNapoliFootballAndFormulaOneFacesFree() {
        val vm = home(true)
        for (id in listOf("napoli__legends","juventus__players","inter__players","f1_ferrari__players")) {
            compose.runOnIdle { vm.selectTheme(id) }; settle(); unobstructed(id); capture(id,"tv")
        }
    }

    @Test fun remoteControlCanMoveBetweenShortcutsAndReturnToTheTiles() {
        home(true)
        val playlist = compose.onNodeWithTag("home-playlist-switch")
        val radio = compose.onNodeWithTag("home-radio")
        playlist.performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        playlist.performKeyInput { keyDown(Key.DirectionRight); keyUp(Key.DirectionRight) }
        settle(); radio.assertIsFocused()
        radio.performKeyInput { keyDown(Key.DirectionDown); keyUp(Key.DirectionDown) }
        settle(); compose.onNodeWithText("FILME").assertIsFocused()
        compose.onNodeWithText("FILME").performKeyInput { keyDown(Key.DirectionUp); keyUp(Key.DirectionUp) }
        settle(); radio.assertIsFocused()
    }

    @Test @Config(qualifiers="de-rDE-w400dp-h800dp-port")
    fun portraitPhoneShortcutsFitBetweenThePlayers() {
        home(false,"national_tr__players"); unobstructed("national_tr__players"); capture("national_tr__players","phone-portrait")
    }

    @Test @Config(qualifiers="de-rDE-w640dp-h360dp-land")
    fun compactPhoneShortcutsStayAboveTheFacesAndAllTilesRemainVisible() {
        home(false,"inter__players"); unobstructed("inter__players"); capture("inter__players","phone-landscape")
    }

    @Test fun radioRemainsAvailableWithASinglePlaylistAndDoesNotCoverNapoli() {
        home(true,playlists=1); unobstructed("napoli__legends",hasSwitch=false)
        compose.onNodeWithTag("home-playlist-switch").assertDoesNotExist()
    }
}
