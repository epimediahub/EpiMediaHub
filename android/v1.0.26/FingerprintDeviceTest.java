package androidx.media3.decoder.ffmpeg;

import static org.junit.Assert.*;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Arrays;

@RunWith(AndroidJUnit4.class)
public class FingerprintDeviceTest {
  private byte[] asset(String path) throws Exception {
    try (InputStream input=InstrumentationRegistry.getInstrumentation().getContext().getAssets().open(path)) {
      ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] buffer=new byte[8192];int n;
      while ((n=input.read(buffer))>=0) out.write(buffer,0,n);
      return out.toByteArray();
    }
  }
  private void verify(String name,int rate,int channels,boolean floating) throws Exception {
    byte[] pcm=asset("capture-"+name+".pcm");
    ByteBuffer expected=ByteBuffer.wrap(asset("capture-"+name+".fp")).order(ByteOrder.LITTLE_ENDIAN);
    int[] prefix=new int[0];
    try (EpiChromaprint capture=new EpiChromaprint(rate,channels,floating)) {
      for (int start=0;start<pcm.length;start+=16384) {
        byte[] chunk=Arrays.copyOfRange(pcm,start,Math.min(start+16384,pcm.length));
        capture.feed(chunk,chunk.length);
        if (start>=pcm.length/2 && prefix.length==0) prefix=capture.snapshot();
      }
      int[] result=capture.finish();
      assertEquals(expected.remaining()/4,result.length);
      long distance=0;
      for (int i=0;i<result.length;i++) distance+=Integer.bitCount(result[i]^expected.getInt());
      assertTrue("Android/server fingerprint mismatch: "+distance, distance/(32.0*result.length)<.01);
      assertTrue(prefix.length>80);
      assertArrayEquals(prefix,Arrays.copyOf(result,prefix.length));
    }
  }
  @Test public void monoPcmMatchesServerAlgorithm() throws Exception { verify("mono",11025,1,false); }
  @Test public void stereoResamplingMatchesServerAlgorithm() throws Exception { verify("stereo",48000,2,false); }
  @Test public void floatPcmMatchesServerAlgorithm() throws Exception { verify("float",48000,2,true); }
}
