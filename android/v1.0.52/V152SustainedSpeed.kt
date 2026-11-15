package de.epimediahub.app.vpn

/**
 * Time-weighted steady-state HTTP goodput. Unlike a peak sample, this uses
 * ALL verified payload bytes between the first post-startup checkpoint and
 * the last checkpoint. It never changes the full-transfer average.
 */
internal class V152SustainedSpeed {
    data class Report(val mbps: Double?, val seconds: Double?, val samples: Int)
    private val samples = ArrayList<V140SpeedTransfer.Sample>()

    @Synchronized fun record(sample: V140SpeedTransfer.Sample) {
        if (sample.nanos < 0L || sample.bytes < 0L) return
        val last = samples.lastOrNull()
        if (last != null && (sample.nanos <= last.nanos || sample.bytes < last.bytes)) return
        samples.add(sample)
    }

    @Synchronized fun report(final: V140SpeedTransfer.Sample): Report {
        // Short bursts are not a valid sustained-speed benchmark.
        if (final.nanos < 1_850_000_000L || samples.size < 6)
            return Report(null, null, samples.size)
        val begin = samples.firstOrNull { it.nanos >= 750_000_000L }
            ?: return Report(null, null, samples.size)
        val end = samples.lastOrNull { it.nanos <= final.nanos }
            ?: return Report(null, null, samples.size)
        val nanos = end.nanos - begin.nanos
        val bytes = end.bytes - begin.bytes
        if (nanos < 1_000_000_000L || bytes <= 0L)
            return Report(null, null, samples.size)
        val speed = bytes * 8_000.0 / nanos
        return if (speed.isFinite() && speed > 0)
            Report(speed, nanos / 1_000_000_000.0, samples.size)
        else Report(null, null, samples.size)
    }
}
