#!/usr/bin/env python3
"""Keep Media3 video and decode unsupported TV/movie audio in the same player."""
import os
from pathlib import Path
import re
import shutil

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
here = Path(__file__).resolve().parent


def replace_once(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, f"{path}: expected one anchor, got {text.count(old)}: {old[:100]}"
    path.write_text(text.replace(old, new, 1))


gradle = root / "app/build.gradle.kts"
replace_once(gradle, "versionCode = 1022", "versionCode = 1023")
replace_once(gradle, 'versionName = "1.0.22"', 'versionName = "1.0.23"')
replace_once(gradle, 'dependencies {', 'dependencies {\n    implementation(project(":ffmpeg-audio"))')
for path in java.rglob("*.kt"):
    text = path.read_text()
    if "1.0.22" in text:
        path.write_text(text.replace("1.0.22", "1.0.23"))
shutil.copyfile(here / "V123AudioRenderers.kt", java / "ui/V123AudioRenderers.kt")
shutil.copytree(here / "ffmpeg-audio", root / "ffmpeg-audio", dirs_exist_ok=True)
shutil.copytree(here / "licenses", root / "app/src/main/assets/licenses", dirs_exist_ok=True)
shutil.copyfile(here / "AUDIO_SOURCES.md", root / "app/src/main/assets/licenses/FFmpeg-SOURCES.txt")
settings = root / "settings.gradle.kts"
settings.write_text(settings.read_text() + '\ninclude(":ffmpeg-audio")\n')
build = root / "build.gradle.kts"
text = build.read_text()
version = re.search(r'id\("com.android.application"\) version "([^"]+)"', text).group(1)
if 'id("com.android.library")' not in text:
    replace_once(build, 'plugins {', f'plugins {{\n    id("com.android.library") version "{version}" apply false')

player = java / "ui/PlayerScreen.kt"
replace_once(player, '''        val renderersFactory = DefaultRenderersFactory(context)
            .setEnableDecoderFallback(true)''', '''        val renderersFactory = V123AudioRenderers(context)''')
replace_once(player, 'import androidx.media3.exoplayer.DefaultRenderersFactory\n', '')
replace_once(player, 'Text("Audio-Kompatibilität", color = Color.White)', 'Text("VLC-Player", color = Color.White)')

surface = java / "ui/V121VodSurface.kt"
replace_once(surface, '    private var decoder = ""', '    private var decoder = ""\n    private var audioDecoder = ""')
replace_once(surface, '    private val analytics = object : AnalyticsListener {', '''    private val analytics = object : AnalyticsListener {
        override fun onAudioDecoderInitialized(eventTime: AnalyticsListener.EventTime, decoderName: String,
            initializedTimestampMs: Long, initializationDurationMs: Long) {
            audioDecoder = decoderName
        }
        override fun onAudioDecoderReleased(eventTime: AnalyticsListener.EventTime, decoderName: String) {
            if (audioDecoder == decoderName) audioDecoder = ""
        }''')
replace_once(surface, '        val format = player.videoFormat', '''        val format = player.videoFormat
        val audio = player.audioFormat ?: player.currentTracks.groups
            .filter { it.type == C.TRACK_TYPE_AUDIO }.let { groups ->
                (groups.firstOrNull { it.isSelected } ?: groups.firstOrNull())?.let { group ->
                    if (group.length > 0) group.getTrackFormat(
                        (0 until group.length).firstOrNull { group.isTrackSelected(it) } ?: 0) else null
                }
            }''')
replace_once(surface, '            codec = format?.sampleMimeType.orEmpty(), decoder = decoder,', '''            audioCodec = audio?.sampleMimeType.orEmpty(), audioDecoder = audioDecoder,
            audioChannels = audio?.channelCount ?: 0, audioSampleRate = audio?.sampleRate ?: 0,
            audioSelected = player.currentTracks.isTypeSelected(C.TRACK_TYPE_AUDIO),
            codec = format?.sampleMimeType.orEmpty(), decoder = decoder,''')

info = java / "ui/V122PlaybackInfo.kt"
replace_once(info, '    val request: String = "Wird ermittelt"', '''    val request: String = "Wird ermittelt",
    val audioCodec: String = "", val audioDecoder: String = "",
    val audioChannels: Int = 0, val audioSampleRate: Int = 0, val audioSelected: Boolean = false''')
replace_once(info, '                        if (data.speed != 1f)', '''                        Info("Tonformat", listOfNotNull(data.audioCodec.ifBlank { "Nicht gemeldet" },
                            if (data.audioChannels > 0) "${data.audioChannels} Kanäle" else null,
                            if (data.audioSampleRate > 0) "${data.audioSampleRate} Hz" else null).joinToString(" · "))
                        Info("Audiodecoder", data.audioDecoder.ifBlank {
                            if (data.audioSelected) "Wird ermittelt" else "Keine Tonspur ausgewählt"
                        })
                        if (data.speed != 1f)''')
replace_once(info, 'else "Audio-Kompatibilität", color', 'else "Zum VLC-Player", color')

tests = root / "app/src/test/java/de/epimediahub/app/ui"
for source in here.glob("*Test.kt"):
    shutil.copyfile(source, tests / source.name)
print("Android 1.0.23: Media3 FFmpeg audio, hardware video and audio diagnostics installed")
