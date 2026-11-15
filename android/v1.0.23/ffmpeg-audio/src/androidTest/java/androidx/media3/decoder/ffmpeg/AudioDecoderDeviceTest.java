package androidx.media3.decoder.ffmpeg;

import static org.junit.Assert.*;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import androidx.media3.common.C;
import androidx.media3.common.Format;
import androidx.media3.common.MediaItem;
import androidx.media3.common.MimeTypes;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.decoder.DecoderInputBuffer;
import androidx.media3.decoder.SimpleDecoderOutputBuffer;
import androidx.media3.exoplayer.DefaultRenderersFactory;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.analytics.AnalyticsListener;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.ByteBuffer;
import java.util.Collections;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.Test;
import org.junit.runner.RunWith;

/** Executes the packaged JNI on Android, rather than pretending Linux can load Android .so files. */
@RunWith(AndroidJUnit4.class)
public class AudioDecoderDeviceTest {
  private byte[] asset(String name) throws Exception {
    try (InputStream in = InstrumentationRegistry.getInstrumentation().getContext().getAssets().open(name);
         ByteArrayOutputStream out = new ByteArrayOutputStream()) {
      byte[] block = new byte[4096];
      int size;
      while ((size = in.read(block)) != -1) out.write(block, 0, size);
      return out.toByteArray();
    }
  }

  private void decode(String name, String mime, byte[] extra) throws Exception {
    assertTrue("Packaged FFmpeg JNI must load on Android", FfmpegLibrary.isAvailable());
    assertTrue("Missing decoder: " + mime, FfmpegLibrary.supportsFormat(mime));
    Format.Builder format = new Format.Builder().setSampleMimeType(mime).setChannelCount(2).setSampleRate(48000);
    if (extra != null) format.setInitializationData(Collections.singletonList(extra));
    FfmpegAudioDecoder decoder = new FfmpegAudioDecoder(format.build(), 4, 4, 16384, false);
    SimpleDecoderOutputBuffer output = null;
    try {
      DecoderInputBuffer input = decoder.dequeueInputBuffer();
      assertNotNull(input);
      byte[] data = asset(name + ".bin");
      input.ensureSpaceForWrite(data.length);
      input.data.put(data);
      input.timeUs = 0L;
      input.flip();
      decoder.queueInputBuffer(input);
      long deadline = SystemClock.elapsedRealtime() + 5000L;
      while (output == null && SystemClock.elapsedRealtime() < deadline) {
        output = decoder.dequeueOutputBuffer();
        if (output == null) SystemClock.sleep(5);
      }
      assertNotNull("No PCM output for " + mime, output);
      assertNotNull(output.data);
      assertTrue("PCM output is empty", output.data.remaining() > 256);
      ByteBuffer pcm = output.data.duplicate();
      boolean nonzero = false;
      while (pcm.hasRemaining()) if (pcm.get() != 0) nonzero = true;
      assertTrue("Decoded audio is silent", nonzero);
      assertEquals(2, decoder.getChannelCount());
      assertEquals(48000, decoder.getSampleRate());
      assertEquals(C.ENCODING_PCM_16BIT, decoder.getEncoding());
    } finally {
      if (output != null) output.release();
      decoder.release();
    }
  }

  @Test public void mpegLayerTwoProducesAudiblePcm() throws Exception { decode("mp2", MimeTypes.AUDIO_MPEG_L2, null); }
  @Test public void ac3ProducesAudiblePcm() throws Exception { decode("ac3", MimeTypes.AUDIO_AC3, null); }
  @Test public void eac3ProducesAudiblePcm() throws Exception { decode("eac3", MimeTypes.AUDIO_E_AC3, null); }
  @Test public void dtsProducesAudiblePcm() throws Exception { decode("dca", MimeTypes.AUDIO_DTS, null); }
  @Test public void aacProducesAudiblePcm() throws Exception { decode("aac", MimeTypes.AUDIO_AAC, new byte[] {0x11, (byte) 0x90}); }

  @Test public void transportStreamPlaysWithFfmpegAudioAndTheExoplayerClock() throws Exception {
    Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
    File file = new File(context.getCacheDir(), "v123-mp2-live.ts");
    try (FileOutputStream out = new FileOutputStream(file)) { out.write(asset("mp2-live.ts")); }
    CountDownLatch done = new CountDownLatch(1);
    AtomicReference<PlaybackException> error = new AtomicReference<>();
    AtomicReference<String> decoderName = new AtomicReference<>();
    AtomicReference<ExoPlayer> reference = new AtomicReference<>();
    Handler handler = new Handler(Looper.getMainLooper());
    handler.post(() -> {
      ExoPlayer player = new ExoPlayer.Builder(context,
          new DefaultRenderersFactory(context).setExtensionRendererMode(DefaultRenderersFactory.EXTENSION_RENDERER_MODE_PREFER)
              .setEnableDecoderFallback(true)).build();
      reference.set(player);
      player.addAnalyticsListener(new AnalyticsListener() {
        @Override public void onAudioDecoderInitialized(EventTime time, String name, long initialized, long duration) {
          decoderName.set(name);
        }
      });
      player.addListener(new Player.Listener() {
        @Override public void onPlaybackStateChanged(int state) { if (state == Player.STATE_ENDED) done.countDown(); }
        @Override public void onPlayerError(PlaybackException failure) { error.set(failure); done.countDown(); }
      });
      player.setMediaItem(MediaItem.fromUri(file.toURI().toString()));
      player.prepare();
      player.play();
    });
    try {
      assertTrue("Transport stream playback timed out", done.await(20, TimeUnit.SECONDS));
      assertNull("Player error: " + error.get(), error.get());
      assertNotNull("No audio decoder selected", decoderName.get());
      assertTrue("Wrong audio decoder: " + decoderName.get(), decoderName.get().startsWith("ffmpeg"));
    } finally {
      CountDownLatch released = new CountDownLatch(1);
      handler.post(() -> { if (reference.get() != null) reference.get().release(); released.countDown(); });
      assertTrue(released.await(5, TimeUnit.SECONDS));
      file.delete();
    }
  }
}
