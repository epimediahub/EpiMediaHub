#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_screens.py <Screens.kt>')

path = Path(sys.argv[1])
s = path.read_text()

def replace_between(text, start_marker, end_marker, replacement):
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit(f'markers missing: {start_marker!r} -> {end_marker!r}')
    return text[:start] + replacement + '\n' + text[end:]

# Repair known syntax defects emitted by the historical v0.3.5 raw-string patch.
s = s.replace(
    'now?.let{\\"${clock(it.start)}–${clock(it.end)}  ${it.title}\\"}.orEmpty()',
    'now?.let{"${clock(it.start)}–${clock(it.end)}  ${it.title}"}.orEmpty()'
)
s = s.replace(
    'kind?.let{sectionTitle(it)+\\" · \\"}',
    'kind?.let{sectionTitle(it)+" · "}'
)
s = s.replace(
    'OutlinedButton(onClick={vm.navigate(Screen.Categories(kind),remember=false),modifier=Modifier.weight(1f)){Text("Kategorien")}',
    'OutlinedButton(onClick={vm.navigate(Screen.Categories(kind),remember=false)},modifier=Modifier.weight(1f)){Text("Kategorien")}'
)

home = '''@Composable
fun HomeScreen(vm:MainViewModel,isTv:Boolean,accent:Color){
    V036HomeScreen(vm,isTv,accent)
}
'''

s = replace_between(s, '@Composable\nfun HomeScreen', '@Composable\nfun AddPlaylistScreen', home)
s = s.replace('Android v0.3.5', 'Android v0.3.6')
s = s.replace('IBO-inspirierter Browser · Kategorien links · Positionsspeicher', 'Premium-Skins · integriertes Logo-Design · IBO-Browser')

# Guard against regressions in the historical patch chain.
invalid_fragments = [
    '\\" · \\"',
    'now?.let{\\"',
    'remember=false),modifier=Modifier.weight(1f)'
]
for fragment in invalid_fragments:
    if fragment in s:
        raise SystemExit(f'v0.3.5 Kotlin repair incomplete: {fragment}')

path.write_text(s)
print('Screens.kt patched for Android v0.3.6')
