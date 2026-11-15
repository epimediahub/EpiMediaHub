#!/usr/bin/env python3
"""Playback-only fingerprints and a legible, numerically ordered radio keyboard."""
import os
import shutil
from pathlib import Path

root = Path(os.environ['PROJECT_ROOT'])
java = root / 'app/src/main/java/de/epimediahub/app'
here = Path(__file__).resolve().parent

def replace_once(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, f'{path}: expected exactly one anchor: {old[:90]}'
    path.write_text(text.replace(old, new, 1))

gradle = root / 'app/build.gradle.kts'
replace_once(gradle, 'versionCode = 1025', 'versionCode = 1026')
replace_once(gradle, 'versionName = "1.0.25"', 'versionName = "1.0.26"')
for path in java.rglob('*.kt'):
    text = path.read_text()
    if '1.0.25' in text: path.write_text(text.replace('1.0.25', '1.0.26'))

for package, name in [('data','V126FingerprintCapture.kt'), ('ui','V126CaptureAudioSink.kt'), ('ui','V126RadioKeyboard.kt')]:
    shutil.copyfile(here / name, java / package / name)
native = root / 'ffmpeg-audio/src/main'
shutil.copyfile(here / 'EpiChromaprint.java', native / 'java/androidx/media3/decoder/ffmpeg/EpiChromaprint.java')
shutil.copyfile(here / 'FingerprintDeviceTest.java', root / 'ffmpeg-audio/src/androidTest/java/androidx/media3/decoder/ffmpeg/FingerprintDeviceTest.java')
for name in ['epi_chromaprint_jni.cc','Chromaprint.cmake']:
    shutil.copyfile(here / name, native / 'jni' / name)
cmake = native / 'jni/CMakeLists.txt'
cmake.write_text(cmake.read_text() + '\ninclude(Chromaprint.cmake)\n')
replace_once(java / 'ui/RadioScreen.kt',
    'V110TvKeyboardDialog(title, initial, accent, dismiss, allowEmpty = true, onSubmit = submit)',
    'V126RadioKeyboard(title, initial, accent, dismiss, onSubmit = submit)')

renderers = java / 'ui/V123AudioRenderers.kt'
replace_once(renderers, 'internal class V123AudioRenderers(context: Context) : DefaultRenderersFactory(context) {',
    '''internal class V123AudioRenderers(context: Context,
    private val capture: de.epimediahub.app.data.V126FingerprintCapture? = null) : DefaultRenderersFactory(context) {
    override fun buildAudioSink(context: Context, enableFloatOutput: Boolean,
        enableAudioOutputPlaybackParams: Boolean): androidx.media3.exoplayer.audio.AudioSink {
        val sink = requireNotNull(super.buildAudioSink(context, enableFloatOutput, enableAudioOutputPlaybackParams))
        return if (capture != null) V126CaptureAudioSink(sink, capture) else sink
    }''')

repo = java / 'data/V116SkipRepository.kt'
replace_once(repo, '    suspend fun flushPending() {', '''    fun canCapture(item: MediaEntry): Boolean = item.kind == MediaKind.EPISODE &&
        playlistId(item) > 0 && !SetupCodeProvisioning.sessionToken(context).isNullOrBlank()

    suspend fun captureAvailable(item: MediaEntry, duration: Long): Boolean? =
        request("${SetupCodeProvisioning.provisioningBaseUrl(context)}/v1/device/skip/lookup",
            payload(item, duration), true)?.optBoolean("fingerprint_capture", false)

    suspend fun uploadFingerprint(item: MediaEntry, fp: V126Fingerprint) {
        if (!canCapture(item)) return
        val bytes = java.nio.ByteBuffer.allocate(fp.words.size * 4).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        fp.words.forEach { bytes.putInt(it) }
        val body = payload(item, fp.durationMs).put("algorithm", "chromaprint-1").put("kind", "intro")
            .put("offset_ms", fp.offsetMs).put("length_ms", fp.lengthMs).put("audio_key", fp.audioKey)
            .put("fingerprint", android.util.Base64.encodeToString(bytes.array(), android.util.Base64.NO_WRAP))
        // Bounded retries are independent of playback and never open provider media.
        repeat(2) { attempt ->
            val result = request("${SetupCodeProvisioning.provisioningBaseUrl(context)}/v1/device/skip/fingerprint", body, true)
            if (result?.optString("status") in listOf("accepted", "cached", "unavailable")) return
            if (attempt == 0) delay(1_000L)
        }
    }

    suspend fun flushPending() {''')

player = java / 'ui/PlayerScreen.kt'
replace_once(player, '    val playbackEngine = remember(item.resumeKey, item.streamUrl) {',
    '''    val captureRepository = remember(context) { de.epimediahub.app.data.V116SkipRepository(context.applicationContext) }
    val capture = remember(item.resumeKey, item.streamUrl) {
        if (captureRepository.canCapture(item)) de.epimediahub.app.data.V126FingerprintCapture {
            captureRepository.uploadFingerprint(item, it)
        }.apply { enabled = true } else null
    }
    val playbackEngine = remember(item.resumeKey, item.streamUrl) {''')
replace_once(player, '        val renderersFactory = V123AudioRenderers(context)',
    '        val renderersFactory = V123AudioRenderers(context, capture)')
replace_once(player, '    val player = playbackEngine.second', '''    val player = playbackEngine.second
    DisposableEffect(capture) { onDispose { capture?.close() } }
    LaunchedEffect(player, capture) {
        val activeCapture = capture ?: return@LaunchedEffect
        var checked = false
        while (true) {
            val duration = player.duration.takeIf { it > 0 } ?: 0L
            activeCapture.durationMs = duration
            if (!checked && duration > 0) {
                val available = captureRepository.captureAvailable(item, duration)
                if (available != null) { checked = true; activeCapture.enabled = available }
            }
            delay(1_000L)
        }
    }''')

tests = root / 'app/src/test/java/de/epimediahub/app/ui'
for source in here.glob('*Test.kt'):
    shutil.copyfile(source, tests / source.name)
print('Android 1.0.26: playback fingerprints and larger ordered radio keyboard installed')
