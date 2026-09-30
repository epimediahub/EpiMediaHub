#!/usr/bin/env python3
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
here = Path(__file__).resolve().parent

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
replace_once(gradle, "versionCode = 1005", "versionCode = 1006", "versionCode")
replace_once(gradle, 'versionName = "1.0.5"', 'versionName = "1.0.6"', "versionName")

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    p = java / relative
    if p.exists():
        p.write_text(p.read_text().replace("1.0.5", "1.0.6"))

shutil.copyfile(here / "V106SmartTubePlayer.kt", java / "ui/V106SmartTubePlayer.kt")

shell = java / "ui/V104SmartTubeShell.kt"

replace_once(
    shell,
    '''    var resolvingId by remember { mutableStateOf<String?>(null) }
    var generation by remember { mutableIntStateOf(0) }
''',
    '''    var resolvingId by remember { mutableStateOf<String?>(null) }
    var activePlayback by remember {
        mutableStateOf<Pair<V100SmartTubeVideo, V100SmartTubePlayback>?>(null)
    }
    var generation by remember { mutableIntStateOf(0) }
''',
    "SmartTube active playback state",
)

old_play = '''            V105SmartTubeCore.resolvePlayback(context, video)
                .onSuccess { playback ->
                    resolvingId = null
                    vm.play(
                        MediaEntry(
                            id = "smarttube:${video.videoId}",
                            name = video.title,
                            kind = MediaKind.MOVIE,
                            categoryId = "smarttube",
                            image = video.image,
                            plot = video.author,
                            streamUrl = playback.url,
                            extension = playback.extension
                        )
                    )
                }
'''
new_play = '''            V105SmartTubeCore.resolvePlayback(context, video)
                .onSuccess { playback ->
                    resolvingId = null
                    activePlayback = video to playback
                }
'''
replace_once(shell, old_play, new_play, "SmartTube dedicated player route")

column_anchor = '''    Column(Modifier.fillMaxSize()) {
'''
replace_once(
    shell,
    column_anchor,
    '''    activePlayback?.let { (video, playback) ->
        V106SmartTubePlayer(
            video = video,
            playback = playback,
            onBack = { activePlayback = null }
        )
        return
    }

    Column(Modifier.fillMaxSize()) {
''',
    "SmartTube player overlay",
)

checks = [
    (gradle, "versionCode = 1006"),
    (gradle, 'versionName = "1.0.6"'),
    (gradle, "minSdk = 25"),
    (shell, "activePlayback = video to playback"),
    (shell, "V106SmartTubePlayer("),
    (java / "ui/V106SmartTubePlayer.kt", "DefaultDataSource.Factory(context, http)"),
    (java / "ui/V106SmartTubePlayer.kt", "SmartTube-Player:"),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing marker {marker} in {path}")

print("Android 1.0.6 isolated SmartTube player patch applied")
