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
replace_once(gradle, "versionCode = 1007", "versionCode = 1008", "versionCode")
replace_once(gradle, 'versionName = "1.0.7"', 'versionName = "1.0.8"', "versionName")

for relative in (
    "ui/Screens.kt",
    "ui/V078DashboardPairingGate.kt",
    "ui/V083Home.kt",
    "data/V070WeatherClient.kt",
    "ui/V106SmartTubePlayer.kt",
):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("1.0.7", "1.0.8"))

shutil.copyfile(here / "V108SmartTubeCore.kt", java / "ui/V108SmartTubeCore.kt")
shutil.copyfile(here / "V108SmartTubeShell.kt", java / "ui/V108SmartTubeShell.kt")

home = java / "ui/V083Home.kt"
replace_once(
    home,
    "        V104SmartTubeShell(\n",
    "        V108SmartTubeShell(\n",
    "SmartTube 1.0.8 shell route",
)

checks = [
    (gradle, "versionCode = 1008"),
    (gradle, 'versionName = "1.0.8"'),
    (gradle, "minSdk = 25"),
    (home, "V108SmartTubeShell("),
    (java / "ui/V108SmartTubeCore.kt", "V108SmartTubeSection"),
    (java / "ui/V108SmartTubeCore.kt", "getTrendingObserve().blockingFirst()"),
    (java / "ui/V108SmartTubeShell.kt", "V108SmartTubeSidebar("),
    (java / "ui/V108SmartTubeShell.kt", "V108TopAction("),
    (java / "ui/V108SmartTubeShell.kt", "if (focused) 2.dp else 1.dp"),
    (java / "ui/V108SmartTubeShell.kt", "V106SmartTubePlayer("),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing marker {marker} in {path}")

print("Android 1.0.8 SmartTube navigation and focus UI applied")
