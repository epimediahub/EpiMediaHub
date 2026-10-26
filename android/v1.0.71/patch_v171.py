#!/usr/bin/env python3
"""v171: focusable Skip Outro / Next Episode with safe remote navigation.

The fullscreen player currently captures horizontal remote presses as seeks
even while a child skip button has the focus and its control overlay is hidden.
Keep the live and Cinema cadence policies from v170 untouched.
"""
import os
from pathlib import Path
import shutil

root=Path(os.environ["PROJECT_ROOT"])
here=Path(__file__).resolve().parent
app=root/"app"
ui=app/"src/main/java/de/epimediahub/app/ui"
tests=app/"src/test/java/de/epimediahub/app/ui"

def replace(path, old, new):
    text=path.read_text()
    count=text.count(old)
    if count!=1:
        raise SystemExit(f"v171 expected single anchor in {path}, got {count}: {old[:100]}")
    path.write_text(text.replace(old,new,1))

gradle=app/"build.gradle.kts"
replace(gradle,"versionCode = 1070","versionCode = 1071")
replace(gradle,'versionName = "1.0.70"','versionName = "1.0.71"')

chrome=ui/"V115PlayerChrome.kt"
replace(chrome,"import androidx.compose.ui.focus.focusRequester",
    "import androidx.compose.ui.focus.focusRequester\nimport androidx.compose.ui.focus.focusProperties")
replace(chrome,
    '    val nextCardFocus = remember(item.resumeKey) { FocusRequester() }',
    '    val nextCardFocus = remember(item.resumeKey) { FocusRequester() }\n'
    '    val outroSkipFocus = remember(item.resumeKey) { FocusRequester() }\n'
    '    val outroNextFocus = remember(item.resumeKey) { FocusRequester() }')
replace(chrome,
    'code == KeyEvent.KEYCODE_DPAD_LEFT && !controls && (!nextVisible || rootFocused) -> {',
    'code == KeyEvent.KEYCODE_DPAD_LEFT && !controls && !nextVisible && rootFocused -> {')
replace(chrome,
    'code == KeyEvent.KEYCODE_DPAD_RIGHT && !controls && (!nextVisible || rootFocused) -> {',
    'code == KeyEvent.KEYCODE_DPAD_RIGHT && !controls && !nextVisible && rootFocused -> {')
replace(chrome,
    'if (!controls && next != null && active.any { it.kind == V115SegmentKind.OUTRO } && !nextVisible) {',
    'if (next != null && active.any { it.kind == V115SegmentKind.OUTRO } && !nextVisible) {')
replace(chrome,
    'if (segment == focusSegment) Modifier.focusRequester(segmentFocus)\n'
    '                                .onFocusChanged { segmentHasFocus = it.isFocused } else Modifier)',
    'if (segment == focusSegment) Modifier.focusRequester(segmentFocus)\n'
    '                                .onFocusChanged { segmentHasFocus = it.isFocused } else Modifier)\n'
    '                            .then(if (segment.kind == V115SegmentKind.OUTRO && next != null && !nextVisible)\n'
    '                                Modifier.focusRequester(outroSkipFocus)\n'
    '                                    .focusProperties { right = outroNextFocus } else Modifier)')
replace(chrome,
    'modifier = Modifier.heightIn(min = 56.dp).v114FocusRing().testTag("vod-outro-next")',
    'modifier = Modifier.heightIn(min = 56.dp)\n'
    '                        .focusRequester(outroNextFocus)\n'
    '                        .focusProperties { left = outroSkipFocus }\n'
    '                        .v114FocusRing().testTag("vod-outro-next")')
shutil.copyfile(here/"V171OutroFocusTest.kt",tests/"V171OutroFocusTest.kt")
assert "outroSkipFocus" in chrome.read_text()
assert "&& !nextVisible && rootFocused" in chrome.read_text()
print("v171: outro skip->next DPAD navigation; root seeks only; no Live/VoD cadence changes")
