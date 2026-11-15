package androidx.media3.decoder.ffmpeg;

/** Algorithm 1, unsigned raw words; native resampling matches the server's
 * FFmpeg mono / 11025 Hz path. Instances belong to one background worker. */
public final class EpiChromaprint implements AutoCloseable {
  static { System.loadLibrary("epiChromaprint"); }
  private long handle;
  public EpiChromaprint(int sampleRate, int channels, boolean floatingPoint) {
    handle = create(sampleRate, channels, floatingPoint);
    if (handle == 0) throw new IllegalStateException("fingerprint_unavailable");
  }
  public void feed(byte[] pcm, int length) {
    if (handle == 0 || !feed(handle, pcm, length)) throw new IllegalStateException("fingerprint_failed");
  }
  public int[] snapshot() { return read(handle, false); }
  public int[] finish() { return read(handle, true); }
  @Override public void close() { if (handle != 0) { destroy(handle); handle = 0; } }
  private static native long create(int sampleRate, int channels, boolean floatingPoint);
  private static native boolean feed(long handle, byte[] pcm, int length);
  private static native int[] read(long handle, boolean finish);
  private static native void destroy(long handle);
}
