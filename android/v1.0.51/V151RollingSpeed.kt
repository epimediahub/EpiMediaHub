package de.epimediahub.app.vpn

import java.util.ArrayDeque

/** Last ~1.2 seconds' ACTUAL bytes across parallel connections.
 * Never substitutes a peak for the complete-transfer average.
 */
internal class V151RollingSpeed(
    private val windowNanos: Long = 1_200_000_000L
) {
    private val history = ArrayDeque<V140SpeedTransfer.Sample>()
    @Synchronized fun rate(sample: V140SpeedTransfer.Sample): Double? {
        val previous = history.peekLast()
        if (previous != null &&
            (sample.nanos <= previous.nanos || sample.bytes < previous.bytes)) return null
        history.addLast(sample)
        while (history.size > 2 &&
               sample.nanos - history.peekFirst().nanos > windowNanos) {
            history.removeFirst()
        }
        val first = history.peekFirst() ?: return null
        val span = sample.nanos - first.nanos
        val bytes = sample.bytes - first.bytes
        if (span < 250_000_000L || bytes <= 0L) return null
        val mbps = bytes * 8_000.0 / span
        return mbps.takeIf { it.isFinite() && it > 0.0 }
    }
}
