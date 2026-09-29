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
replace_once(gradle, "versionCode = 1003", "versionCode = 1004", "versionCode")
replace_once(gradle, 'versionName = "1.0.3"', 'versionName = "1.0.4"', "versionName")

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    p = java / relative
    if p.exists():
        p.write_text(p.read_text().replace("1.0.3", "1.0.4"))

shutil.copyfile(here / "V104SmartTubeCore.kt", java / "ui/V104SmartTubeCore.kt")
shutil.copyfile(here / "V104SmartTubeShell.kt", java / "ui/V104SmartTubeShell.kt")

home = java / "ui/V083Home.kt"
replace_once(
    home,
    "        V100SmartTubeShell(\n",
    "        V104SmartTubeShell(\n",
    "SmartTube shell route",
)

checks = [
    (gradle, "versionCode = 1004"),
    (gradle, 'versionName = "1.0.4"'),
    (gradle, "minSdk = 25"),
    (java / "ui/V104SmartTubeCore.kt", "signInObserve"),
    (java / "ui/V104SmartTubeCore.kt", "fallbackRows"),
    (java / "ui/V104SmartTubeCore.kt", "createMpdStream"),
    (java / "ui/V104SmartTubeShell.kt", "https://yt.be/activate"),
    (java / "ui/V104SmartTubeShell.kt", "V104SmartTubeCore.resolvePlayback"),
    (home, "V104SmartTubeShell("),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing marker {marker} in {path}")

print("Android 1.0.4 SmartTube account/home/playback patch applied")
