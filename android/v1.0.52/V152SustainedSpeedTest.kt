package de.epimediahub.app.vpn

import org.junit.Assert.*
import org.junit.Test

class V152SustainedSpeedTest {
    @Test fun startupAndShortRunsNeverGiveFakeSteadySpeed() {
        val v = V152SustainedSpeed()
        v.record(V140SpeedTransfer.Sample(1_000_000, 300_000_000))
        v.record(V140SpeedTransfer.Sample(2_000_000, 700_000_000))
        assertNull(v.report(V140SpeedTransfer.Sample(2_000_000, 700_000_000)).mbps)
    }

    @Test fun sustainedRateUsesAllActualPostStartupBytesNotMaxPeak() {
        val v = V152SustainedSpeed()
        val samples = listOf(
            V140SpeedTransfer.Sample(0,100_000_000),
            V140SpeedTransfer.Sample(1_000_000,300_000_000),
            V140SpeedTransfer.Sample(3_000_000,500_000_000),
            V140SpeedTransfer.Sample(5_000_000,800_000_000),
            V140SpeedTransfer.Sample(11_000_000,1_100_000_000),
            V140SpeedTransfer.Sample(15_000_000,1_400_000_000),
            V140SpeedTransfer.Sample(24_000_000,1_800_000_000),
            V140SpeedTransfer.Sample(28_000_000,2_100_000_000),
            V140SpeedTransfer.Sample(34_000_000,2_400_000_000)
        )
        samples.forEach(v::record)
        val result = v.report(samples.last())
        assertNotNull(result.mbps)
        // 29M payload bytes / 1.6 seconds = 145 Mbit/s, not best 300ms.
        assertEquals(145.0, result.mbps!!, 0.01)
        assertEquals(1.6, result.seconds!!, 0.01)
    }

    @Test fun outOfOrderOrDecreasingByteSamplesCannotInflateRate() {
        val v = V152SustainedSpeed()
        val s = (1..10).map {
            V140SpeedTransfer.Sample(it * 1_000_000L, it * 250_000_000L)
        }
        s.forEach(v::record)
        v.record(V140SpeedTransfer.Sample(100_000_000, 100_000_000))
        v.record(V140SpeedTransfer.Sample(1_000, 2_700_000_000))
        val result = v.report(s.last())
        assertEquals(32.0, result.mbps!!, 0.01)
    }
}
