package de.epimediahub.app.data

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.IOException

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class RadioRepositoryTest {
    @get:Rule val temp = TemporaryFolder()
    private val hosts = listOf("a.api.radio-browser.info", "b.api.radio-browser.info")
    @Test fun failedOrMalformedMirrorFallsBackToTheNext() = runBlocking {
        val urls = mutableListOf<String>()
        val client = RadioBrowserClient(temp.newFolder(), RadioTransport { url ->
            urls += url; if (url.contains("//a.")) "invalid-json" else "[]"
        }, hosts)
        assertEquals(0, client.request("/json/countrycodes").json.size)
        assertEquals(2, urls.size)
        assertTrue(urls.last().contains("//b."))
    }
    @Test fun cacheAvoidsNetworkAndSurvivesTemporaryOutage() = runBlocking {
        var calls = 0; var now = System.currentTimeMillis(); var fail = false
        val client = RadioBrowserClient(temp.newFolder(), RadioTransport {
            calls++; if (fail) throw IOException("offline") else "[{\"name\":\"DE\",\"stationcount\":12}]"
        }, hosts) { now }
        assertFalse(client.request("/json/countrycodes").cached)
        assertTrue(client.request("/json/countrycodes").cached)
        assertEquals(1, calls)
        now += 3_600_000; fail = true
        assertTrue(client.request("/json/countrycodes").cached)
        assertEquals(3, calls)
    }
    @Test fun cancellationDoesNotRetryAnotherMirror() = runBlocking {
        var calls = 0
        val client = RadioBrowserClient(temp.newFolder(), RadioTransport { calls++; throw CancellationException("cancelled") }, hosts)
        try { client.request("/json/countrycodes"); fail("Expected cancellation") } catch (_: CancellationException) { }
        assertEquals(1, calls)
    }
    @Test fun genreAliasesUseOrQueriesAndKeepCountryAndLanguageFilters() = runBlocking {
        val urls = mutableListOf<String>()
        val client = RadioBrowserClient(temp.newFolder(), RadioTransport { url ->
            synchronized(urls) { urls += url }
            val tag = if (url.contains("tag=metal")) "metal" else "rock"
            """[{"stationuuid":"$tag-123","name":"$tag Radio","url_resolved":"https://radio.example/$tag","lastcheckok":1,"countrycode":"IT","language":"english","tags":"$tag"}]"""
        }, listOf(hosts.first()))
        val page = client.stations(RadioQuery(countryCode = "IT", language = "english", categoryId = "rock"), page = 2)
        assertEquals(2, page.stations.size)
        assertEquals(2, urls.size)
        assertTrue(urls.all { it.contains("countrycode=IT") && it.contains("language=english") && it.contains("offset=60") && it.contains("limit=30") })
        assertFalse(page.hasMore)
    }
    @Test fun oneUnavailableAliasDoesNotDiscardOtherStations() = runBlocking {
        val client = RadioBrowserClient(temp.newFolder(), RadioTransport {
            if (it.contains("tag=metal")) throw IOException("unavailable")
            """[{"stationuuid":"rock-123","name":"Rock","url_resolved":"https://radio.example/rock","lastcheckok":1}]"""
        }, listOf(hosts.first()))
        val result = client.stations(RadioQuery(categoryId = "rock"))
        assertEquals(1, result.stations.size); assertTrue(result.partial)
    }
    @Test fun favoritesAndRecentStationsPersistAcrossRepositoryInstances() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        context.getSharedPreferences("epimediahub-radio", Context.MODE_PRIVATE).edit().clear().commit()
        val station = RadioStation("station", "Radio Epi", "https://radio.example/live")
        RadioPreferences(context).apply { saveFavorites(listOf(station)); rememberStation(station) }
        val restored = RadioPreferences(context)
        assertEquals(listOf(station), restored.read("favorites"))
        restored.rememberStation(station)
        assertEquals(listOf(station), restored.read("recent"))
    }
    @Test fun everyAvailableCountryIsShownWithGermanLabelsAndQuickCountriesFirst() = runBlocking {
        val client = RadioBrowserClient(temp.newFolder(), RadioTransport {
            """[{"name":"US","stationcount":"80"},{"name":"JP","stationcount":30},{"name":"DE","stationcount":100},{"name":"IT","stationcount":90}]"""
        }, listOf(hosts.first()))
        val countries = client.countries()
        assertEquals(listOf("DE", "IT", "JP", "US"), countries.map { it.id })
        assertEquals("Japan", countries[2].label)
    }
}
