package de.epimediahub.app.ui

import androidx.test.core.app.ApplicationProvider
import android.content.Context
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class V188VerifiedFpsTest {
    private fun live(id: String, category: String, profile: String) =
        MediaEntry(id, "IT: SKY CALCIO 1", MediaKind.LIVE,
            categoryId = category, sourceProfileId = profile)

    @Test fun neverConfusesSystemRefreshOrUnverifiedFormatFpsWithVerifiedFrames() {
        assertEquals(0, V188VerifiedFps.verifiedCandidate(0f, true, 300))
        assertEquals(0, V188VerifiedFps.verifiedCandidate(50f, true, 20))
        assertEquals(0, V188VerifiedFps.verifiedCandidate(50f, false, 300))
        assertEquals(50, V188VerifiedFps.verifiedCandidate(50f, true, 300))
        assertEquals(25, V188VerifiedFps.verifiedCandidate(25f, true, 300))
        assertEquals(0, V188VerifiedFps.verifiedCandidate(-1f, true, 300))
        assertTrue(V188VerifiedFps.diagnosticLabel(0, 50).contains("nicht bestätigt"))
        assertEquals("50 fps · Gemessen", V188VerifiedFps.diagnosticLabel(50, 25))
    }

    @Test fun remembersVerifiedRateSeparatelyPerProviderCategoryAndChannel() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        V188VerifiedFps.initialize(context)
        val base = "fps-v188-cross-test"
        V188VerifiedFps.recordVerified(context, live(base, "it-fhd", "italia"), 50)
        V188VerifiedFps.recordVerified(context, live(base, "it-4k", "italia"), 25)
        assertEquals(50, V188VerifiedFps.rememberedRate("italia", "it-fhd", base))
        assertEquals(25, V188VerifiedFps.rememberedRate("italia", "it-4k", base))
        assertEquals(0, V188VerifiedFps.rememberedRate("germany", "it-fhd", base))
        assertEquals(0, V188VerifiedFps.rememberedRate("italia", "it-hd", base))
        assertEquals(0, V188VerifiedFps.rememberedRate("italia", "it-fhd", "different-id"))
    }

    @Test fun unknownOrUnsupportedRateCannotPolluteVerifiedStore() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val id = "fps-v188-unknown-test"
        V188VerifiedFps.initialize(context)
        V188VerifiedFps.recordVerified(context, live(id, "calcio", "italia"), 0)
        V188VerifiedFps.recordVerified(context, live(id, "calcio", "italia"), 60)
        assertEquals(0, V188VerifiedFps.rememberedRate("italia", "calcio", id))
    }

    @Test fun onlyKnown50FpsOtherCategoryEnablesSportMode() {
        val original = live("4k", "sport4k", "italia").copy(name = "IT SKY CALCIO 1 4K")
        val alt = live("fhd", "sportfhd", "italia").copy(name = "IT SKY CALCIO 1 FULL HD")
        val all = V188SportCatalog.samePlaylist(original, listOf(original),
            mapOf("sport4k" to listOf(original), "sportfhd" to listOf(alt)), "italia")

        assertTrue(V188SportMode.verifiedAlternatives(original, all, "italia") { _, _, _ -> 25 }.isEmpty())
        assertTrue(V188SportMode.verifiedAlternatives(original, all, "italia") { _, _, _ -> 0 }.isEmpty())

        val confirmed = V188SportMode.verifiedAlternatives(original, all, "italia") { _, _, id ->
            if (id == "fhd") 50 else 25
        }
        assertEquals(listOf("fhd"), confirmed.map { it.id })
    }

    @Test fun multipleVerified50FpsAcrossCategoriesAllAvailableForFailover() {
        val original = live("4k", "uhd", "italia").copy(name = "IT: SKY CALCIO 1 UHD")
        val fhd = live("fhd", "fullhd", "italia").copy(name = "IT: SKY CALCIO 1 FHD")
        val hd = live("hd", "hd", "italia").copy(name = "IT: SKY CALCIO 1 HD")
        val other = live("wrong", "fullhd", "other").copy(name = "IT: SKY CALCIO 1 FHD")
        val merged = V188SportCatalog.samePlaylist(original, listOf(original),
            mapOf("uhd" to listOf(original), "fullhd" to listOf(fhd, other),
                "hd" to listOf(hd)), "italia")
        val verified = V188SportMode.verifiedAlternatives(original, merged, "italia") { _, _, id ->
            if (id == "fhd" || id == "hd") 50 else 25
        }
        assertEquals(listOf("fhd", "hd"), verified.map { it.id })
        assertFalse(verified.any { it.id == "wrong" })
    }
}
