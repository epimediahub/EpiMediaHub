package de.epimediahub.app.ui

import android.app.Application
import android.content.Context
import com.sun.net.httpserver.HttpServer
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.Screen
import de.epimediahub.app.data.PrefsRepository
import de.epimediahub.app.data.V128ParentalControl
import de.epimediahub.app.model.*
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.LooperMode
import org.robolectric.shadows.ShadowLooper
import java.net.InetSocketAddress
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@LooperMode(LooperMode.Mode.PAUSED)
class V128CatalogueLoadingTest {
    @Test fun favoritesAndLivePlaybackReadAdultCategoryFlagsBeforeAnyLibraryWasOpened() {
        val app = RuntimeEnvironment.getApplication<Application>()
        app.getSharedPreferences("epi_parental_v128", Context.MODE_PRIVATE).edit().clear().commit()
        app.getSharedPreferences("epimediahub", Context.MODE_PRIVATE).edit().clear().commit()
        V128ParentalControl(app).apply { setPin("0042"); update(true, false, false) }
        val threads = Executors.newCachedThreadPool()
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.executor = threads
        server.createContext("/player_api.php") { exchange ->
            val action = exchange.requestURI.rawQuery.orEmpty().substringAfter("action=", "").substringBefore('&')
            val body = if (action.endsWith("_categories"))
                """[{"category_id":"42","category_name":"Premium","is_adult":1}]"""
            else """{"info":{"age_rating":12},"movie_data":{"category_id":"42"}}"""
            val bytes = body.toByteArray()
            exchange.sendResponseHeaders(200, bytes.size.toLong())
            exchange.responseBody.use { it.write(bytes) }
        }
        server.start()
        try {
            val url = "http://127.0.0.1:${server.address.port}"
            PrefsRepository(app).savePlaylists(listOf(PlaylistProfile("protected", "Fixture", url, PlaylistType.XTREAM, url, "fixture", "fixture")))
            listOf(MediaKind.MOVIE, MediaKind.LIVE).forEach { kind ->
                val vm = MainViewModel(app)
                val entry = MediaEntry("18", "Neutraler Titel", kind, categoryId = "42", sourceProfileId = "protected")
                vm.play(entry)
                val limit = System.nanoTime() + 8_000_000_000L
                while (vm.ui.value.pinPrompt == null && System.nanoTime() < limit) { ShadowLooper.idleMainLooper(); Thread.sleep(10) }
                ShadowLooper.idleMainLooper()
                assertNotNull("Category-only adult flags must protect $kind on a cold start", vm.ui.value.pinPrompt)
                assertEquals(Screen.Home, vm.ui.value.screen)
                assertTrue(vm.isContentLocked(entry))
                assertTrue(PrefsRepository(app).loadRecentlyWatched("protected").isEmpty())
                vm.cancelParentalPin()
            }
        } finally { server.stop(0); threads.shutdownNow() }
    }

    @Test fun categoryAndLibraryMetadataOverlapAndWarmReentryDoesNotDownloadAgain() {
        val app = RuntimeEnvironment.getApplication<Application>()
        app.getSharedPreferences("epi_parental_v128", Context.MODE_PRIVATE).edit().clear().commit()
        app.getSharedPreferences("epimediahub", Context.MODE_PRIVATE).edit().clear().commit()
        val both = CountDownLatch(2)
        val overlapped = AtomicBoolean(true)
        val requests = AtomicInteger()
        val threads = Executors.newCachedThreadPool()
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.executor = threads
        server.createContext("/player_api.php") { exchange ->
            requests.incrementAndGet()
            val action = exchange.requestURI.rawQuery.orEmpty().substringAfter("action=", "").substringBefore('&')
            if (action in setOf("get_vod_categories", "get_vod_streams")) {
                both.countDown(); if (!both.await(2, TimeUnit.SECONDS)) overlapped.set(false)
            }
            val json = when(action) {
                "get_vod_categories" -> """[{"category_id":"a","category_name":"Filme"},{"category_id":"adult","category_name":"18+ Erwachsene"}]"""
                "get_vod_streams" -> """[{"stream_id":"1","name":"Normaler Film","category_id":"a","container_extension":"mp4"},{"stream_id":"2","name":"Geschützter Film","category_id":"adult","container_extension":"mp4"}]"""
                else -> "{}"
            }
            val data = json.toByteArray()
            exchange.sendResponseHeaders(200, data.size.toLong())
            exchange.responseBody.use { it.write(data) }
        }
        server.start()
        try {
            val url = "http://127.0.0.1:${server.address.port}"
            PrefsRepository(app).savePlaylists(listOf(PlaylistProfile("parallel", "Fixture", url, PlaylistType.XTREAM, url, "fixture", "fixture")))
            val vm = MainViewModel(app)
            vm.openLibrary(MediaKind.MOVIE)
            val limit = System.nanoTime() + 8_000_000_000L
            while (vm.ui.value.loading && System.nanoTime() < limit) { ShadowLooper.idleMainLooper(); Thread.sleep(10) }
            ShadowLooper.idleMainLooper()
            assertFalse(vm.ui.value.error, vm.ui.value.loading)
            assertTrue("The two metadata requests must run concurrently", overlapped.get())
            assertTrue(vm.ui.value.catalogRows["adult"]!!.single().adult)
            val previous = requests.get()
            vm.navigate(Screen.Home); vm.refreshPlaylistsAtAppStart(); vm.openLibrary(MediaKind.MOVIE)
            assertFalse(vm.ui.value.loading)
            assertEquals(previous, requests.get())
            assertEquals(2, vm.ui.value.catalogRows.values.sumOf { it.size })
        } finally { server.stop(0); threads.shutdownNow() }
    }
}
