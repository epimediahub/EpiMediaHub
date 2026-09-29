#!/usr/bin/env python3
"""Android 0.9.4: full-screen global skin watermark."""
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
replace_once(gradle, 'versionCode = 903', 'versionCode = 904', 'versionCode')
replace_once(gradle, 'versionName = "0.9.3"', 'versionName = "0.9.4"', 'versionName')

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("0.9.3", "0.9.4"))

# ---------------------------------------------------------------------------
# One full-screen watermark across the complete app.
# ---------------------------------------------------------------------------
common = java / "ui/Common.kt"
c = common.read_text()

bg_anchor = '''        val bg = remember(themeId) { repo.backgroundRes(themeId) }
'''
if bg_anchor not in c:
    raise SystemExit("ThemeBackdrop background anchor missing")
c = c.replace(
    bg_anchor,
    bg_anchor + '''        val watermark = remember(themeId) {
            repo.centerMarkRes(themeId).takeIf { it != 0 }
                ?: repo.homeMotifRes(themeId).takeIf { it != 0 }
                ?: repo.markRes(themeId)
        }
''',
    1,
)

radial_anchor = '''            Box(
                Modifier.fillMaxSize().background(
                    Brush.radialGradient(
                        listOf(accent.copy(.12f), Color.Transparent),
                        radius = 980f
                    )
                )
            )

            content()
'''
if radial_anchor not in c:
    raise SystemExit("ThemeBackdrop radial/content anchor missing")
c = c.replace(
    radial_anchor,
    '''            Box(
                Modifier.fillMaxSize().background(
                    Brush.radialGradient(
                        listOf(accent.copy(.12f), Color.Transparent),
                        radius = 980f
                    )
                )
            )

            if (watermark != 0) {
                Image(
                    painter = painterResource(watermark),
                    contentDescription = null,
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 24.dp, vertical = 20.dp)
                        .graphicsLayer { alpha = .11f },
                    contentScale = ContentScale.Fit
                )
            }

            content()
''',
    1,
)
common.write_text(c)

# ---------------------------------------------------------------------------
# Home no longer paints a second strong motif behind the tile grid.
# The global ThemeBackdrop is now the single source of skin artwork.
# ---------------------------------------------------------------------------
home = java / "ui/V083Home.kt"
h = home.read_text()

motif_state = '''    val skinMotif = remember(u.themeId) {
        vm.themeRepo().centerMarkRes(u.themeId).takeIf { it != 0 }
            ?: vm.themeRepo().homeMotifRes(u.themeId).takeIf { it != 0 }
            ?: vm.themeRepo().markRes(u.themeId)
    }

'''
if motif_state not in h:
    raise SystemExit("V083 home skin motif state anchor missing")
h = h.replace(motif_state, "", 1)

motif_block = '''                // One continuous skin motif behind the whole grid.
                // It is NOT repeated per tile. Semi-transparent tile surfaces
                // reveal different parts of the same centered artwork.
                if (skinMotif != 0) {
                    Image(
                        painterResource(skinMotif),
                        null,
                        Modifier.align(Alignment.Center)
                            .fillMaxWidth(if (isTv) .67f else .82f)
                            .fillMaxHeight(if (isTv) 1f else .98f)
                            .graphicsLayer { alpha = if (isTv) .64f else .72f },
                        contentScale = ContentScale.Fit
                    )
                }

'''
if motif_block not in h:
    raise SystemExit("V083 home motif rendering anchor missing")
h = h.replace(
    motif_block,
    '''                // Skin artwork is rendered once by ThemeBackdrop as a
                // full-screen watermark behind the complete app.

''',
    1,
)
home.write_text(h)

checks = [
    (gradle, 'versionCode = 904'),
    (gradle, 'versionName = "0.9.4"'),
    (common, 'val watermark = remember(themeId)'),
    (common, 'repo.centerMarkRes(themeId)'),
    (common, '.fillMaxSize()'),
    (common, '.graphicsLayer { alpha = .11f }'),
    (home, 'full-screen watermark behind the complete app'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"Android 0.9.4 marker missing in {path}: {marker}")

if 'val skinMotif = remember(u.themeId)' in home.read_text():
    raise SystemExit("Android 0.9.4 home still contains duplicate skin motif state")
if 'alpha = if (isTv) .64f else .72f' in home.read_text():
    raise SystemExit("Android 0.9.4 home still contains duplicate strong motif")

print("Android 0.9.4 full-screen global skin watermark applied")
