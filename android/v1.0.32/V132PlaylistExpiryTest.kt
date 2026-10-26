package de.epimediahub.app.data

import de.epimediahub.app.model.PlaylistProfile
import de.epimediahub.app.model.PlaylistType
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.util.Locale

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class V132PlaylistExpiryTest {
    private fun profile(id: String = "a", password: String = "secret") =
        PlaylistProfile(id, id, "", PlaylistType.XTREAM, "https://provider.invalid", "user", password)
    private fun response(value: Any?) = JSONObject().put("user_info", JSONObject()
        .put("auth", 1).put("status", "Active").put("exp_date", value ?: JSONObject.NULL))
    private fun repo(): V132PlaylistExpiryRepository {
        val app = RuntimeEnvironment.getApplication()
        app.getSharedPreferences("v132_playlist_expiry", 0).edit().clear().commit()
        return V132PlaylistExpiryRepository(app)
    }
    @Test fun epochSecondsAndMillisecondsReferToTheSameExpiry() {
        assertEquals(1_800_000_000_000L, V132PlaylistExpiryRepository.parse(response("1800000000")).untilMs)
        assertEquals(1_800_000_000_000L, V132PlaylistExpiryRepository.parse(response("1800000000000")).untilMs)
    }
    @Test fun malformedOrOutOfRangeValuesDoNotInventAnExpiry() {
        for (value in listOf("garbage", "9223372036854775807", "-2", "2027-02-30", "2027-01-15oops")) {
            val result = V132PlaylistExpiryRepository.parse(response(value))
            assertNull(value, result.untilMs); assertFalse(value, result.unlimited)
        }
    }
    @Test fun strictDateFormatsAndTranslatedLabelsAreSupported() {
        val result = V132PlaylistExpiryRepository.parse(response("2027-01-15T00:00:00Z"))
        assertNotNull(result.untilMs)
        assertTrue(result.label(Locale.GERMAN, 0).startsWith("Gültig bis 15.01.2027"))
        assertTrue(result.label(Locale.GERMAN, Long.MAX_VALUE).startsWith("Abgelaufen am"))
    }
    @Test fun unlimitedRequiresAnExplicitActiveProviderAccount() {
        assertTrue(V132PlaylistExpiryRepository.parse(response(null)).unlimited)
        assertFalse(V132PlaylistExpiryRepository.parse(JSONObject()).unlimited)
        val inactive = response(null); inactive.getJSONObject("user_info").put("auth", 0).put("status", "Expired")
        assertFalse(V132PlaylistExpiryRepository.parse(inactive).unlimited)
    }
    @Test fun accountCacheSurvivesOfflineButNeverLeaksToAnotherAccount() = runBlocking {
        val repo = repo(); val a = profile()
        val known = repo.refresh(a, 1000) { response("1800000000") }
        assertEquals(known, repo.refresh(a, 7*60*60*1000L) { throw java.io.IOException("offline") })
        assertNull(repo.cached(profile("b")).untilMs)
        assertNull(repo.cached(profile(password = "changed")).untilMs)
    }
    @Test fun freshCacheAvoidsNetworkAndPlainM3uHasNoFabricatedDate() = runBlocking {
        val repo = repo(); val a = profile(); var requests = 0
        repo.refresh(a, 1000) { requests++; response("1800000000") }
        repo.refresh(a, 2000) { requests++; response("1800000000") }; assertEquals(1, requests)
        val plain = PlaylistProfile("m3u", "M3U", "https://provider.invalid/channels.m3u", PlaylistType.M3U)
        assertNull(V132PlaylistExpiryRepository.providerProfile(plain))
        assertNull(repo.refresh(plain, 1000) { fail("Plain M3U must not query an account"); JSONObject() }.untilMs)
    }
    @Test fun revokedProviderAccountClearsCachedUnlimitedState() = runBlocking {
        val repo = repo(); val a = profile(); assertTrue(repo.refresh(a, 1000) { response(null) }.unlimited)
        val expired = response(null); expired.getJSONObject("user_info").put("auth", 0).put("status", "Expired")
        assertFalse(repo.refresh(a, 7*60*60*1000L) { expired }.unlimited)
    }
}
