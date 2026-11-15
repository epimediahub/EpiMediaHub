package de.epimediahub.app.ui

import android.app.Application
import android.content.Context
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.Screen
import de.epimediahub.app.data.PrefsRepository
import de.epimediahub.app.data.V128AdultContent
import de.epimediahub.app.data.V128ParentalControl
import de.epimediahub.app.data.V128ParentalSettings
import de.epimediahub.app.model.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.LooperMode
import org.robolectric.shadows.ShadowLooper

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@LooperMode(LooperMode.Mode.PAUSED)
class V128ParentalControlTest {
    private lateinit var app: Application
    @Before fun clear() {
        app = RuntimeEnvironment.getApplication()
        app.getSharedPreferences("epi_parental_v128", Context.MODE_PRIVATE).edit().clear().commit()
        app.getSharedPreferences("epimediahub", Context.MODE_PRIVATE).edit().clear().commit()
    }

    @Test fun customerPinKeepsLeadingZeroesAndPersistsWithoutPlaintext() {
        val store = V128ParentalControl(app)
        store.setPin("0042")
        assertTrue(V128ParentalControl(app).verify("0042").accepted)
        assertFalse(store.verify("0043").accepted)
        val saved = app.getSharedPreferences("epi_parental_v128", Context.MODE_PRIVATE)
        assertFalse(saved.all.values.any { it.toString() == "0042" })
        val firstHash = saved.getString("hash", "")
        store.setPin("0042")
        assertNotEquals(firstHash, saved.getString("hash", ""))
        assertFalse(V128ParentalControl.validPin("１２３４"))
        assertFalse(V128ParentalControl.validPin("123"))
        assertFalse(V128ParentalControl.validPin("12345"))
    }

    @Test fun repeatedFailuresSurviveReopeningAndCorrectPinWaitsForCooldown() {
        var now = 1_000_000L
        val store = V128ParentalControl(app) { now }
        store.setPin("3141")
        repeat(5) { assertFalse(store.verify("1111").accepted) }
        assertFalse(V128ParentalControl(app) { now }.verify("3141").accepted)
        now += 30_001
        assertTrue(V128ParentalControl(app) { now }.verify("3141").accepted)
        assertFalse(store.verify("1111").accepted)
        assertTrue(store.verify("3141").accepted)
    }

    @Test fun adultClassificationDistinguishesViewerScoresFromAgeAndInheritsCategory() {
        val settings = V128ParentalSettings(true, true)
        val normal = MediaEntry("1", "Dokumentation", MediaKind.MOVIE, rating = "9.8", ageRating = 12)
        assertFalse(V128AdultContent.restricted(normal, settings))
        assertEquals(-1, V128AdultContent.providerAge(JSONObject().put("rating", "18")))
        assertEquals(18, V128AdultContent.providerAge(JSONObject().put("certification", "FSK 18")))
        assertEquals(18, V128AdultContent.providerAge(JSONObject().put("mpaa", "NC-17")))
        assertTrue(V128AdultContent.providerAdult(JSONObject().put("is_adult", 1)))
        val bound = V128AdultContent.bind(listOf(normal.copy(categoryId = "a")), listOf(MediaCategory("a", "DE | 18+ Erwachsene"))).single()
        assertTrue(V128AdultContent.restricted(bound, settings))
        assertTrue(V128AdultContent.restricted(normal.copy(ageRating = -1), settings.copy(lockUnrated = true)))
        assertFalse(V128AdultContent.restricted(normal.copy(ageRating = 0), settings.copy(lockUnrated = true)))
    }

    private fun vm(menu: Boolean = false): MainViewModel {
        val parental = V128ParentalControl(app)
        parental.setPin("3141"); parental.update(true, menu, false)
        PrefsRepository(app).savePlaylists(listOf(PlaylistProfile("fixture", "Fixture", "", PlaylistType.M3U)))
        return MainViewModel(app)
    }
    private fun protected(kind: MediaKind = MediaKind.MOVIE) = MediaEntry("adult", "Geschützter Inhalt", kind,
        sourceProfileId = "fixture", adult = true, seriesId = if (kind == MediaKind.EPISODE) "series" else "")
    private fun waitUntil(test: () -> Boolean) {
        val limit = System.nanoTime() + 5_000_000_000L
        while (!test() && System.nanoTime() < limit) { ShadowLooper.idleMainLooper(); Thread.sleep(10) }
        ShadowLooper.idleMainLooper(); assertTrue("Asynchronous PIN operation did not complete", test())
    }

