# Hash-verified upstream source is prepared before Gradle configures CMake.
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(FFT_LIB kissfft CACHE STRING "Chromaprint FFT backend" FORCE)
# Android root-path lookup must not reinterpret this vendored source directory.
set(KISSFFT_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/chromaprint/src/3rdparty/kissfft" CACHE PATH "Bundled FFT source" FORCE)
# JNI already provides mono 11025 Hz; no second converter is needed in the core.
set(AUDIO_PROCESSOR_LIB "internal" CACHE STRING "PCM normalized by JNI" FORCE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "Static Chromaprint" FORCE)
set(BUILD_TESTS OFF CACHE BOOL "No upstream test executable in APK" FORCE)
set(BUILD_TOOLS OFF CACHE BOOL "No upstream command line tools in APK" FORCE)
add_subdirectory(chromaprint)
add_library(epiChromaprint SHARED epi_chromaprint_jni.cc)
target_include_directories(epiChromaprint PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/chromaprint/src")
target_link_libraries(epiChromaprint PRIVATE chromaprint swresample avutil)
target_link_options(epiChromaprint PRIVATE "-Wl,-z,max-page-size=16384")
