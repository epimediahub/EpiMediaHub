package de.epimediahub.app.vpn

import kotlin.math.ceil
import kotlin.math.roundToInt

/**
 * A bounded adaptive benchmark: choose transfer size from a measured pilot,
 * not from the customer's advertised tariff. The server's 32 MiB/request and
 * 176 MiB/session limits remain enforced independently.
 */
internal object V150AdaptiveSpeed {
    private const val MIB = 1024 * 1024
    data class Plan(val streams: Int, val bytesPerStream: Int, val estimatedSeconds: Double)

    fun plan(pilotMbps: Double, maxPerStreamMiB: Int = 32): Plan {
        val mbps = pilotMbps.takeIf { it.isFinite() && it > 0.0 } ?: 10.0
        val streams = if (mbps < 25.0) 2 else 4
        // More time for modest links; fast links stop at our bounded data budget.
        val targetSeconds = when {
            mbps < 25.0 -> 7.0
            mbps < 100.0 -> 6.5
            else -> 6.0
        }
        val wantedMiB = ceil(mbps * 1_000_000.0 / 8.0 *
            targetSeconds / streams / MIB).toInt()
        val perStreamMiB = wantedMiB.coerceIn(2, maxPerStreamMiB.coerceIn(2, 32))
        val expected = (perStreamMiB.toDouble() * MIB * streams * 8.0) /
            (mbps * 1_000_000.0)
        return Plan(streams, perStreamMiB * MIB, expected)
    }

    /**
     * Collect interval rates from actual transferred bytes. The first second
     * is discarded to avoid TLS/TCP startup bias. No samples -> no fake score.
     */
    internal class Stability {
        private var previous: V140SpeedTransfer.Sample? = null
        private val intervals = ArrayList<Double>()
        @Synchronized fun record(sample: V140SpeedTransfer.Sample) {
            val prior = previous
            previous = sample
            if (prior == null || prior.nanos < 1_000_000_000L) return
            val bytes = sample.bytes - prior.bytes
            val nanos = sample.nanos - prior.nanos
            if (bytes <= 0L || nanos < 120_000_000L) return
            val rate = bytes * 8_000.0 / nanos
            if (rate.isFinite() && rate > 0.0) intervals.add(rate)
        }
        @Synchronized fun report(): Report {
            if (intervals.size < 2) return Report(null, null)
            val sorted = intervals.sorted()
            val median = sorted[sorted.size / 2]
            val low = sorted[(sorted.size * .15).toInt()]
            val high = sorted[(sorted.size * .85).toInt().coerceAtMost(sorted.lastIndex)]
            val variation = if (median > 0.0) ((high - low) / median * 100.0)
                .coerceIn(0.0, 999.0) else return Report(null, null)
            return Report(variation.roundToInt(), high)
        }
    }
    data class Report(val variationPercent: Int?, val peakMbps: Double?)
}
