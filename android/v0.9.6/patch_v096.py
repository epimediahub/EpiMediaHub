#!/usr/bin/env python3
"""Android 0.9.6: remove the recurring small right-side logo from every skin."""
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
replace_once(gradle, 'versionCode = 905', 'versionCode = 906', 'versionCode')
replace_once(gradle, 'versionName = "0.9.5"', 'versionName = "0.9.6"', 'versionName')

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("0.9.5", "0.9.6"))

# ---------------------------------------------------------------------------
# Runtime skin background:
# The imported Enigma backgrounds already contain the small mark on the right.
# Use only the clean left portion of the artwork by zooming from the left edge.
# The separately supplied center mark remains the ONE visible skin logo.
# ---------------------------------------------------------------------------
common = java / "ui/Common.kt"
replace_once(
    common,
    'Modifier.fillMaxSize().graphicsLayer { alpha = .46f },',
    '''Modifier.fillMaxSize().graphicsLayer {
                        alpha = .46f
                        scaleX = 1.85f
                        scaleY = 1.85f
                        transformOrigin = androidx.compose.ui.graphics.TransformOrigin(0f, .5f)
                    },''',
    'crop embedded right-side background logo'
)

# ---------------------------------------------------------------------------
# Theme picker preview must follow the same rule: clean background + one
# centered mark, never a second small mark aligned to the right.
# ---------------------------------------------------------------------------
themes = java / "ui/V079Themes.kt"

replace_once(
    themes,
    '''    val motifRes = vm.themeRepo().homeMotifRes(theme.id).takeIf { it != 0 }
        ?: vm.themeRepo().markRes(theme.id)
''',
    '''    val motifRes = vm.themeRepo().centerMarkRes(theme.id).takeIf { it != 0 }
        ?: vm.themeRepo().homeMotifRes(theme.id).takeIf { it != 0 }
        ?: vm.themeRepo().markRes(theme.id)
''',
    'theme preview center mark priority'
)

replace_once(
    themes,
    '''                Modifier.fillMaxSize().graphicsLayer { alpha = .28f },
                contentScale = ContentScale.Crop''',
    '''                Modifier.fillMaxSize().graphicsLayer {
                    alpha = .34f
                    scaleX = 1.85f
                    scaleY = 1.85f
                    transformOrigin = androidx.compose.ui.graphics.TransformOrigin(0f, .5f)
                },
                contentScale = ContentScale.Crop''',
    'theme preview background crop'
)

replace_once(
    themes,
    '''                Modifier.align(Alignment.CenterEnd)
                    .fillMaxHeight(.88f)
                    .fillMaxWidth(if (isTv) .38f else .42f)
                    .padding(end = if (isTv) 18.dp else 8.dp)
                    .graphicsLayer { alpha = if (focused) .18f else .095f },
                contentScale = ContentScale.Fit''',
    '''                Modifier.align(Alignment.Center)
                    .fillMaxHeight(.92f)
                    .fillMaxWidth(if (isTv) .56f else .62f)
                    .graphicsLayer { alpha = if (focused) .30f else .22f },
                contentScale = ContentScale.Fit''',
    'theme preview centered single logo'
)

checks = [
    (gradle, 'versionCode = 906'),
    (gradle, 'versionName = "0.9.6"'),
    (common, 'scaleX = 1.85f'),
    (common, 'TransformOrigin(0f, .5f)'),
    (themes, 'vm.themeRepo().centerMarkRes(theme.id)'),
    (themes, 'Modifier.align(Alignment.Center)'),
    (themes, '.graphicsLayer { alpha = if (focused) .30f else .22f }'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"Android 0.9.6 marker missing in {path}: {marker}")

if 'Modifier.align(Alignment.CenterEnd)\n                    .fillMaxHeight(.88f)' in themes.read_text():
    raise SystemExit("Android 0.9.6 still renders the theme preview logo on the right")

print("Android 0.9.6 single centered skin logo applied")
