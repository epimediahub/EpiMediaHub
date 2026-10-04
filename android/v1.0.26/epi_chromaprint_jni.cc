#include <jni.h>
#include <cstdint>
#include <memory>
#include <vector>
#include "chromaprint.h"
extern "C" {
#include <libavutil/channel_layout.h>
#include <libavutil/mathematics.h>
#include <libswresample/swresample.h>
}

struct Capture {
  ChromaprintContext* cp = nullptr;
  SwrContext* swr = nullptr;
  int rate = 0, channels = 0, bytes = 0;
  bool finished = false;
  ~Capture() { swr_free(&swr); if (cp) chromaprint_free(cp); }
};

extern "C" JNIEXPORT jlong JNICALL
Java_androidx_media3_decoder_ffmpeg_EpiChromaprint_create(JNIEnv*, jclass, jint rate, jint channels, jboolean floating) {
  if (rate < 8000 || rate > 192000 || channels < 1 || channels > 8) return 0;
  std::unique_ptr<Capture> c(new Capture());
  c->rate = rate; c->channels = channels; c->bytes = floating ? 4 : 2;
  AVChannelLayout input, output = AV_CHANNEL_LAYOUT_MONO;
  av_channel_layout_default(&input, channels);
  const int result = swr_alloc_set_opts2(&c->swr, &output, AV_SAMPLE_FMT_S16, 11025,
      &input, floating ? AV_SAMPLE_FMT_FLT : AV_SAMPLE_FMT_S16, rate, 0, nullptr);
  av_channel_layout_uninit(&input);
  if (result < 0 || !c->swr || swr_init(c->swr) < 0) return 0;
  c->cp = chromaprint_new(1); // Matches skip_analysis.fingerprint(), not default algorithm guesses.
  if (!c->cp || !chromaprint_start(c->cp, 11025, 1)) return 0;
  return reinterpret_cast<jlong>(c.release());
}

static bool convert(Capture* c, const uint8_t* pcm, int frames) {
  const int capacity = av_rescale_rnd(swr_get_delay(c->swr, c->rate) + frames,
      11025, c->rate, AV_ROUND_UP) + 64;
  if (capacity < 0 || capacity > 100000) return false;
  std::vector<int16_t> mono(capacity);
  uint8_t* output = reinterpret_cast<uint8_t*>(mono.data());
  int count = swr_convert(c->swr, &output, capacity, pcm ? &pcm : nullptr, frames);
  return count >= 0 && (!count || chromaprint_feed(c->cp, mono.data(), count));
}

extern "C" JNIEXPORT jboolean JNICALL
Java_androidx_media3_decoder_ffmpeg_EpiChromaprint_feed(JNIEnv* env, jclass, jlong handle, jbyteArray pcm, jint length) {
  auto* c = reinterpret_cast<Capture*>(handle);
  if (!c || c->finished || !pcm || length < 0 || length > 262144 ||
      length > env->GetArrayLength(pcm) || length % (c->channels * c->bytes)) return false;
  // Copy only on the capture worker, never pin the renderer's audio buffer.
  std::vector<uint8_t> input(length);
  env->GetByteArrayRegion(pcm, 0, length, reinterpret_cast<jbyte*>(input.data()));
  if (env->ExceptionCheck()) return false;
  return convert(c, input.data(), length / (c->channels * c->bytes));
}

extern "C" JNIEXPORT jintArray JNICALL
Java_androidx_media3_decoder_ffmpeg_EpiChromaprint_read(JNIEnv* env, jclass, jlong handle, jboolean finish) {
  auto* c = reinterpret_cast<Capture*>(handle);
  if (!c) return env->NewIntArray(0);
  if (finish && !c->finished) {
    if (!convert(c, nullptr, 0) || !chromaprint_finish(c->cp)) return env->NewIntArray(0);
    c->finished = true;
  }
  uint32_t* words = nullptr;
  int count = 0;
  if (!chromaprint_get_raw_fingerprint(c->cp, &words, &count) || count < 0 || count > 6000) {
    if (words) chromaprint_dealloc(words);
    return env->NewIntArray(0);
  }
  jintArray result = env->NewIntArray(count);
  if (result && count) env->SetIntArrayRegion(result, 0, count, reinterpret_cast<const jint*>(words));
  chromaprint_dealloc(words);
  return result;
}

extern "C" JNIEXPORT void JNICALL
Java_androidx_media3_decoder_ffmpeg_EpiChromaprint_destroy(JNIEnv*, jclass, jlong handle) {
  delete reinterpret_cast<Capture*>(handle);
}
