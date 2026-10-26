package de.epimediahub.app.ui

import android.content.Context
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class V128SmartTubeStoreTest {
    @Test fun learnedClientSurvivesColdStartStaysAccountScopedAndExpires() {
        val context = RuntimeEnvironment.getApplication()
        context.getSharedPreferences("epi_smarttube_clients_v128", Context.MODE_PRIVATE).edit().clear().commit()
        var now = 100_000L
        val first = V128SmartTubeClientStore(context) { now }
        assertNull(first.load("guest"))
        first.remember("guest", "TV_DOWNGRADED")
        val restarted = V128SmartTubeClientStore(context) { now }
        assertEquals("TV_DOWNGRADED", restarted.load("guest"))
        assertNull(restarted.load("other-account"))
        now += 7L * 24 * 60 * 60 * 1000
        assertNull(restarted.load("guest"))
        restarted.remember("guest", "WEB")
        restarted.clear("guest"); assertNull(restarted.load("guest"))
        restarted.remember("guest", "https://example.invalid/stream")
        assertNull(restarted.load("guest"))
    }
}
