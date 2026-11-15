package de.epimediahub.app.ui

import de.epimediahub.app.data.*
import de.epimediahub.app.model.*
import java.io.StringReader
import kotlinx.coroutines.CancellationException
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [25])
class V129CatalogueRegressionTest {
    @Test fun largeCatalogueKeepsAllEntriesAndAgeFlagsWithoutWholeResponseJsonTree() {
        val json = buildString {
            append('[')
            repeat(20_000) { index ->
                if (index > 0) append(',')
                append("""{"stream_id":$index,"name":"Film $index","category_id":"${index % 30}","age_rating":${if (index % 7 == 0) 18 else 12},"is_adult":${index % 7 == 0},"unused":{"large":[1,2,3]}}""")
            }
            append(']')
        }
        val rows = V129JsonRows.parse(StringReader(json)) { item ->
            MediaEntry(item.optString("stream_id"), item.optString("name"), MediaKind.MOVIE,
                categoryId = item.optString("category_id"), adult = V128AdultContent.providerAdult(item), ageRating = V128AdultContent.providerAge(item))
        }
        assertEquals(20_000, rows.size)
        assertEquals("19999", rows.last().id)
        assertEquals(18, rows.first().ageRating)
        assertEquals(12, rows[1].ageRating)
        assertTrue(rows[7].adult)
        val bound = V128AdultContent.bind(rows, listOf(MediaCategory("1", "Erwachsene", true)))
        assertTrue(bound[1].adult)
        assertSame(rows[2], bound[2])
    }

    @Test fun cancelledCatalogueStopsBeforeMappingMoreRowsAndClosesReader() {
        var checks = 0
        var mapped = 0
        var closed = false
        val input = object : StringReader("[{\"id\":1},{\"id\":2},{\"id\":3}]") {
            override fun close() { closed = true; super.close() }
        }
        try {
            V129JsonRows.parse(input, { if (++checks == 2) throw CancellationException("screen changed") }) { mapped++; it }
            fail("Cancellation must be propagated")
        } catch (_: CancellationException) { }
        assertEquals(1, mapped)
        assertTrue(closed)
    }

    @Test fun absentNullNumericAndNamedAgeFieldsRemainCompatible() {
        assertEquals(-1, V128AdultContent.providerAge(JSONObject().put("rating", "18")))
        assertEquals(-1, V128AdultContent.providerAge(JSONObject().put("age_rating", JSONObject.NULL)))
        for (age in listOf(0, 6, 12, 16, 18, 21)) {
            assertEquals(age, V128AdultContent.providerAge(JSONObject().put("age_rating", age)))
        }
        assertEquals(18, V128AdultContent.providerAge(JSONObject().put("certification", "FSK 18")))
        assertEquals(18, V128AdultContent.providerAge(JSONObject().put("mpaa", "NC-17")))
        assertEquals(16, V128AdultContent.providerAge(JSONObject().put("content_rating", "16+")))
        val empty = JSONObject()
        val started = System.nanoTime()
        repeat(50_000) { assertEquals(-1, V128AdultContent.providerAge(empty)) }
        println("V129: 50000 entries without age metadata: ${(System.nanoTime() - started) / 1_000_000} ms")
    }

    @Test fun malformedOrNonArrayResponsesFailInsteadOfInstallingPartialCatalogue() {
        listOf("{\"error\":\"offline\"}", "[{\"id\":1},", "[{\"id\":1}] trailing").forEach { json ->
            assertTrue(runCatching { V129JsonRows.parse(StringReader(json)) { it } }.isFailure)
        }
        val items = V129JsonRows.parse(StringReader("[null,\"noise\",{\"id\":5,\"name\":\"Grüße\"}]")) { it.optString("name") }
        assertEquals(listOf("Grüße"), items)
    }
}
