#!/usr/bin/env python3
import os
import re
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
replace_once(gradle, "versionCode = 1008", "versionCode = 1009", "versionCode")
replace_once(gradle, 'versionName = "1.0.8"', 'versionName = "1.0.9"', "versionName")

for relative in (
    "ui/Screens.kt",
    "ui/V078DashboardPairingGate.kt",
    "ui/V083Home.kt",
    "data/V070WeatherClient.kt",
    "ui/V106SmartTubePlayer.kt",
):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("1.0.8", "1.0.9"))

intro = java / "ui/V070Intro.kt"
s = intro.read_text()

for old in (
    "import android.media.AudioAttributes\n",
    "import android.media.AudioFormat\n",
    "import android.media.AudioTrack\n",
    "import kotlin.math.PI\n",
    "import kotlin.math.sin\n",
):
    s = s.replace(old, "")

if "import android.content.Context\n" not in s:
    s = s.replace(
        "package de.epimediahub.app.ui\n\n",
        "package de.epimediahub.app.ui\n\nimport android.content.Context\nimport android.media.MediaPlayer\n",
        1,
    )

if "import androidx.compose.ui.platform.LocalContext\n" not in s:
    s = s.replace(
        "import androidx.compose.ui.layout.ContentScale\n",
        "import androidx.compose.ui.layout.ContentScale\nimport androidx.compose.ui.platform.LocalContext\n",
        1,
    )

signature = "fun V070IntroScreen(accent: Color, onFinished: () -> Unit) {\n"
if signature not in s:
    raise SystemExit("Intro screen signature missing")
s = s.replace(
    signature,
    signature + "    val context = LocalContext.current\n",
    1,
)

if "launch { V070IntroSound.play() }" not in s:
    raise SystemExit("Old intro sound launch missing")
s = s.replace(
    "launch { V070IntroSound.play() }",
    "launch { V109IntroSound.play(context) }",
    1,
)

new_sound = r'''private object V109IntroSound {
    suspend fun play(context: Context) = withContext(Dispatchers.IO) {
        var player: MediaPlayer? = null
        try {
            player = MediaPlayer.create(
                context.applicationContext,
                R.raw.epimedia_intro_organic_orchestral_chime
            ) ?: return@withContext
            // The master itself peaks around -1 dBFS. Keep a little app-level
            // headroom so the ident feels premium rather than startling.
            player.setVolume(0.82f, 0.82f)
            player.start()
            delay(2850L)
        } catch (_: Throwable) {
            // Intro visuals must never fail because a device rejects audio.
        } finally {
            runCatching {
                if (player?.isPlaying == true) player?.stop()
            }
            runCatching { player?.release() }
        }
    }
}
'''

s2, count = re.subn(
    r"private object V070IntroSound \{[\s\S]*?\n\}\s*$",
    new_sound,
    s,
    count=1,
)
if count != 1:
    raise SystemExit(f"Old synthesized intro sound block count was {count}")
intro.write_text(s2)

raw = root / "app/src/main/res/raw/epimedia_intro_organic_orchestral_chime.wav"
if not raw.exists() or raw.stat().st_size < 100_000:
    raise SystemExit("Generated 2.85 second intro WAV is missing or unexpectedly small")

checks = [
    (gradle, "versionCode = 1009"),
    (gradle, 'versionName = "1.0.9"'),
    (gradle, "minSdk = 25"),
    (intro, "val context = LocalContext.current"),
    (intro, "V109IntroSound.play(context)"),
    (intro, "R.raw.epimedia_intro_organic_orchestral_chime"),
    (intro, "player.setVolume(0.82f, 0.82f)"),
    (intro, "delay(2850L)"),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing marker {marker} in {path}")

print("Android 1.0.9 organic orchestral intro sound applied")
