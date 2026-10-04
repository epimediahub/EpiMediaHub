@file:OptIn(androidx.media3.common.util.UnstableApi::class)

package de.epimediahub.app.ui

import androidx.media3.common.C
import androidx.media3.common.Format
import androidx.media3.exoplayer.audio.AudioSink
import androidx.media3.exoplayer.audio.ForwardingAudioSink
import de.epimediahub.app.data.V126PcmTap
import java.nio.ByteBuffer

/** Tap only bytes actually consumed by the real sink. ExoPlayer may retry one
 * partially consumed buffer; its original timestamp must not be counted twice. */
internal class V126CaptureAudioSink(sink: AudioSink, private val capture: V126PcmTap) : ForwardingAudioSink(sink) {
    private var format = Format.EMPTY
    private var streamOffsetUs = 0L
    private var lastBuffer: ByteBuffer? = null
    private var firstPosition = 0
    override fun configure(inputFormat: Format, specifiedBufferSize: Int, outputChannels: IntArray?) {
        if (format != inputFormat) capture.discontinuity()
        format = inputFormat
        super.configure(inputFormat, specifiedBufferSize, outputChannels)
    }
    override fun setOutputStreamOffsetUs(outputStreamOffsetUs: Long) {
        streamOffsetUs = outputStreamOffsetUs
        super.setOutputStreamOffsetUs(outputStreamOffsetUs)
    }
    override fun handleBuffer(buffer: ByteBuffer, presentationTimeUs: Long, encodedAccessUnitCount: Int): Boolean {
        if (lastBuffer !== buffer) { lastBuffer = buffer; firstPosition = buffer.position() }
        val before = buffer.position()
        val view = buffer.duplicate()
        val handled = super.handleBuffer(buffer, presentationTimeUs, encodedAccessUnitCount)
        val consumed = buffer.position() - before
        val bpf = (if (format.pcmEncoding == C.ENCODING_PCM_FLOAT) 4 else 2) * format.channelCount
        if (consumed > 0 && bpf > 0 && format.sampleRate > 0) {
            view.limit(before + consumed)
            capture.offer(view, presentationTimeUs - streamOffsetUs +
                (before - firstPosition) / bpf * 1_000_000L / format.sampleRate, format)
        }
        if (handled) lastBuffer = null
        return handled
    }
    override fun handleDiscontinuity() { capture.discontinuity(); super.handleDiscontinuity() }
    override fun flush() { lastBuffer = null; capture.discontinuity(); super.flush() }
    override fun reset() { lastBuffer = null; capture.discontinuity(); super.reset() }
}
