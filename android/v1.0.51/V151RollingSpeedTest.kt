package de.epimediahub.app.vpn

import org.junit.Assert.*
import org.junit.Test

class V151RollingSpeedTest {
    @Test fun firstAndShortSamplesMustNotInventSpeed() {
        val r = V151RollingSpeed()
        assertNull(r.rate(V140SpeedTransfer.Sample(100,100_000_000)))
        assertNull(r.rate(V140SpeedTransfer.Sample(900,150_000_000)))
    }
    @Test fun rateIsIncrementalNotCumulative() {
        val r = V151RollingSpeed()
        assertNull(r.rate(V140SpeedTransfer.Sample(10_000_000,1_000_000_000)))
        assertEquals(16.0,
            r.rate(V140SpeedTransfer.Sample(11_000_000,1_500_000_000))!!,0.01)
    }
    @Test fun backwardsSamplesNeverSpikeGauge() {
        val r = V151RollingSpeed()
        r.rate(V140SpeedTransfer.Sample(1_000,100_000_000))
        assertNull(r.rate(V140SpeedTransfer.Sample(900,500_000_000)))
        assertNull(r.rate(V140SpeedTransfer.Sample(2_000,100_000_000)))
    }
    @Test fun windowTracksRecentBytes() {
        val r = V151RollingSpeed()
        r.rate(V140SpeedTransfer.Sample(0,100_000_000))
        r.rate(V140SpeedTransfer.Sample(1_000_000,500_000_000))
        r.rate(V140SpeedTransfer.Sample(2_000_000,900_000_000))
        assertTrue(r.rate(V140SpeedTransfer.Sample(6_000_000,1_700_000_000))!!>0)
    }
}
