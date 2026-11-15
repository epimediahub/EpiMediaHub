package de.epimediahub.app.data

import de.epimediahub.app.model.MediaKind
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class V158ProviderDatesTest {
    @Test fun usesLastModifiedForLatestSeriesUpdates() {
        val row = JSONObject().put("added", "1650000000").put("last_modified", "1760000000")
        assertEquals(1760000000L, V158ProviderDates.fromRow(row, MediaKind.SERIES))
        assertEquals(1650000000L, V158ProviderDates.fromRow(row, MediaKind.MOVIE))
    }

    @Test fun decodesSecondsMillisecondsAndText() {
        assertEquals(1760000000L, V158ProviderDates.parse("1760000000"))
        assertEquals(1760000000L, V158ProviderDates.parse("1760000000000"))
        assertEquals(1760000000L, V158ProviderDates.parse("2025-10-09 08:53:20"))
        assertEquals(1760000000L, V158ProviderDates.fromRow(
            JSONObject().put("date_added", "2025-10-09T08:53:20Z"), MediaKind.MOVIE))
    }

    @Test fun skipsInvalidDatesWithoutInventingOrder() {
        assertEquals(0L, V158ProviderDates.parse("null"))
        assertEquals(0L, V158ProviderDates.parse("123"))
        assertEquals(0L, V158ProviderDates.fromRow(JSONObject().put("added", "0"), MediaKind.MOVIE))
        assertEquals(1760000000L, V158ProviderDates.fromRow(
            JSONObject().put("added", "0").put("last_modified", "1760000000"), MediaKind.SERIES))
    }
}
