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
replace_once(gradle, "versionCode = 1010", "versionCode = 1011", "versionCode")
replace_once(gradle, 'versionName = "1.0.10"', 'versionName = "1.0.11"', "versionName")

for relative in (
    "ui/Screens.kt",
    "ui/V078DashboardPairingGate.kt",
    "ui/V083Home.kt",
    "data/V070WeatherClient.kt",
):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("1.0.10", "1.0.11"))

shutil.copyfile(here / "V111SmartTubeShell.kt", java / "ui/V111SmartTubeShell.kt")
shutil.copyfile(here / "V111SmartTubePlayer.kt", java / "ui/V111SmartTubePlayer.kt")
shutil.copyfile(here / "V111MenuMemory.kt", java / "ui/V111MenuMemory.kt")

home = java / "ui/V083Home.kt"
replace_once(
    home,
    "        V110SmartTubeShell(\n",
    "        V111SmartTubeShell(\n",
    "SmartTube 1.0.11 shell route",
)

checks = [
    (gradle, "versionCode = 1011"),
    (gradle, 'versionName = "1.0.11"'),
    (home, "V111SmartTubeShell("),
    (java / "ui/V111SmartTubeShell.kt", "V097SkinEnvironment(smartTubeSkinWorld, accent)"),
    (java / "ui/V111SmartTubeShell.kt", "V111SmartTubeSidebar("),
    (java / "ui/V111SmartTubeShell.kt", "V111SmartTubeVideoCard("),
    (java / "ui/V111SmartTubePlayer.kt", "fontSize = if (isTv) 30.sp"),
    (java / "ui/V111SmartTubePlayer.kt", "v111FormatPlaybackTime"),
    (java / "ui/V111MenuMemory.kt", "internal object V111MenuMemory"),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing marker {marker} in {path}")

print("Android 1.0.11 SmartTube YouTube-style UI, visible skin and large player overlay applied")
