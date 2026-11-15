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
replace_once(gradle, "versionCode = 1009", "versionCode = 1010", "versionCode")
replace_once(gradle, 'versionName = "1.0.9"', 'versionName = "1.0.10"', "versionName")

for relative in (
    "ui/Screens.kt",
    "ui/V078DashboardPairingGate.kt",
    "ui/V083Home.kt",
    "data/V070WeatherClient.kt",
):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("1.0.9", "1.0.10"))

shutil.copyfile(here / "V110SmartTubeShell.kt", java / "ui/V110SmartTubeShell.kt")
shutil.copyfile(here / "V110SmartTubePlayer.kt", java / "ui/V110SmartTubePlayer.kt")

home = java / "ui/V083Home.kt"
replace_once(
    home,
    "        V108SmartTubeShell(\n",
    "        V110SmartTubeShell(\n",
    "SmartTube 1.0.10 shell route",
)

checks = [
    (gradle, "versionCode = 1010"),
    (gradle, 'versionName = "1.0.10"'),
    (gradle, "minSdk = 25"),
    (home, "V110SmartTubeShell("),
    (java / "ui/V110SmartTubeShell.kt", "filterNot { it == V108SmartTubeSection.TRENDING }"),
    (java / "ui/V110SmartTubeShell.kt", "smartTubeBackgroundRes"),
    (java / "ui/V110SmartTubeShell.kt", "smartTubeMotifRes"),
    (java / "ui/V110SmartTubeShell.kt", "V110TvKeyboardDialog("),
    (java / "ui/V110SmartTubeShell.kt", "nextVideoAfter(video)"),
    (java / "ui/V110SmartTubePlayer.kt", "Player.STATE_ENDED"),
    (java / "ui/V110SmartTubePlayer.kt", "onEnded()"),
    (java / "ui/V110SmartTubePlayer.kt", "DashMediaSource.Factory(dataSource)"),
    (java / "ui/V110SmartTubePlayer.kt", "HlsMediaSource.Factory(dataSource)"),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing marker {marker} in {path}")

print("Android 1.0.10 SmartTube skin, autoplay and legacy Fire TV search fixes applied")
