#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_app.py <EpiMediaHubApp.kt>')

p=Path(sys.argv[1])
s=p.read_text()
repls={
    'Screen.Home -> HomeScreen(vm, isTv, accent)':'Screen.Home -> V035HomeScreen(vm, isTv, accent)',
    'Screen.Search -> SearchScreen(vm, accent, isTv)':'Screen.Search -> V035SearchScreen(vm, accent, isTv)',
    'Screen.Favorites -> FavoritesScreen(vm, accent, isTv)':'Screen.Favorites -> V035FavoritesScreen(vm, accent, isTv)',
    'is Screen.Categories -> CategoryScreen(vm, s.kind, accent, isTv)':'is Screen.Categories -> V035CategoryScreen(vm, s.kind, accent, isTv)',
    'is Screen.Items -> ItemsScreen(vm, s.kind, s.category, accent, isTv)':'is Screen.Items -> V035ItemsScreen(vm, s.kind, s.category, accent, isTv)'
}
for a,b in repls.items():
    if a not in s:
        raise SystemExit(f'missing app route: {a}')
    s=s.replace(a,b,1)
p.write_text(s)
print('EpiMediaHubApp.kt routed to v0.3.5 browser screens')
