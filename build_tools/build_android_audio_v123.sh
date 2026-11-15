#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?Missing PROJECT_ROOT}"
: "${ANDROID_HOME:?Missing ANDROID_HOME}"

TASK_PROJECT="$(cd "$PROJECT_ROOT" && pwd)"
TASK_NATIVE="$TASK_PROJECT/ffmpeg-audio/src/main/jni"
TASK_SOURCE="$TASK_NATIVE/ffmpeg"
TASK_ARCHIVE="$TASK_PROJECT/ffmpeg-6.1.6.tar.xz"
TASK_NDK="$ANDROID_HOME/ndk/26.1.10909125"
TASK_TOOLS="$TASK_NDK/toolchains/llvm/prebuilt/linux-x86_64/bin"
TASK_JOBS="${FFMPEG_BUILD_JOBS:-2}"
TASK_DECODERS="aac,mp3,mp2,mp1,ac3,eac3,dca,truehd,mlp,vorbis,opus,flac,alac,amrnb,amrwb,pcm_mulaw,pcm_alaw"
TASK_BUILD_KEY="$(sha256sum "${BASH_SOURCE[0]}" | cut -d' ' -f1)"

test -x "$TASK_TOOLS/aarch64-linux-android25-clang"
if [ ! -f "$TASK_ARCHIVE" ]; then
  curl --fail --location --retry 3 --user-agent EpiMediaHub-Builder/1.0.23 \
    https://ffmpeg.org/releases/ffmpeg-6.1.6.tar.xz --output "$TASK_ARCHIVE"
fi
echo "d4fcb164028dd3beee5d92c0ac72e46aac6973c75ea12dc14de07bf8f407370a  $TASK_ARCHIVE" | sha256sum --check
if [ ! -f "$TASK_SOURCE/configure" ]; then
  mkdir -p "$TASK_SOURCE"
  tar --no-same-owner -xJf "$TASK_ARCHIVE" -C "$TASK_SOURCE" --strip-components=1
fi

# Each ABI has its own build and configuration headers. Never reuse ARM config
# headers for the x86 emulator or another Android device architecture.
for TASK_ABI in armeabi-v7a arm64-v8a x86 x86_64; do
  TASK_BUILD="$TASK_PROJECT/.audio-build/$TASK_ABI"
  TASK_PREFIX="$TASK_SOURCE/android-libs/$TASK_ABI"
  if [ -f "$TASK_PREFIX/build-key.txt" ] && [ "$(cat "$TASK_PREFIX/build-key.txt")" = "$TASK_BUILD_KEY" ] &&
      [ -s "$TASK_PREFIX/libavcodec.a" ] && [ -s "$TASK_PREFIX/libavutil.a" ] && [ -s "$TASK_PREFIX/libswresample.a" ]; then
    echo "Reusing verified audio build for $TASK_ABI"
    continue
  fi
  mkdir -p "$TASK_BUILD" "$TASK_PREFIX"
  case "$TASK_ABI" in
    armeabi-v7a) TASK_ARCH=arm; TASK_CPU=armv7-a; TASK_TRIPLE=armv7a-linux-androideabi25; TASK_FLAGS=(-march=armv7-a -mfloat-abi=softfp);;
    arm64-v8a) TASK_ARCH=aarch64; TASK_CPU=armv8-a; TASK_TRIPLE=aarch64-linux-android25; TASK_FLAGS=();;
    x86) TASK_ARCH=x86; TASK_CPU=i686; TASK_TRIPLE=i686-linux-android25; TASK_FLAGS=();;
    x86_64) TASK_ARCH=x86_64; TASK_CPU=x86-64; TASK_TRIPLE=x86_64-linux-android25; TASK_FLAGS=();;
  esac
  (
    cd "$TASK_BUILD"
    "$TASK_SOURCE/configure" \
      --prefix="$TASK_PREFIX" --libdir="$TASK_PREFIX" --incdir="$TASK_PREFIX/include" \
      --target-os=android --arch="$TASK_ARCH" --cpu="$TASK_CPU" --enable-cross-compile \
      --cc="$TASK_TOOLS/$TASK_TRIPLE-clang" --cxx="$TASK_TOOLS/$TASK_TRIPLE-clang++" \
      --ar="$TASK_TOOLS/llvm-ar" --ranlib="$TASK_TOOLS/llvm-ranlib" \
      --nm="$TASK_TOOLS/llvm-nm" --strip="$TASK_TOOLS/llvm-strip" \
      --enable-static --disable-shared --enable-pic --disable-doc --disable-programs \
      --disable-everything --disable-avdevice --disable-avformat --disable-swscale \
      --disable-postproc --disable-avfilter --disable-symver --disable-network \
      --disable-autodetect --disable-gpl --disable-nonfree --disable-version3 \
      --disable-v4l2-m2m --disable-vulkan --disable-x86asm --enable-swresample \
      --enable-decoder="$TASK_DECODERS" --extra-cflags="${TASK_FLAGS[*]}" \
      --extra-ldexeflags=-pie
    make -j"$TASK_JOBS"
    make install-libs install-headers
    test -s "$TASK_PREFIX/libavcodec.a"
    cp config.h "$TASK_PREFIX/include/epimediahub-ffmpeg-config.h"
    printf '%s\n' "$TASK_BUILD_KEY" > "$TASK_PREFIX/build-key.txt"
  )
done

# CMake's wrapper uses installed public headers matching its target ABI.
python3 - "$TASK_NATIVE/CMakeLists.txt" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]);s=p.read_text()
old='include_directories(${ffmpeg_location})'
new='include_directories(${ffmpeg_binaries}/include)'
assert s.count(old)==1 or new in s
p.write_text(s.replace(old,new))
PY
echo 'FFmpeg audio-only decoders built for ARMv7, ARM64, x86 and x86_64'
