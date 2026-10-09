package de.epimediahub.app.vpn

import kotlin.math.ceil
import kotlin.math.max

/**
 * Do not size the real multi-connection benchmark from a single HTTP connection:
 * TCP/TLS ramp-up on one small request can badly underestimate a fast link.
 *
 * The 2-stream diagnostic is already measured, so use the faster confirmed
 * pilot. Keep self-hosted per-request/session quotas and distinct fixed-file
 * byte ranges intact.
 */
internal object V152BenchmarkPolicy {
    private const val MIB = 1024 * 1024
    data class Plan(val streams: Int, val bytesPerStream: Int,
                    val expectedSeconds: Double, val pilotMbps: Double)

    fun plan(singleMbps: Double, dualMbps: Double, fixedFile: Boolean): Plan {
        val valid = listOf(singleMbps, dualMbps).filter { it.isFinite() && it > 0.0 }
        val pilot = valid.maxOrNull() ?: 1.0
        // At 8+ Mbit/s, four sockets also reveal per-connection throttling.
        val streams = if (pilot < 8.0) 2 else 4
        val capMiB = if (fixedFile) 16 else 32
        val targetSeconds = if (pilot < 25.0) 7.0 else 8.0
        val wantedMiB = ceil(pilot * 1_000_000.0 * targetSeconds /
                            (streams * 8.0 * MIB)).toInt()
        val perStream = wantedMiB.coerceIn(2,capMiB)
        val seconds = perStream.toDouble() * MIB * streams * 8.0 /
                      (max(pilot,0.01) * 1_000_000.0)
        return Plan(streams, perStream * MIB, seconds, pilot)
    }
}
