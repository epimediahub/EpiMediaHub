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
replace_once(gradle, "versionCode = 1006", "versionCode = 1007", "versionCode")
replace_once(gradle, 'versionName = "1.0.6"', 'versionName = "1.0.7"', "versionName")

# Match the host's existing Media3 version. Reflective source lookup previously
# allowed compilation without the DASH module, then failed at video startup.
text = gradle.read_text()
core = re.findall(r'implementation\("androidx\.media3:media3-exoplayer:([^"]+)"\)', text)
if len(core) != 1:
    raise SystemExit(f"expected one Media3 core dependency, found {len(core)}")
version = core[0]
dash = f'implementation("androidx.media3:media3-exoplayer-dash:{version}")'
if "androidx.media3:media3-exoplayer-dash:" in text:
    if text.count(dash) != 1:
        raise SystemExit("DASH dependency must match the Media3 core version")
else:
    anchor = f'implementation("androidx.media3:media3-exoplayer:{version}")'
    replace_once(gradle, anchor, anchor + "\n    " + dash, "Media3 DASH dependency")

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("1.0.6", "1.0.7"))

player = java / "ui/V106SmartTubePlayer.kt"
player.write_text(player.read_text().replace("1.0.6", "1.0.7"))
replace_once(
    player,
    "import androidx.media3.exoplayer.source.DefaultMediaSourceFactory\n",
    "import androidx.media3.exoplayer.dash.DashMediaSource\n"
    "import androidx.media3.exoplayer.hls.HlsMediaSource\n"
    "import androidx.media3.exoplayer.source.MediaSource\n"
    "import androidx.media3.exoplayer.source.DefaultMediaSourceFactory\n",
    "explicit adaptive media source imports",
)
replace_once(
    player,
    '''            ExoPlayer.Builder(context)
                .setMediaSourceFactory(
                    DefaultMediaSourceFactory(context).setDataSourceFactory(dataSource)
                )
                .build()
''',
    '''            val sourceFactory: MediaSource.Factory = when (playback.extension.lowercase()) {
                "mpd" -> DashMediaSource.Factory(dataSource)
                "m3u8" -> HlsMediaSource.Factory(dataSource)
                else -> DefaultMediaSourceFactory(context).setDataSourceFactory(dataSource)
            }
            ExoPlayer.Builder(context)
                .setMediaSourceFactory(sourceFactory)
                .build()
''',
    "explicit DASH and HLS factories",
)

checks = [
    (gradle, "versionCode = 1007"),
    (gradle, 'versionName = "1.0.7"'),
    (gradle, "minSdk = 25"),
    (gradle, dash),
    (player, "DashMediaSource.Factory(dataSource)"),
    (player, "HlsMediaSource.Factory(dataSource)"),
    (player, "DefaultDataSource.Factory(context, http)"),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing marker {marker} in {path}")
print(f"Android 1.0.7 DASH playback fix applied; Media3 version expression: {version}")