    @Test fun contentCannotStartThroughDetailsFavoritesDirectPlayerOrChannelSwitchWithoutPin() {
        val vm = vm()
        val movie = protected()
        vm.navigate(Screen.Details(movie)); assertNotNull(vm.ui.value.pinPrompt); assertEquals(Screen.Home, vm.ui.value.screen)
        vm.cancelParentalPin()
        vm.play(movie); assertNotNull(vm.ui.value.pinPrompt); assertEquals(Screen.Home, vm.ui.value.screen)
        assertTrue(PrefsRepository(app).loadRecentlyWatched("fixture").isEmpty())
        vm.cancelParentalPin()
        vm.navigate(Screen.Player(movie)); assertNotNull(vm.ui.value.pinPrompt); assertEquals(Screen.Home, vm.ui.value.screen)
        vm.cancelParentalPin()
        val live = protected(MediaKind.LIVE)
        vm.switchLiveChannel(live, listOf(live)); assertNotNull(vm.ui.value.pinPrompt); assertEquals(Screen.Home, vm.ui.value.screen)
    }

    @Test fun approvedContentStartsAndBackgroundingRequiresPinAgain() {
        val vm = vm()
        vm.play(protected()); vm.submitParentalPin("3141")
        waitUntil { vm.ui.value.screen is Screen.Player }
        assertFalse(vm.isContentLocked(protected()))
        vm.lockParentalSession()
        assertEquals(Screen.Home, vm.ui.value.screen)
        assertTrue(vm.isContentLocked(protected()))
        vm.play(protected()); assertNotNull(vm.ui.value.pinPrompt)
    }

    @Test fun cancelledVerificationNeverStartsProtectedPlayback() {
        val vm = vm()
        vm.play(protected()); vm.submitParentalPin("3141"); vm.cancelParentalPin()
        repeat(80) { ShadowLooper.idleMainLooper(); Thread.sleep(10) }
        assertEquals(Screen.Home, vm.ui.value.screen)
        assertNull(vm.ui.value.pinPrompt)
        assertTrue(vm.ui.value.parentalGranted.isEmpty())
    }

    @Test fun settingsCannotDisableProtectionUntilAuthenticatedAndReentryAsksAgain() {
        val vm = vm()
        vm.navigate(Screen.ParentalSettings)
        vm.updateParentalSettings(adult = false)
        assertTrue(vm.ui.value.parentalSettings.lockAdult)
        vm.submitParentalPin("3141"); waitUntil { vm.ui.value.screen == Screen.ParentalSettings }
        vm.updateParentalSettings(adult = false); assertFalse(vm.ui.value.parentalSettings.lockAdult)
        vm.back(); vm.navigate(Screen.ParentalSettings)
        assertNotNull(vm.ui.value.pinPrompt)
    }

    @Test fun menuAndAutomaticEpisodeTransitionsUseTheSamePin() {
        val vm = vm(menu = true)
        vm.requestMenuUnlock(); vm.submitParentalPin("3141")
        waitUntil { vm.ui.value.parentalMenuUnlocked }
        val first = MediaEntry("first", "Erste Folge", MediaKind.EPISODE, seriesId = "series", sourceProfileId = "fixture", episode = 1)
        val next = protected(MediaKind.EPISODE).copy(episode = 2)
        vm.skipEpisode(first, listOf(first, next), 1)
        assertNotNull(vm.ui.value.pinPrompt)
        assertEquals(Screen.Home, vm.ui.value.screen)
        vm.cancelParentalPin()
        vm.selectV115Episode(first, next, listOf(first, next)); assertNotNull(vm.ui.value.pinPrompt)
        vm.lockParentalSession(); assertFalse(vm.ui.value.parentalMenuUnlocked)
    }
}
