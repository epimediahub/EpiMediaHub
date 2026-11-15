# Media3 FFmpeg audio extension

EpiMediaHub Android 1.0.23 includes the audio-only FFmpeg decoder extension from
AndroidX Media3 1.9.4 (Apache License 2.0) and FFmpeg 6.1.6 (LGPL 2.1 or later).
FFmpeg is built without GPL, nonfree or version-3 components. No FFmpeg video
decoder is included. Android MediaCodec continues to decode video.

Copyright belongs to the respective upstream authors. License texts are in this
directory and in the corresponding source package. FFmpeg is provided without
warranty. Modifications and reverse engineering for debugging modifications to
these LGPL components are permitted under their license.

Corresponding source and build scripts, including the exact FFmpeg release:
https://github.com/epimediahub/EpiMediaHub/releases/download/v0.7.0-test/EpiMediaHub_Audio_Sources_v1.0.23.tar.xz

App integration and source versions:
https://github.com/epimediahub/EpiMediaHub/tree/android-v1.0.23-audio/android/v1.0.23
https://github.com/androidx/media/tree/1.9.4/libraries/decoder_ffmpeg
https://ffmpeg.org/releases/ffmpeg-6.1.6.tar.xz

To rebuild the replaceable libffmpegJNI.so library, extract the source package,
install JDK 17, Gradle 8.10.2, Android SDK 35, NDK 26.1.10909125 and CMake 3.22.1.
Set ANDROID_HOME to the SDK and PROJECT_ROOT to the extracted directory, then run:

    bash build_android_audio_v123.sh
    gradle :ffmpeg-audio:assembleRelease

This produces an AAR with a JNI shared library for each of armeabi-v7a,
arm64-v8a, x86 and x86_64. The FFmpeg static libraries are linked inside that
replaceable shared library; the full corresponding source is provided.
To install a locally modified APK, replace its ABI-matching libffmpegJNI.so and
re-sign the APK with your own Android signing key. This requires a separate
installation from the official APK because Android requires matching signatures
for in-place updates. Application integration is also available in the repository.

Changes to the Media3 extension: standalone Gradle module; CMake uses the
per-ABI installed FFmpeg headers; only the four audio Java classes are packaged.
The upstream Java classes and JNI implementation are unmodified. FFmpeg source is
unmodified; the decoder selection and configure arguments are in the build script.
