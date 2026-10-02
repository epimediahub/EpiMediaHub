#!/usr/bin/env python3
"""Clean player titles and show/focus the next-episode card at 40 seconds remaining."""
import os
from pathlib import Path
import shutil

root = Path(os.environ['PROJECT_ROOT'])
java = root / 'app/src/main/java/de/epimediahub/app'
here = Path(__file__).resolve().parent
gradle = root / 'app/build.gradle.kts'
s = gradle.read_text()
assert s.count('versionCode = 1017') == 1 and s.count('versionName = "1.0.17"') == 1
gradle.write_text(s.replace('versionCode = 1017', 'versionCode = 1018').replace('versionName = "1.0.17"', 'versionName = "1.0.18"'))
for path in java.rglob('*.kt'):
    s = path.read_text()
    if '1.0.17' in s:
        path.write_text(s.replace('1.0.17', '1.0.18'))
for filename in ('V118Names.kt', 'V118NextEpisode.kt'):
    shutil.copyfile(here / filename, java / 'ui' / filename)

chrome = java / 'ui/V115PlayerChrome.kt'
s = chrome.read_text()
def replace_once(old, new):
    global s
    assert s.count(old) == 1, old
    s = s.replace(old, new, 1)

replace_once('    val nextFocus = remember(item.resumeKey) { FocusRequester() }',
             '    val nextFocus = remember(item.resumeKey) { FocusRequester() }\n    val nextCardFocus = remember(item.resumeKey) { FocusRequester() }')
replace_once('    var focusedIntro by remember(item.resumeKey) { mutableStateOf<String?>(null) }',
             '    var focusedIntro by remember(item.resumeKey) { mutableStateOf<String?>(null) }\n    var focusedNext by remember(item.resumeKey) { mutableStateOf(false) }')
replace_once('v117NextWindow(state.durationMs, segments)', 'v118NextWindow(state.durationMs)')
replace_once('    LaunchedEffect(controls, dialog, restore, introKey, isTv) {\n        if (isTv && dialog == null) {',
             '    LaunchedEffect(controls, dialog, restore, introKey, isTv) {\n        if (isTv && dialog == null) {\n            if (!controls && nextVisible) return@LaunchedEffect')
replace_once('"audio" -> audioFocus; "episodes" -> episodesFocus; "next" -> nextFocus; "skip" -> skipFocus; else -> playFocus',
             '"audio" -> audioFocus; "episodes" -> episodesFocus; "next" -> nextFocus; "next-card" -> if (nextVisible) nextCardFocus else playFocus; "skip" -> skipFocus; else -> playFocus')
anchor = '    LaunchedEffect(nextVisible, nextWindow, state.positionMs, state.playing, state.ended,'
replace_once(anchor, '''    LaunchedEffect(nextVisible, dialog, isTv) {
        if (!nextVisible) {
            focusedNext = false
            if (restore == "next-card") restore = "play"
        } else if (isTv && dialog == null && !focusedNext && !advanced) {
            restore = "next-card"
            inputMode.requestInputMode(InputMode.Keyboard)
            delay(120L)
            if (runCatching { nextCardFocus.requestFocus(); true }.getOrDefault(false)) focusedNext = true
        }
    }
''' + anchor)
replace_once('''        val target = nextTargetMs ?: if (nextWindow?.credits == true)
            (state.positionMs + 10_000L).coerceAtMost(state.durationMs) else state.durationMs''',
             '        val target = nextTargetMs ?: v118NextTarget(state.positionMs, state.durationMs)')
replace_once('        if (state.ended) { restore = if (next != null) "next" else "play"; controls = true }',
             '        if (state.ended) { if (!focusedNext) restore = if (next != null) "next-card" else "play"; controls = true }')
replace_once('Text(if (item.kind == MediaKind.EPISODE) item.categoryId.ifBlank { "Serie" } else item.name,',
             'Text(if (item.kind == MediaKind.EPISODE) V118Names.display(item.categoryId).ifBlank { "Serie" } else V118Names.display(item.name),')
replace_once('Text("Staffel ${item.season} · Folge ${item.episode} · ${item.name}",',
             'Text(V118Names.subtitle(item.name, item.categoryId, item.season, item.episode),')
replace_once('Text("Staffel ${next.season} · Folge ${next.episode} · ${next.name}",',
             'Text(V118Names.subtitle(next.name, item.categoryId, next.season, next.episode),')
assert s.count('.v114FocusRing().testTag("vod-card-next")') == 2
s = s.replace('.v114FocusRing().testTag("vod-card-next")', '.focusRequester(nextCardFocus).v114FocusRing().testTag("vod-card-next")')
replace_once('code in listOf(KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN) && (!controls || rootFocused)',
             'code in listOf(KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN) && (rootFocused || (!controls && !nextVisible))')
replace_once('code == KeyEvent.KEYCODE_DPAD_LEFT && !controls ->',
             'code == KeyEvent.KEYCODE_DPAD_LEFT && !controls && (!nextVisible || rootFocused) ->')
replace_once('code == KeyEvent.KEYCODE_DPAD_RIGHT && !controls ->',
             'code == KeyEvent.KEYCODE_DPAD_RIGHT && !controls && (!nextVisible || rootFocused) ->')
chrome.write_text(s)

tests = root / 'app/src/test/java/de/epimediahub/app/ui'
# Replace the previous UI expectations for the now deliberately changed timing.
(tests / 'V117PlayerTest.kt').unlink()
for filename in ('V118NamesTest.kt', 'V118NextEpisodeTest.kt', 'V118PlayerTest.kt'):
    shutil.copyfile(here / filename, tests / filename)
print('Android 1.0.18: clean player titles, fixed 40-second next-episode window and automatic TV focus installed')
