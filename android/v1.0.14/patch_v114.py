#!/usr/bin/env python3
"""Readable details and a consistent visible focus outline across active screens."""
import os
import re
import shutil
from pathlib import Path

root = Path(os.environ['PROJECT_ROOT'])
java = root / 'app/src/main/java/de/epimediahub/app'
ui = java / 'ui'
here = Path(__file__).resolve().parent


def masked(source):
    pattern = r'//[^\n]*|/\*[\s\S]*?\*/|"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(pattern, lambda match: ''.join('\n' if c == '\n' else ' ' for c in match.group()), source)


def closing(code, start, opening='(', end=')'):
    depth = 0
    for i in range(start, len(code)):
        if code[i] == opening:
            depth += 1
        elif code[i] == end:
            depth -= 1
            if depth == 0:
                return i
    raise ValueError(f'Unclosed {opening} at {start}')


def function_span(source, signature):
    code = masked(source)
    a = code.index(signature)
    brace = code.index('{', a)
    return a, closing(code, brace, '{', '}') + 1


def arguments(code, opening, end):
    stack = []
    start = opening + 1
    result = []
    for i in range(start, end):
        c = code[i]
        if c in '([{':
            stack.append(c)
        elif c in ')]}':
            stack.pop()
        elif c == ',' and not stack:
            result.append((start, i))
            start = i + 1
    result.append((start, end))
    return [(a, b) for a, b in result if code[a:b].strip()]


CONTROLS = {
    'Button': 1, 'OutlinedButton': 1, 'TextButton': 1, 'ElevatedButton': 1,
    'FilledTonalButton': 1, 'IconButton': 1, 'OutlinedIconButton': 1,
    'FilledIconButton': 1, 'FilledTonalIconButton': 1, 'FloatingActionButton': 1,
    'OutlinedTextField': 2, 'TextField': 2, 'BasicTextField': 2,
    'Switch': 2, 'Checkbox': 2, 'RadioButton': 2, 'Slider': 2,
    'FilterChip': 3, 'AssistChip': 2, 'InputChip': 3, 'SuggestionChip': 2,
    'DropdownMenuItem': 2, 'Tab': 2, 'Surface': 1, 'Card': 1,
}


def add_focus(source):
    code = masked(source)
    edits = []
    total = 0
    for match in re.finditer(r'\b(' + '|'.join(CONTROLS) + r')\s*\(', code):
        name = match.group(1)
        opening = code.index('(', match.start())
        end = closing(code, opening)
        args = arguments(code, opening, end)
        if name in ('Surface', 'Card') and not any(re.match(r'\s*onClick\s*=', code[a:b]) for a, b in args):
            continue
        modifier_arg = None
        for a, b in args:
            found = re.match(r'\s*modifier\s*=\s*', code[a:b])
            if found:
                modifier_arg = (a + found.end(), b)
                break
        if modifier_arg is None:
            idx = CONTROLS[name]
            if len(args) > idx and all(not re.match(r'\s*\w+\s*=(?!=)', code[a:b]) for a, b in args[:idx + 1]):
                modifier_arg = args[idx]
        if modifier_arg:
            a, b = modifier_arg
            expression_end = a + len(code[a:b].rstrip())
            expression = source[a:expression_end]
            trailing = source[expression_end:b]
            if '.v114FocusRing()' in expression:
                continue
            edits.append((a, b, '(' + expression + ').v114FocusRing()' + trailing))
        else:
            trailing_comma = bool(args and code[args[-1][1]:end].strip().startswith(','))
            prefix = '' if not args or trailing_comma else ','
            edits.append((end, end, prefix + '\n            modifier = Modifier.v114FocusRing()\n        '))
        total += 1
    for a, b, replacement in sorted(edits, reverse=True):
        source = source[:a] + replacement + source[b:]
    matches = list(re.finditer(r'\.clickable\s*(?=\(|\{)', masked(source)))
    clickables = len(matches)
    for match in reversed(matches):
        source = source[:match.start()] + '.v114FocusRing()' + source[match.start():]
    return source, total, clickables


