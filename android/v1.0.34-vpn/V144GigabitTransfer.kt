package de.epimediahub.app.vpn

import java.util.concurrent.Callable
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicLongArray

/**
 * Multi-stream aggregate HTTPS bandwidth measurement, up to gigabit and beyond.
 * Each worker uses the existing route-verified, cancellation-aware HTTP transfer.
 * Rates are aggregate REAL bytes / single wall-clock duration; never sum Mbps.
 */
internal object V144GigabitTransfer {
    private const val STREAMS = 4
    private const val MIB = 1024 * 1024
    private const val MAX_TOTAL_MIB = 512

    /** Pilot before sizing a bounded test, not before trusting the VPN route. */
    fun downloadBytesPerStream(warmupMbps: Double): Int {
        val mib = when {
            warmupMbps >= 600.0 -> 128
            warmupMbps >= 300.0 -> 64
            warmupMbps >= 130.0 -> 32
            warmupMbps >= 60.0 -> 16
            else -> 8
        }
        return mib * MIB
    }

    fun uploadBytesPerStream(downloadMbps: Double): Int =
        (if (downloadMbps >= 500.0) 8 else 4) * MIB

    fun measure(
        parent: V140SpeedTransfer,
        url: String,
        bytesPerStream: Int,
        upload: Boolean,
        verify: () -> Unit,
        onSample: (V140SpeedTransfer.Sample) -> Unit
    ): V140SpeedTransfer.Sample {
        require(bytesPerStream in (256 * 1024)..(128 * MIB))
        require(bytesPerStream.toLong() * STREAMS <= MAX_TOTAL_MIB.toLong() * MIB)
        parent.checkActive()
        verify()

        val executor = Executors.newFixedThreadPool(STREAMS) { command ->
            Thread(command, "epimedia-gigabit-speed-worker").apply { isDaemon = true }
        }
        val workers = ArrayList<V140SpeedTransfer>(STREAMS)
        val totals = AtomicLongArray(STREAMS)
        val lastReport = AtomicLong(0)
        val ready = CountDownLatch(STREAMS)
        val go = CountDownLatch(1)
        val started = System.nanoTime()
        try {
            repeat(STREAMS) {
                val worker = V140SpeedTransfer()
                parent.registerWorker(worker)
                workers.add(worker)
            }
            val futures = workers.mapIndexed { index, worker ->
                executor.submit(Callable {
                    ready.countDown()
                    check(go.await(5, TimeUnit.SECONDS)) { "Worker-Start überschritten" }
                    parent.checkActive()
                    val sampleUpdate: (V140SpeedTransfer.Sample) -> Unit = { snapshot ->
                        totals.set(index, snapshot.bytes)
                        val now = System.nanoTime()
                        val previous = lastReport.get()
                        if (now - previous >= 150_000_000L &&
                            lastReport.compareAndSet(previous, now)) {
                            parent.checkActive()
                            val count = (0 until STREAMS).sumOf { totals.get(it) }
                            onSample(V140SpeedTransfer.Sample(count, now - started))
                        }
                    }
                    if (upload) worker.uploadLive(url, bytesPerStream, verify, sampleUpdate)
                    else worker.downloadLive(
                        "$url?bytes=$bytesPerStream&stream=$index",
                        bytesPerStream, verify, sampleUpdate
                    )
                })
            }
            check(ready.await(5, TimeUnit.SECONDS)) { "Worker konnten nicht gestartet werden" }
            go.countDown()
            val deadline = System.nanoTime() + 50_000_000_000L
            var received = 0L
            for (future in futures) {
                val remaining = (deadline - System.nanoTime()).coerceAtLeast(1L)
                received += future.get(remaining, TimeUnit.NANOSECONDS).bytes
            }
            val elapsed = (System.nanoTime() - started).coerceAtLeast(1L)
            parent.checkActive()
            verify()
            check(received == bytesPerStream.toLong() * STREAMS) {
                "Unvollständige parallele Datenübertragung"
            }
            val final = V140SpeedTransfer.Sample(received, elapsed)
            onSample(final)
            return final
        } catch (failure: Exception) {
            workers.forEach { it.cancel() }
            parent.checkActive()
            throw failure
        } finally {
            go.countDown()
            workers.forEach {
                it.cancel()
                parent.unregisterWorker(it)
            }
            executor.shutdownNow()
        }
    }
}
