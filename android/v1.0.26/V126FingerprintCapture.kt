@file:OptIn(androidx.media3.common.util.UnstableApi::class)

package de.epimediahub.app.data

import androidx.media3.common.C
import androidx.media3.common.Format
import androidx.media3.decoder.ffmpeg.EpiChromaprint
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.abs

internal data class V126Fingerprint(val words: IntArray, val offsetMs: Long, val lengthMs: Long,
    val durationMs: Long, val audioKey: String)

internal interface V126PcmTap {
    fun discontinuity()
    fun offer(buffer: ByteBuffer, ptsUs: Long, format: Format)
}

/** PCM stays in this bounded queue. Only hashes are uploaded. A full queue drops
 * capture data, never blocks ExoPlayer, and starts a new contiguous section. */
internal class V126FingerprintCapture(private val upload: suspend (V126Fingerprint) -> Unit) : V126PcmTap {
    companion object { const val WINDOW_US = 720_000_000L }
    private data class Block(val bytes: ByteArray, val ptsUs: Long, val format: Format, val generation: Int)
    private val generation = AtomicInteger()
    private val closed = AtomicBoolean()
    private val pcm = Channel<Block>(16)
    private val hashes = Channel<V126Fingerprint>(Channel.CONFLATED)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    @Volatile var durationMs = 0L
    @Volatile var enabled = false

    init {
        scope.launch(Dispatchers.IO) {
            for (fingerprint in hashes) {
                try { upload(fingerprint) }
                catch (cancelled: CancellationException) { throw cancelled }
                catch (_: Exception) { /* Playback remains independent of the server. */ }
            }
        }
        scope.launch {
            // No native work or network operation executes on the renderer thread.
            var native: EpiChromaprint? = null
            var currentGeneration = -1
            var audioKey = ""
            var keyedFormat: Format? = null
            var formatKey = ""
            var startUs = 0L
            var frames = 0L
            var rate = 0
            var nextSnapshotUs = 120_000_000L
            fun snapshot(final: Boolean) {
                val engine = native ?: return
                val lengthUs = frames * 1_000_000L / rate
                if (lengthUs < 30_000_000L || durationMs <= 0) return
                val words = if (final) engine.finish() else engine.snapshot()
                if (words.size >= 200) hashes.trySend(V126Fingerprint(words, startUs / 1000,
                    lengthUs / 1000, durationMs, audioKey))
            }
            fun finish() {
                try { snapshot(true) } finally { native?.close(); native = null; frames = 0 }
            }
            try {
                for (block in pcm) {
                    val bytesPerSample = if (block.format.pcmEncoding == C.ENCODING_PCM_FLOAT) 4 else 2
                    val bpf = bytesPerSample * block.format.channelCount
                    val endUs = startUs + if (rate > 0) frames * 1_000_000L / rate else 0
                    if (keyedFormat !== block.format) {
                        keyedFormat = block.format
                        formatKey = V116SkipKeys.hash("${block.format.id}|${block.format.language}|${block.format.sampleRate}|${block.format.channelCount}|${block.format.pcmEncoding}")
                    }
                    val key = formatKey
                    if (native != null && (block.generation != currentGeneration || key != audioKey ||
                            abs(block.ptsUs - endUs) > 20_000L)) finish()
                    if (block.ptsUs !in 0 until WINDOW_US) continue
                    if (native == null) {
                        currentGeneration = block.generation; audioKey = key
                        startUs = block.ptsUs; frames = 0; rate = block.format.sampleRate
                        nextSnapshotUs = 120_000_000L
                        native = EpiChromaprint(rate, block.format.channelCount, bytesPerSample == 4)
                    }
                    val remainingFrames = ((WINDOW_US - startUs) * rate / 1_000_000L - frames).coerceAtLeast(0L)
                    val count = minOf(block.bytes.size / bpf, remainingFrames.toInt())
                    if (count > 0) {
                        native!!.feed(block.bytes, count * bpf)
                        frames += count
                    }
                    val capturedUs = frames * 1_000_000L / rate
                    if (capturedUs >= nextSnapshotUs) {
                        snapshot(false); nextSnapshotUs += 120_000_000L
                    }
                    if (frames >= (WINDOW_US - startUs) * rate / 1_000_000L ||
                        (durationMs > 0 && startUs + capturedUs >= durationMs * 1000L - 20_000L)) finish()
                }
            } catch (_: Exception) { /* A capture failure cannot stop video or sound. */ }
            catch (_: LinkageError) { /* Unsupported native ABI disables capture only. */ }
            finally {
                runCatching { finish() }; hashes.close()
            }
        }.invokeOnCompletion { pcm.close() }
    }

    override fun discontinuity() { generation.incrementAndGet() }

    override fun offer(buffer: ByteBuffer, ptsUs: Long, format: Format) {
        if (!enabled || closed.get() || ptsUs !in 0 until WINDOW_US ||
            format.sampleRate !in 8000..192000 || format.channelCount !in 1..8 ||
            (format.pcmEncoding != C.ENCODING_PCM_16BIT && format.pcmEncoding != C.ENCODING_PCM_FLOAT)) return
        if (buffer.remaining() > 262_144) { discontinuity(); return }
        val copy = ByteArray(buffer.remaining()); buffer.get(copy)
        if (pcm.trySend(Block(copy, ptsUs, format, generation.get())).isFailure) discontinuity()
    }

    fun close() {
        if (!closed.compareAndSet(false, true)) return
        pcm.close()
        // Allow a final useful snapshot to upload after leaving the player.
        scope.launch { delay(12_000L); scope.cancel() }
    }
}
