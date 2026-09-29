#!/usr/bin/env python3
"""Android 0.9.7: thematic environments, private labels, national teams and F1 skin worlds."""
import os
import shutil
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
replace_once(gradle, 'versionCode = 906', 'versionCode = 907', 'versionCode')
replace_once(gradle, 'versionName = "0.9.6"', 'versionName = "0.9.7"', 'versionName')

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("0.9.6", "0.9.7"))

src = Path(__file__).with_name("V097SkinEnvironment.kt")
dst = java / "ui/V097SkinEnvironment.kt"
shutil.copyfile(src, dst)

# ---------------------------------------------------------------------------
# Global skin backdrop: football/national teams get stadium atmosphere,
# automotive brands get a premium garage, Formula 1 gets a pit-stop garage.
# Neutral brand/clothing skins keep their existing artwork.
# ---------------------------------------------------------------------------
common = java / "ui/Common.kt"
c = common.read_text()

watermark_anchor = '''        val watermark = remember(themeId) {
            repo.centerMarkRes(themeId).takeIf { it != 0 }
                ?: repo.homeMotifRes(themeId).takeIf { it != 0 }
                ?: repo.markRes(themeId)
        }
'''
if watermark_anchor not in c:
    raise SystemExit("0.9.6 ThemeBackdrop watermark anchor missing")
c = c.replace(
    watermark_anchor,
    watermark_anchor + '''        val skinWorld = remember(themeId, theme?.label, theme?.group) {
            V097SkinWorldFor(themeId, theme?.label.orEmpty(), theme?.group.orEmpty())
        }
''',
    1
)

old_bg = '''            if (bg != 0) {
                Image(
                    painterResource(bg),
                    null,
                    Modifier.fillMaxSize().graphicsLayer {
                        alpha = .46f
                        scaleX = 1.85f
                        scaleY = 1.85f
                        transformOrigin = androidx.compose.ui.graphics.TransformOrigin(0f, .5f)
                    },
                    contentScale = ContentScale.Crop
                )
            }
'''
if old_bg not in c:
    raise SystemExit("0.9.6 ThemeBackdrop background block missing")
c = c.replace(
    old_bg,
    '''            V097SkinEnvironment(skinWorld, accent)

            if (bg != 0 && skinWorld == V097SkinWorld.NEUTRAL) {
                Image(
                    painterResource(bg),
                    null,
                    Modifier.fillMaxSize().graphicsLayer {
                        alpha = .46f
                        scaleX = 1.85f
                        scaleY = 1.85f
                        transformOrigin = androidx.compose.ui.graphics.TransformOrigin(0f, .5f)
                    },
                    contentScale = ContentScale.Crop
                )
            }
''',
    1
)

old_mark = '''            if (watermark != 0) {
                Image(
                    painter = painterResource(watermark),
                    contentDescription = null,
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 8.dp, vertical = 8.dp)
                        .graphicsLayer { alpha = .30f },
                    contentScale = ContentScale.Fit
                )
            }

            content()
'''
if old_mark not in c:
    raise SystemExit("0.9.6 ThemeBackdrop center mark block missing")
c = c.replace(
    old_mark,
    '''            if (watermark != 0) {
                Image(
                    painter = painterResource(watermark),
                    contentDescription = null,
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 8.dp, vertical = 8.dp)
                        .graphicsLayer { alpha = .34f },
                    contentScale = ContentScale.Fit
                )
            } else if (skinWorld != V097SkinWorld.NEUTRAL) {
                V097FallbackSkinMark(
                    themeId = themeId,
                    label = theme?.label.orEmpty(),
                    accent = accent
                )
            }

            content()
''',
    1
)
common.write_text(c)

# ---------------------------------------------------------------------------
# Skin chooser: same themed environments, central mark only, and visible
# wording "Privat" instead of "Family".
# ---------------------------------------------------------------------------
themes = java / "ui/V079Themes.kt"
t = themes.read_text()

if t.count('group.label.uppercase(),') != 1:
    raise SystemExit(f"private group display wording: expected exactly one anchor, found {t.count('group.label.uppercase(),')}")
t = t.replace(
    'group.label.uppercase(),',
    'V097GroupDisplayLabel(group.label).uppercase(),',
    1
)

