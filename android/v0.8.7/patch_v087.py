#!/usr/bin/env python3
"""Advance the update version after correcting the release metadata."""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
gradle = root / "app/build.gradle.kts"
value = gradle.read_text()
assert value.count('versionCode = 806') == 1
assert value.count('versionName = "0.8.6"') == 1
gradle.write_text(value.replace('versionCode = 806', 'versionCode = 807')
                 .replace('versionName = "0.8.6"', 'versionName = "0.8.7"'))
base = root / "app/src/main/java/de/epimediahub/app"
for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    path = base / relative
    if path.exists():
        path.write_text(path.read_text().replace("0.8.6", "0.8.7"))
print("Android 0.8.7 updater metadata applied")
