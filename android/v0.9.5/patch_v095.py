#!/usr/bin/env python3
"""Android 0.9.5: stronger default skin visibility across the app."""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 904', 'versionCode = 905', 'versionCode')
replace_once(gradle, 'versionName = "0.9.4"', 'versionName = "0.9.5"', 'versionName')

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("0.9.4", "0.9.5"))

common = java / "ui/Common.kt"
c = common.read_text()

# Let the actual full-screen theme artwork show through much more clearly.
replace_once(
    common,
    'Modifier.fillMaxSize().graphicsLayer { alpha = .22f },',
    'Modifier.fillMaxSize().graphicsLayer { alpha = .46f },',
    'theme background alpha'
)

# Keep text readable while avoiding the nearly-black veil used before.
replace_once(
    common,
    '''                        listOf(
                            Color(0xB804080D),
                            Color(0xD8080D14),
                            Color(0xF205080D)
                        )''',
    '''                        listOf(
                            Color(0x7604080D),
                            Color(0x9E080D14),
                            Color(0xC805080D)
                        )''',
    'theme dark overlay'
)

replace_once(
    common,
    'listOf(accent.copy(.12f), Color.Transparent),',
    'listOf(accent.copy(.16f), Color.Transparent),',
    'theme accent glow'
)

# The logo/skin motif is intentionally obvious by default now.
replace_once(
    common,
    '''                        .padding(horizontal = 24.dp, vertical = 20.dp)
                        .graphicsLayer { alpha = .11f },''',
    '''                        .padding(horizontal = 8.dp, vertical = 8.dp)
                        .graphicsLayer { alpha = .30f },''',
    'watermark visibility'
)

checks = [
    (gradle, 'versionCode = 905'),
    (gradle, 'versionName = "0.9.5"'),
    (common, 'alpha = .46f'),
    (common, 'Color(0x7604080D)'),
    (common, 'Color(0x9E080D14)'),
    (common, 'Color(0xC805080D)'),
    (common, 'accent.copy(.16f)'),
    (common, '.graphicsLayer { alpha = .30f }'),
    (common, '.padding(horizontal = 8.dp, vertical = 8.dp)'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"Android 0.9.5 marker missing in {path}: {marker}")

print("Android 0.9.5 stronger default skin visibility applied")
