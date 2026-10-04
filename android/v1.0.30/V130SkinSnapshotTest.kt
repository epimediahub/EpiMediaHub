package de.epimediahub.app.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.data.PrefsRepository
import de.epimediahub.app.model.PlaylistProfile
import de.epimediahub.app.model.PlaylistType
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.LooperMode
import java.io.File

/** Render the shipping skin components for the requested design review. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "de-rDE-w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V130SkinSnapshotTest {
    @get:Rule val compose = createComposeRule()

    @Test fun captureCurrentStandardFerrariAndJuventusSkins() {
        val app = RuntimeEnvironment.getApplication()
        app.getSharedPreferences("epimediahub", Context.MODE_PRIVATE).edit().clear().putString("menu_lang", "de").commit()
        val prefs = PrefsRepository(app)
        prefs.savePlaylists(listOf(PlaylistProfile("fixture", "EpiMediaHub", "", PlaylistType.M3U)))
        prefs.setFamilySkinsUnlocked(true)
        // Fixed local weather prevents network traffic during this visual review.
        app.getSharedPreferences("v070_weather", Context.MODE_PRIVATE).edit().clear()
            .putString("language", "de").putString("location_key", "auto")
            .putLong("time", System.currentTimeMillis())
            .putString("payload", """{"current_condition":[{"temp_C":"18","weatherCode":"116"}],"nearest_area":[{"areaName":[{"value":"Köln"}]}]}""").commit()
        val vm = MainViewModel(app)
        lateinit var view: View
        compose.setContent {
            val local = LocalView.current
            SideEffect { view = local }
            val ui by vm.ui.collectAsState()
            val theme = ui.themeCatalog!!.themes.getValue(ui.themeId)
            val accent = color(theme.accent)
            MaterialTheme(colorScheme = darkColorScheme(primary = accent)) {
                ThemeBackdrop(vm.themeRepo(), theme, ui.themeId) { V083HomeScreen(vm, true, accent) }
            }
        }
        for (id in listOf("default", "f1_ferrari", "juventus", "ferrari")) {
            compose.runOnIdle { vm.selectTheme(id) }
            compose.waitForIdle(); compose.mainClock.advanceTimeBy(350); compose.waitForIdle()
            compose.onNodeWithText("LIVE TV").assertIsDisplayed()
            lateinit var bitmap: Bitmap
            compose.runOnIdle {
                check(vm.ui.value.themeId == id)
                bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
                view.draw(Canvas(bitmap))
            }
            File("build/reports/ui").mkdirs()
            File("build/reports/ui/v130-current-skin-$id.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            bitmap.recycle()
        }
    }
}
