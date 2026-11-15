#!/usr/bin/env python3
from pathlib import Path
import os
import shutil

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))

# Version metadata.
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 704', 'versionCode = 705', 'versionCode')
replace_once(gradle, 'versionName = "0.7.4"', 'versionName = "0.7.5"', 'versionName')

home = java / "ui/V070Home.kt"
if home.exists():
    home.write_text(home.read_text().replace("0.7.4", "0.7.5"))

weather = java / "data/V070WeatherClient.kt"
if weather.exists():
    weather.write_text(weather.read_text().replace("EpiMediaHub-Android/0.7.4", "EpiMediaHub-Android/0.7.5"))

screens = java / "ui/Screens.kt"
if screens.exists():
    screens.write_text(screens.read_text().replace("Android v0.7.0", "Android v0.7.5"))

# Shared responsive Live-TV UI for TV + mobile.
src = Path(__file__).with_name("V075LiveTv.kt")
dst = java / "ui/V075LiveTv.kt"
shutil.copyfile(src, dst)

# Route LIVE to the dedicated three-pane receiver-style screen.
app = java / "EpiMediaHubApp.kt"
old_route = 'is Screen.Categories -> if (s.kind == de.epimediahub.app.model.MediaKind.MOVIE || s.kind == de.epimediahub.app.model.MediaKind.SERIES || s.kind == de.epimediahub.app.model.MediaKind.LIVE) V060CinematicHubScreen(vm, s.kind, accent, isTv) else CategoryScreen(vm, s.kind, accent, isTv)'
new_route = 'is Screen.Categories -> when { s.kind == de.epimediahub.app.model.MediaKind.LIVE -> V075LiveTvScreen(vm, accent, isTv); s.kind == de.epimediahub.app.model.MediaKind.MOVIE || s.kind == de.epimediahub.app.model.MediaKind.SERIES -> V060CinematicHubScreen(vm, s.kind, accent, isTv); else -> CategoryScreen(vm, s.kind, accent, isTv) }'
replace_once(app, old_route, new_route, 'Live TV route')

checks = [
    (gradle, 'versionName = "0.7.5"'),
    (gradle, 'versionCode = 705'),
    (dst, 'fun V075LiveTvScreen'),
    (dst, 'V075CategoryPane'),
    (dst, 'V075ChannelPane'),
    (dst, 'V075InfoPane'),
    (dst, 'val wide = isTv || maxWidth >= 760.dp'),
    (app, 'V075LiveTvScreen(vm, accent, isTv)'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing v0.7.5 marker {marker} in {path}")

print("Android v0.7.5 shared TV/mobile receiver-style Live TV UI applied")
