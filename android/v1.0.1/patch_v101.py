#!/usr/bin/env python3
"""Android 1.0.1 compatibility patch.

- Restores Fire OS 6 / Android 7.1 (API 25) installation support.
- Adds a central category-management entry under Settings.
"""
import os
import re
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
here = Path(__file__).resolve().parent

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
g = gradle.read_text()
if g.count("versionCode = 1000") != 1:
    raise SystemExit("versionCode 1000 anchor missing")
if g.count('versionName = "1.0.0"') != 1:
    raise SystemExit("versionName 1.0.0 anchor missing")
g = g.replace("versionCode = 1000", "versionCode = 1001", 1)
g = g.replace('versionName = "1.0.0"', 'versionName = "1.0.1"', 1)
g, count = re.subn(r'\bminSdk\s*=\s*26\b', 'minSdk = 25', g, count=1)
if count != 1:
    raise SystemExit("minSdk 26 anchor missing")
gradle.write_text(g)

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    p = java / relative
    if p.exists():
        p.write_text(p.read_text().replace("1.0.0", "1.0.1"))

shutil.copyfile(here / "V101CategorySettings.kt", java / "ui/V101CategorySettings.kt")

vm = java / "MainViewModel.kt"
replace_once(
    vm,
    "    data object Settings : Screen\n",
    "    data object Settings : Screen\n    data object CategorySettings : Screen\n",
    "CategorySettings screen route",
)

app = java / "EpiMediaHubApp.kt"
replace_once(
    app,
    "                Screen.Settings -> SettingsScreen(vm, accent)\n",
    "                Screen.Settings -> SettingsScreen(vm, accent)\n"
    "                Screen.CategorySettings -> V101CategorySettingsScreen(vm, accent, isTv)\n",
    "CategorySettings app route",
)

screens = java / "ui/Screens.kt"
settings_anchor = '''            item{FocusCard("Playlists verwalten","${u.playlists.size} gespeichert",R.drawable.icon_playlist,accent=accent,onClick={vm.navigate(Screen.Playlists)})}
'''
if settings_anchor not in screens.read_text():
    raise SystemExit("Settings playlist card anchor missing")
replace_once(
    screens,
    settings_anchor,
    settings_anchor +
    '''            item{FocusCard("Kategorien verwalten","Live TV · Filme · Serien",R.drawable.icon_live,accent=accent,onClick={vm.navigate(Screen.CategorySettings)})}
''',
    "Settings category card",
)

checks = [
    (gradle, 'versionCode = 1001'),
    (gradle, 'versionName = "1.0.1"'),
    (gradle, 'minSdk = 25'),
    (java / "MainViewModel.kt", 'data object CategorySettings : Screen'),
    (java / "EpiMediaHubApp.kt", 'Screen.CategorySettings -> V101CategorySettingsScreen'),
    (java / "ui/Screens.kt", '"Kategorien verwalten"'),
    (java / "ui/V101CategorySettings.kt", 'fun V101CategorySettingsScreen'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"Android 1.0.1 marker missing in {path}: {marker}")

print("Android 1.0.1 Fire OS 6 compatibility + settings category manager applied")
