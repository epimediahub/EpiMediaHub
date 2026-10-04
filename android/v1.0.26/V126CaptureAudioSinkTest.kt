@file:OptIn(androidx.media3.common.util.UnstableApi::class)
package de.epimediahub.app.ui

import androidx.media3.common.C
import androidx.media3.common.Format
import androidx.media3.exoplayer.audio.AudioSink
import de.epimediahub.app.data.V126PcmTap
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.lang.reflect.Proxy
import java.nio.ByteBuffer

@RunWith(RobolectricTestRunner::class)
class V126CaptureAudioSinkTest {
    @Test fun partialBufferRetriesPreserveAudioAndUseFileTimeExactlyOnce() {
        val blocks = mutableListOf<ByteArray>()
        val times = mutableListOf<Long>()
        val tap = object : V126PcmTap {
            override fun discontinuity() {}
            override fun offer(buffer: ByteBuffer, ptsUs: Long, format: Format) {
                val bytes = ByteArray(buffer.remaining()); buffer.get(bytes)
                blocks += bytes; times += ptsUs
            }
        }
        val delegate = Proxy.newProxyInstance(AudioSink::class.java.classLoader, arrayOf(AudioSink::class.java)) { _, method, args ->
            when (method.name) {
                "handleBuffer" -> { val buffer = args!![0] as ByteBuffer
                    buffer.position(minOf(buffer.limit(), buffer.position()+8)); !buffer.hasRemaining() }
                else -> null
            }
        } as AudioSink
        val sink = V126CaptureAudioSink(delegate,tap)
        sink.configure(Format.Builder().setSampleMimeType("audio/raw").setSampleRate(8000)
            .setChannelCount(2).setPcmEncoding(C.ENCODING_PCM_16BIT).build(),0,null)
        val offset = 1_000_000_000_000L
        sink.setOutputStreamOffsetUs(offset)
        val bytes = ByteArray(16) { it.toByte() }
        val buffer = ByteBuffer.wrap(bytes.copyOf())
        assertFalse(sink.handleBuffer(buffer,offset+12_000_000L,1))
        assertTrue(sink.handleBuffer(buffer,offset+12_000_000L,1))
        assertArrayEquals(bytes,blocks.flatMap { it.toList() }.toByteArray())
        assertEquals(listOf(12_000_000L,12_000_250L),times)
        assertArrayEquals(bytes,buffer.array())
    }

    @Test fun seekAndFormatChangeBreakCaptureContinuity() {
        var resets=0
        val tap=object : V126PcmTap {
            override fun discontinuity() { resets++ }
            override fun offer(buffer: ByteBuffer, ptsUs: Long, format: Format) {}
        }
        val delegate=Proxy.newProxyInstance(AudioSink::class.java.classLoader,arrayOf(AudioSink::class.java)) { _,_,_ -> null } as AudioSink
        val sink=V126CaptureAudioSink(delegate,tap)
        sink.configure(Format.Builder().setSampleMimeType("audio/raw").setSampleRate(48000)
            .setChannelCount(2).setPcmEncoding(C.ENCODING_PCM_16BIT).build(),0,null)
        sink.flush(); sink.handleDiscontinuity()
        sink.configure(Format.Builder().setSampleMimeType("audio/raw").setSampleRate(44100)
            .setChannelCount(1).setPcmEncoding(C.ENCODING_PCM_16BIT).build(),0,null)
        assertEquals(4,resets)
    }
}
