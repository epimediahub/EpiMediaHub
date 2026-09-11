#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_screens_fix.py <Screens.kt>')

p = Path(sys.argv[1])
s = p.read_text()

s = s.replace(
    'LazyColumn(state=listState,Modifier.fillMaxSize().padding(10.dp),',
    'LazyColumn(state=listState,modifier=Modifier.fillMaxSize().padding(10.dp),'
)
s = s.replace(
    'LazyColumn(state=listState,Modifier.fillMaxSize().padding(horizontal=10.dp),',
    'LazyColumn(state=listState,modifier=Modifier.fillMaxSize().padding(horizontal=10.dp),'
)
s = s.replace(
    '    val favCount=u.favorites.count{matchesSection(it,kind)}\n',
    '    val favCount=u.favorites.count{matchesSection(it,kind)}\n    val favLabel=if(favCount>0) "Favoriten ($favCount)" else "Favoriten"\n'
)
s = s.replace(
    'item{SideBarRow("Favoriten${if(favCount>0)" ($favCount)" else ""}",false,accent,Icons.Default.FavoriteBorder){vm.openKindFavorites(kind)}}',
    'item{SideBarRow(favLabel,false,accent,Icons.Default.FavoriteBorder){vm.openKindFavorites(kind)}}'
)

p.write_text(s)
print('Screens.kt syntax fixes applied for v0.3.5')