preview_anchor = '''    val motifRes = vm.themeRepo().centerMarkRes(theme.id).takeIf { it != 0 }
        ?: vm.themeRepo().homeMotifRes(theme.id).takeIf { it != 0 }
        ?: vm.themeRepo().markRes(theme.id)
'''
if preview_anchor not in t:
    raise SystemExit("0.9.6 theme preview motif anchor missing")
t = t.replace(
    preview_anchor,
    preview_anchor + '''    val skinWorld = V097SkinWorldFor(theme.id, theme.label, theme.group)
''',
    1
)

old_preview_bg = '''        if (backgroundRes != 0) {
            Image(
                painterResource(backgroundRes),
                null,
                Modifier.fillMaxSize().graphicsLayer {
                    alpha = .34f
                    scaleX = 1.85f
                    scaleY = 1.85f
                    transformOrigin = androidx.compose.ui.graphics.TransformOrigin(0f, .5f)
                },
                contentScale = ContentScale.Crop
            )
        }
'''
if old_preview_bg not in t:
    raise SystemExit("0.9.6 theme preview background block missing")
t = t.replace(
    old_preview_bg,
    '''        V097SkinEnvironment(skinWorld, themeAccent)
        if (backgroundRes != 0 && skinWorld == V097SkinWorld.NEUTRAL) {
            Image(
                painterResource(backgroundRes),
                null,
                Modifier.fillMaxSize().graphicsLayer {
                    alpha = .34f
                    scaleX = 1.85f
                    scaleY = 1.85f
                    transformOrigin = androidx.compose.ui.graphics.TransformOrigin(0f, .5f)
                },
                contentScale = ContentScale.Crop
            )
        }
''',
    1
)

old_preview_mark = '''        if (motifRes != 0) {
            Image(
                painterResource(motifRes),
                null,
                Modifier.align(Alignment.Center)
                    .fillMaxHeight(.92f)
                    .fillMaxWidth(if (isTv) .56f else .62f)
                    .graphicsLayer { alpha = if (focused) .30f else .22f },
                contentScale = ContentScale.Fit
            )
        }
'''
if old_preview_mark not in t:
    raise SystemExit("0.9.6 theme preview center mark block missing")
t = t.replace(
    old_preview_mark,
    '''        if (motifRes != 0) {
            Image(
                painterResource(motifRes),
                null,
                Modifier.align(Alignment.Center)
                    .fillMaxHeight(.92f)
                    .fillMaxWidth(if (isTv) .56f else .62f)
                    .graphicsLayer { alpha = if (focused) .34f else .26f },
                contentScale = ContentScale.Fit
            )
        } else if (skinWorld != V097SkinWorld.NEUTRAL) {
            V097FallbackSkinMark(
                themeId = theme.id,
                label = theme.label,
                accent = themeAccent,
                compact = true
            )
        }
''',
    1
)

t = t.replace(
    '''                    theme.label,
                    color = Color.White,''',
    '''                    V097PrivateDisplayLabel(theme.label, privateTheme),
                    color = Color.White,''',
    1
)
t = t.replace('privateTheme -> "PRIVATE · FREIGESCHALTET"', 'privateTheme -> "PRIVAT · FREIGESCHALTET"', 1)
themes.write_text(t)

checks = [
    (gradle, 'versionCode = 907'),
    (gradle, 'versionName = "0.9.7"'),
    (dst, 'enum class V097SkinWorld'),
    (dst, 'V097SkinWorld.PIT_GARAGE'),
    (dst, 'V097PrivateDisplayLabel'),
    (common, 'V097SkinEnvironment(skinWorld, accent)'),
    (common, 'V097FallbackSkinMark('),
    (themes, 'V097GroupDisplayLabel(group.label)'),
    (themes, 'V097PrivateDisplayLabel(theme.label, privateTheme)'),
    (themes, '"PRIVAT · FREIGESCHALTET"'),
    (themes, 'V097SkinEnvironment(skinWorld, themeAccent)'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"Android 0.9.7 marker missing in {path}: {marker}")

print("Android 0.9.7 thematic stadium/garage/pit skins and Privat labels applied")
