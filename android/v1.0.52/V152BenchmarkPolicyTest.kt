package de.epimediahub.app.vpn

import org.junit.Assert.*
import org.junit.Test

class V152BenchmarkPolicyTest {
    @Test fun aSlowSinglePilotNeverCapsAnActuallyFastDualPilot() {
        val p = V152BenchmarkPolicy.plan(9.0,110.0,false)
        assertEquals(4,p.streams)
        assertTrue(p.bytesPerStream >= 16*1024*1024)
    }
    @Test fun commonHomeBroadbandUsesFourStreams() {
        assertEquals(4,V152BenchmarkPolicy.plan(13.0,17.0,false).streams)
        assertEquals(4,V152BenchmarkPolicy.plan(40.0,90.0,false).streams)
        assertEquals(4,V152BenchmarkPolicy.plan(103.0,270.0,false).streams)
    }
    @Test fun trulySlowLinksCanUseTwo() {
        assertEquals(2,V152BenchmarkPolicy.plan(2.0,6.0,false).streams)
    }
    @Test fun requestCapsAreNeverExceeded() {
        for(speed in listOf(1.0,10.0,50.0,270.0,1000.0)) {
            val p = V152BenchmarkPolicy.plan(speed,speed,false)
            assertTrue(p.bytesPerStream <= 32*1024*1024)
            assertTrue(p.bytesPerStream.toLong()*p.streams <= 128L*1024*1024)
        }
    }
    @Test fun fixedFileRangesStayDistinctAndInside100Mb() {
        val p = V152BenchmarkPolicy.plan(250.0,380.0,true)
        assertEquals(4,p.streams)
        assertTrue(p.bytesPerStream <= 16*1024*1024)
        assertTrue(p.bytesPerStream.toLong()*p.streams <= 100_000_000L)
    }
    @Test fun invalidOrMissingPilotNeverInventsMbps() {
        val p = V152BenchmarkPolicy.plan(Double.NaN,Double.NEGATIVE_INFINITY,false)
        assertTrue(p.pilotMbps > 0.0)
        assertTrue(p.bytesPerStream > 0)
    }
}
