package de.epimediahub.app.data

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class V115SkipPolicyTest {
    @Test fun wrongCutAndSeasonEstimatesNeverCreateSkipButtons() {
        val response = JSONObject("""{"segments":{"intro":{"start_ms":229500,"end_ms":246500,"match":"out-of-range","adjusted":false,"confidence":0.99}},"intro_length_estimate_ms":17000}""")
        assertTrue(V115SkipPolicy.select(V115SkipPolicy.skipDb(response, 3_480_000), 3_480_000).isEmpty())
        val shifted = JSONObject("""{"segments":{"intro":{"start_ms":209500,"end_ms":226500,"match":"shifted","adjusted":true,"confidence":0.99}}}""")
        assertTrue(V115SkipPolicy.skipDb(shifted, 3_480_000).isEmpty())
    }

    @Test fun durationVersionsAreCheckedBeforeAcceptingIntroDbTimes() {
        val versions = JSONObject("""{"versions":[{"duration_ms":3500192},{"duration_ms":0},{"duration_ms":2839000}]}""")
        assertEquals(3_500_192L, V115SkipPolicy.matchingVersion(versions, 3_500_000))
        assertNull(V115SkipPolicy.matchingVersion(versions, 3_480_000))
        val raw = JSONObject("""{"intro":[{"start_ms":228664,"end_ms":246143}],"credits":[{"start_ms":3431000,"end_ms":null}]}""")
        assertTrue(V115SkipPolicy.select(V115SkipPolicy.theIntroDb(raw, 3_480_000, false), 3_480_000).isEmpty())
        assertEquals(2, V115SkipPolicy.select(V115SkipPolicy.theIntroDb(raw, 3_500_000, true), 3_500_000).size)
    }

    @Test fun agreeingSourcesUseTheIntersectionAndConflictsAreHidden() {
        val a = V115Segment(V115SegmentKind.INTRO, 30_000, 90_000, "SkipDB", true, .93)
        val b = a.copy(startMs = 31_000, endMs = 89_500, source = "TheIntroDB")
        val selected = V115SkipPolicy.select(listOf(a, b), 2_400_000).single()
        assertEquals(31_000L, selected.startMs); assertEquals(89_500L, selected.endMs)
        assertTrue(selected.source.contains("SkipDB") && selected.source.contains("TheIntroDB"))
        assertTrue(V115SkipPolicy.select(listOf(a, b.copy(startMs = 160_000, endMs = 220_000)), 2_400_000).isEmpty())
    }

    @Test fun unknownRuntimeInvalidRangesAndWeakConfidenceCannotSkipContent() {
        val valid = V115Segment(V115SegmentKind.INTRO, 20_000, 80_000, "SkipDB", true, .9)
        val bad = listOf(valid.copy(startMs = -1), valid.copy(endMs = 2_600_000), valid.copy(endMs = 19_000),
            valid.copy(endMs = 400_000), valid.copy(confidence = .6), valid.copy(durationMatched = false))
        assertTrue(V115SkipPolicy.select(bad, 2_400_000).isEmpty())
        assertTrue(V115SkipPolicy.select(listOf(valid), 0).isEmpty())
        assertFalse(valid.active(19_999)); assertTrue(valid.active(20_000)); assertFalse(valid.active(80_000))
    }

    @Test fun outroEndsAtItsBoundaryAndPreservesPostCreditsScenes() {
        val raw = JSONObject("""{"outro":{"start_ms":2200000,"end_ms":2280000,"confidence":0.98},"post_credits":{"start_ms":2300000,"end_ms":2400000}}""")
        val selected = V115SkipPolicy.select(V115SkipPolicy.introDb(raw, 2_400_000), 2_400_000).single()
        assertEquals(2_280_000L, selected.endMs)
        assertFalse(selected.active(2_310_000))
        raw.remove("post_credits")
        assertTrue(V115SkipPolicy.select(V115SkipPolicy.introDb(raw, 2_400_000), 2_400_000).isEmpty())
    }

    @Test fun correctMediaTypeYearAndUniqueTitleAreRequiredForSearch() {
        val raw = JSONObject("""{"results":[{"name":"Dark","mediaType":"series","year":2017,"tmdbId":70523},{"name":"Dark","mediaType":"movie","year":2017,"tmdbId":123}],"local":[{"name":"Dark","mediaType":"series","year":2017,"imdb_id":"tt5753856"}]}""")
        assertEquals(V115Identity("tt5753856", 70523), V115SkipPolicy.searchIdentity(raw, "DE | Dark (2017) FHD", 2017, true))
        assertFalse(V115SkipPolicy.searchIdentity(raw, "Dark", 2024, true).usable)
        raw.getJSONArray("results").put(JSONObject("""{"name":"Dark","mediaType":"series","year":2025,"tmdbId":999}"""))
        assertFalse(V115SkipPolicy.searchIdentity(raw, "Dark", 0, true).usable)
    }

    @Test fun mazeSearchRejectsAmbiguousShowsAndIgnoresFuzzyResults() {
        val rows = JSONArray("""[{"show":{"name":"Breaking Bad","premiered":"2008-01-20","externals":{"imdb":"tt0903747"}}},{"show":{"name":"Breaking Bad: Minisodes","premiered":"2009-01-20","externals":{"imdb":"tt2387761"}}}]""")
        assertEquals("tt0903747", V115SkipPolicy.mazeIdentity(rows, "Breaking Bad", 2008))
        rows.put(JSONObject("""{"show":{"name":"Breaking Bad","premiered":"2026-01-20","externals":{"imdb":"tt1234567"}}}"""))
        assertEquals("", V115SkipPolicy.mazeIdentity(rows, "Breaking Bad", 0))
    }

    @Test fun multipleCreditBlocksKeepTheirSeparateSceneBoundaries() {
        val root = JSONObject("""{"credits":[{"start_ms":2000000,"end_ms":2100000},{"start_ms":2250000,"end_ms":null}]}""")
        val selected = V115SkipPolicy.select(V115SkipPolicy.theIntroDb(root, 2_400_000, true), 2_400_000)
        assertEquals(2, selected.size)
        assertEquals(2_100_000L, selected.first().endMs)
        assertTrue(selected.none { it.active(2_150_000) })
    }
}
