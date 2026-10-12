package de.epimediahub.app.data

import org.junit.Assert.*
import org.junit.Test
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

class V166EpgNowTest {
    private val berlin = TimeZone.getTimeZone("Europe/Berlin")
    private fun seconds(value: String, zone: TimeZone): Long =
        SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).apply {
            timeZone = zone
        }.parse(value)!!.time / 1000L

    @Test fun secondsAndMillisecondsAreEquivalent() {
        val start = 1791806400L
        val end = start + 3600L
        val now = start + 900L
        val seconds = V166EpgTimes.window("$start", "$end", "", "", now, berlin)
        val millis = V166EpgTimes.window("${start}000", "${end}000", "", "", now, berlin)
        assertEquals(seconds, millis)
        assertEquals(start, millis?.start)
        assertTrue(millis!!.contains(now))
    }

    @Test fun missingNumericTimestampsUseProgrammeDateFields() {
        val start = seconds("2026-10-12 18:00:00", berlin)
        val now = start + 900L
        val event = V166EpgTimes.window("", "", "2026-10-12 18:00:00",
            "2026-10-12 19:00:00", now, berlin)
        assertNotNull(event)
        assertTrue(event!!.contains(now))
    }

    @Test fun providerUtcCalendarCanRepairMismatchedEpochs() {
        val now = seconds("2026-10-12 18:30:00", berlin)
        val utc = TimeZone.getTimeZone("UTC")
        val start = seconds("2026-10-12 16:00:00", utc)
        val shifted = V166EpgTimes.window("${start+7200}", "${start+10800}",
            "2026-10-12 16:00:00", "2026-10-12 17:00:00", now, berlin)
        assertNotNull(shifted)
        assertTrue(shifted!!.contains(now))
        assertEquals(start, shifted.start)
    }

    @Test fun futureOnlyMustNotBeLabelledNow() {
        val now = 1791806400L
        val later = now + 7200L
        val result = V166EpgTimes.window("$later", "${later+3600}", "", "", now, berlin)
        assertNotNull(result)
        assertFalse(result!!.contains(now))
    }

    @Test fun invalidOrUnboundedTimesAreDiscarded() {
        assertNull(V166EpgTimes.window("0", "0", "", "", 1791806400L, berlin))
        assertNull(V166EpgTimes.window("1791806400", "1793006400", "", "", 1791806400L, berlin))
    }
}
