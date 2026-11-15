#!/usr/bin/env python3
"""Android 0.8.9: keep Fire TV / Android TV awake while the EpiMediaHub player is open."""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"

def change(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise SystemExit(f"Expected exactly one anchor in {path}: {old[:100]}")
    path.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
change(gradle, 'versionCode = 808', 'versionCode = 809')
change(gradle, 'versionName = "0.8.8"', 'versionName = "0.8.9"')

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("0.8.8", "0.8.9"))

player = java / "ui/PlayerScreen.kt"
s = player.read_text()

import_anchor = 'import androidx.compose.ui.platform.LocalContext\n'
if import_anchor not in s:
    raise SystemExit("PlayerScreen LocalContext import missing")
if 'import androidx.compose.ui.platform.LocalView\n' not in s:
    s = s.replace(import_anchor, import_anchor + 'import androidx.compose.ui.platform.LocalView\n', 1)

signature = 'fun PlayerScreen(vm: MainViewModel, item: MediaEntry, episodeList: List<MediaEntry>, accent: Color, isTv: Boolean) {\n'
if s.count(signature) != 1:
    raise SystemExit(f"PlayerScreen signature count was {s.count(signature)}, expected 1")

awake = '''fun PlayerScreen(vm: MainViewModel, item: MediaEntry, episodeList: List<MediaEntry>, accent: Color, isTv: Boolean) {
    // Fire OS / Android TV may start its system screensaver even while video is
    // actively rendered. The root player owns this flag so it also survives a
    // Media3 <-> VLC compatibility-player switch. Leaving PlayerScreen restores
    // the previous setting automatically.
    val keepAwakeView = LocalView.current
    DisposableEffect(keepAwakeView) {
        val previousKeepScreenOn = keepAwakeView.keepScreenOn
        keepAwakeView.keepScreenOn = true
        onDispose { keepAwakeView.keepScreenOn = previousKeepScreenOn }
    }
'''
s = s.replace(signature, awake, 1)
player.write_text(s)

checks = [
    (gradle, 'versionCode = 809'),
    (gradle, 'versionName = "0.8.9"'),
    (player, 'val keepAwakeView = LocalView.current'),
    (player, 'keepAwakeView.keepScreenOn = true'),
    (player, 'onDispose { keepAwakeView.keepScreenOn = previousKeepScreenOn }'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"Android 0.8.9 marker missing in {path}: {marker}")

print("Android 0.8.9 Fire TV / Android TV player wake lock applied")
