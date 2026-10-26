package de.epimediahub.app.vpn

import java.net.URL
import org.junit.Assert.*
import org.junit.Test

/** Pure contract checks; no connection to a public server during Android QA. */
class V148SelfHostedSpeedTestContractTest {
    private val mib = 1024 * 1024

    @Test fun bearerNeverSentToLookalikeOrInsecureOrigins() {
        assertTrue(isSelfHostedSpeedtestOrigin(URL(
            "https://speedtest.epimediahub.com/v1/down?bytes=4096&stream=0")))
        assertTrue(isSelfHostedSpeedtestOrigin(URL(
            "https://speedtest.epimediahub.com:443/v1/up")))
        assertFalse(isSelfHostedSpeedtestOrigin(URL(
            "http://speedtest.epimediahub.com/v1/up")))
        assertFalse(isSelfHostedSpeedtestOrigin(URL(
            "https://speedtest.epimediahub.com:444/v1/up")))
        assertFalse(isSelfHostedSpeedtestOrigin(URL(
            "https://speedtest.epimediahub.com.evil.invalid/v1/up")))
        assertFalse(isSelfHostedSpeedtestOrigin(URL(
            "https://speed.cloudflare.com/__up")))
    }

    @Test fun selfHostedPlanStaysWithinSessionAndRequestLimits() {
        // 32 B probe, 4 MiB single, 2x4 MiB dual, max 4x32 MiB main.
        for (sample in listOf(0.1, 1.0, 15.0, 60.0, 130.0, 300.0, 1000.0)) {
            val downEach = V144GigabitTransfer.downloadBytesPerStream(sample)
                .coerceAtMost(32 * mib)
            assertTrue(downEach in (256 * 1024)..(32 * mib))
            val totalDownload = 32L + 4L * mib + 8L * mib + 4L * downEach
            assertTrue("Download exceeds 176 MiB session cap", totalDownload <= 176L * mib)
            val upEach = V144GigabitTransfer.uploadBytesPerStream(sample)
            assertTrue("Upload exceeds 16 MiB request cap", upEach <= 16 * mib)
            assertTrue("Upload exceeds 64 MiB session cap", 4L * upEach <= 64L * mib)
        }
    }
}
