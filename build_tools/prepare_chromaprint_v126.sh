#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?Missing PROJECT_ROOT}"
TASK_ARCHIVE="$PROJECT_ROOT/chromaprint-1.5.1.tar.gz"
TASK_SOURCE="$PROJECT_ROOT/ffmpeg-audio/src/main/jni/chromaprint"
if [ ! -s "$TASK_ARCHIVE" ]; then
  curl --fail --location --retry 3 --connect-timeout 20 --max-time 180 \
    https://github.com/acoustid/chromaprint/releases/download/v1.5.1/chromaprint-1.5.1.tar.gz -o "$TASK_ARCHIVE"
fi
echo "a1aad8fa3b8b18b78d3755b3767faff9abb67242e01b478ec9a64e190f335e1c  $TASK_ARCHIVE" | sha256sum --check
mkdir -p "$TASK_SOURCE"
tar --no-same-owner -xzf "$TASK_ARCHIVE" -C "$TASK_SOURCE" --strip-components=1
TASK_LICENSES="$PROJECT_ROOT/app/src/main/assets/licenses"
mkdir -p "$TASK_LICENSES"
cp "$TASK_SOURCE/LICENSE.md" "$TASK_LICENSES/Chromaprint-LICENSE.md"
cp "$TASK_SOURCE/src/3rdparty/kissfft/COPYING" "$TASK_LICENSES/KissFFT-COPYING.txt"
printf '%s\n' 'Chromaprint 1.5.1 source: https://github.com/acoustid/chromaprint/releases/tag/v1.5.1' \
  'EpiMediaHub JNI/build sources: https://github.com/epimediahub/EpiMediaHub/tree/android-v1.0.26-fingerprints/android/v1.0.26' \
  > "$TASK_LICENSES/Chromaprint-SOURCES.txt"
