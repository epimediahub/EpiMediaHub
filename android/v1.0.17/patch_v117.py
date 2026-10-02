#!/usr/bin/env python3
"""Fit VOD controls, focus skip-intro and count down within verified terminal credits."""
import os
import shutil
from pathlib import Path

root = Path(os.environ['PROJECT_ROOT'])
java = root / 'app/src/main/java/de/epimediahub/app'
here = Path(__file__).resolve().parent
gradle = root / 'app/build.gradle.kts'
s = gradle.read_text()
assert s.count('versionCode = 1016') == 1 and s.count('versionName = "1.0.16"') == 1
gradle.write_text(s.replace('versionCode = 1016', 'versionCode = 1017').replace('versionName = "1.0.16"', 'versionName = "1.0.17"'))
for p in java.rglob('*.kt'):
    value = p.read_text()
    if '1.0.16' in value:
        p.write_text(value.replace('1.0.16', '1.0.17'))

shutil.copyfile(here / 'V117PlayerChrome.kt', java / 'ui/V115PlayerChrome.kt')
shutil.copyfile(here / 'V117NextEpisode.kt', java / 'ui/V117NextEpisode.kt')

hub = java / 'ui/V060CinematicHub.kt'
s = hub.read_text()
def replace_once(old, new):
    global s
    assert s.count(old) == 1, old
    s = s.replace(old, new, 1)

# The same rail is shared by films and series. Rows remain opaque even on bright skins.
replace_once('private fun V071CategoryRail(', 'internal fun V071CategoryRail(')
replace_once('Modifier.width(226.dp).fillMaxHeight().background(Color.Black.copy(.18f))',
             'Modifier.width(226.dp).fillMaxHeight().background(Color(0xF50B111C)).testTag("vod-category-rail")')
replace_once('Text("KATEGORIEN", color = Color.White.copy(.55f)', 'Text("KATEGORIEN", color = Color.White.copy(.88f)')
replace_once('private fun V071CategoryRailItem(', 'internal fun V071CategoryRailItem(')
replace_once('            focused -> accent.copy(.22f)\n            selected -> accent.copy(.13f)\n            else -> Color.Transparent',
             '            focused -> accent.copy(.35f).compositeOver(Color(0xFF172230))\n            selected -> accent.copy(.22f).compositeOver(Color(0xFF172230))\n            else -> Color(0xFF141D29)')
replace_once('color = if (focused || selected) Color.White else Color.White.copy(.72f)',
             'color = if (focused || selected) Color.White else Color.White.copy(.96f)')
replace_once('import androidx.compose.ui.graphics.Color\n', 'import androidx.compose.ui.graphics.Color\nimport androidx.compose.ui.graphics.compositeOver\nimport androidx.compose.ui.platform.testTag\n')
hub.write_text(s)

# The tools button is fully visible now, so the existing regression test no
# longer needs the removed horizontal scroll parent to reach it.
editor_test = root / 'app/src/test/java/de/epimediahub/app/ui/V116SkipEditorTest.kt'
value = editor_test.read_text()
old = 'onNodeWithTag("vod-skip-tools").performScrollTo().performClick()'
assert value.count(old) == 1
editor_test.write_text(value.replace(old, 'onNodeWithTag("vod-skip-tools").assertIsDisplayed().performClick()'))

for filename in ('V117PlayerTest.kt', 'V117NextEpisodeTest.kt', 'V117CategoryTest.kt'):
    source = here / filename
    if source.exists():
        destination = root / 'app/src/test/java/de/epimediahub/app/ui' / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
print('Android 1.0.17: fitted controls, automatic intro focus, opaque categories and credits countdown installed')