gradle = root / 'app/build.gradle.kts'
g = gradle.read_text()
assert g.count('versionCode = 1013') == 1
assert g.count('versionName = "1.0.13"') == 1
gradle.write_text(g.replace('versionCode = 1013', 'versionCode = 1014').replace('versionName = "1.0.13"', 'versionName = "1.0.14"'))
for name in ('Screens.kt', 'V078DashboardPairingGate.kt', 'V083Home.kt', 'V112SmartTubePlayer.kt'):
    p = ui / name
    p.write_text(p.read_text().replace('1.0.13', '1.0.14'))
p = java / 'data/V070WeatherClient.kt'
p.write_text(p.read_text().replace('1.0.13', '1.0.14'))

details = ui / 'V043Details.kt'
s = details.read_text()
adapters = (here / 'detail_adapters.kt.inc').read_text()
for signature in ('fun V043MediaDetailScreen(', 'fun V043MediathekDetailScreen('):
    a, b = function_span(s, signature)
    new_a, new_b = function_span(adapters, signature)
    s = s[:a] + adapters[new_a:new_b] + s[b:]
a, b = function_span(s, 'private fun V043Poster(')
s = s[:a] + s[a:b].replace('ContentScale.Crop', 'ContentScale.Fit') + s[b:]
details.write_text(s)

# All active routes and their dialogs. Dormant historical screen versions are untouched.
active = (
    'Common.kt', 'Screens.kt', 'ParityScreens.kt', 'V035Screens.kt', 'BrowserRows.kt',
    'PlayerScreen.kt', 'V043Browser.kt', 'V043Details.kt', 'V083Home.kt', 'V070Playlists.kt',
    'V079Themes.kt', 'V060CinematicHub.kt', 'V076LiveTv.kt', 'V093CategoryVisibility.kt',
    'V101CategorySettings.kt', 'V093PlaybackUi.kt', 'V112SmartTubeShell.kt',
    'V112SmartTubePlayer.kt', 'V110SmartTubeShell.kt', 'V081WeatherSettings.kt', 'V047WebAdmin.kt',
    'V078DashboardPairingGate.kt', 'UpdateScreen.kt', 'SetupCodeLogin.kt',
)
summary = []
for name in active:
    p = ui / name
    source = p.read_text()
    # Clickable owns its focus target. Keep standalone player keyboard targets.
    if name not in ('PlayerScreen.kt', 'V112SmartTubePlayer.kt'):
        source = source.replace('.focusable()', '')
    source, controls, tiles = add_focus(source)
    p.write_text(source)
    summary.append(f'{name}: {controls} controls, {tiles} tiles')
p = java / 'EpiMediaHubApp.kt'
source, controls, tiles = add_focus(p.read_text())
if 'import androidx.compose.ui.Modifier\n' not in source:
    source = source.replace('import androidx.compose.ui.graphics.Color', 'import androidx.compose.ui.Modifier\nimport androidx.compose.ui.graphics.Color', 1)
p.write_text(source)
summary.append(f'EpiMediaHubApp.kt: {controls} controls, {tiles} tiles')

for name in ('V114Focus.kt', 'V114DetailLayout.kt'):
    shutil.copyfile(here / name, ui / name)
tests = root / 'app/src/test/java/de/epimediahub/app/ui'
shutil.copyfile(here / 'V114DetailsFocusTest.kt', tests / 'V114DetailsFocusTest.kt')
assert 'LazyColumn' not in s[function_span(s, 'fun V043MediaDetailScreen(')[0]:function_span(s, 'fun V043MediathekDetailScreen(')[1]]
assert 'V114DetailLayout(' in s
assert 'v111RememberLazyListState("livetv-channels:" + selectedId)' not in (ui / 'V076LiveTv.kt').read_text()
print('Android 1.0.14: detail reading area and visible focus migration')
print('\n'.join(summary))
