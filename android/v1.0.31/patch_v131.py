#!/usr/bin/env python3
"""Offline sport skin variants; original scenes, badges and PIN policy survive."""
import os, shutil, json
from pathlib import Path
root=Path(os.environ['PROJECT_ROOT']);here=Path(__file__).resolve().parent
java=root/'app/src/main/java/de/epimediahub/app'
def replace(path,old,new):
 s=path.read_text();assert s.count(old)==1,f'{path}: missing/ambiguous anchor {old[:100]!r}'
 path.write_text(s.replace(old,new,1))
replace(root/'app/build.gradle.kts','versionCode = 1030','versionCode = 1031')
replace(root/'app/build.gradle.kts','versionName = "1.0.30"','versionName = "1.0.31"')
for p in java.rglob('*.kt'):
 s=p.read_text()
 if '1.0.30' in s:p.write_text(s.replace('1.0.30','1.0.31'))
for p in here.glob('V131*.kt'):
 destination=(root/'app/src/test/java/de/epimediahub/app/ui')if p.name.endswith('Test.kt')else java/'ui'
 destination.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,destination/p.name)
repo=java/'data/ThemeRepository.kt'
replace(repo,'import de.epimediahub.app.R','import de.epimediahub.app.R\nimport de.epimediahub.app.ui.V131BaseTheme')
replace(repo,'fun backgroundRes(id: String): Int {','fun backgroundRes(themeId: String): Int {\n        val id = V131BaseTheme(themeId)')
replace(repo,'drawable("official_${safe(id)}")','drawable("official_${safe(V131BaseTheme(id))}")')
replace(java/'ui/Common.kt','            if (watermark != 0) {','            V131PortraitLayer(themeId)\n\n            if (watermark != 0) {')
world=java/'ui/V097SkinEnvironment.kt'
replace(world,'NEUTRAL, STADIUM, GARAGE, PIT_GARAGE','NEUTRAL, STADIUM, GARAGE, PIT_GARAGE, BASKETBALL')
replace(world,'    group == "cars" -> V097SkinWorld.GARAGE','    group == "cars" -> V097SkinWorld.GARAGE\n    group == "nba" -> V097SkinWorld.BASKETBALL\n    group == "nfl" -> V097SkinWorld.STADIUM')
replace(world,'    V097SkinWorld.NEUTRAL -> 0','    V097SkinWorld.BASKETBALL -> R.drawable.skin_world_basketball\n    V097SkinWorld.NEUTRAL -> 0')
themes=java/'ui/V079Themes.kt'
replace(themes,'    "cars" -> "Automarken"','    "cars" -> "Automarken"\n    "nba" -> "NBA"\n    "nfl" -> "NFL"')
replace(themes,'setOf("national_teams", "formula_1", "cars")','setOf("national_teams", "formula_1", "cars", "nba", "nfl")')
replace(themes,'Vereine, Nationalteams, Formel 1 und Automarken nach Passwortfreigabe','Vereine, Nationalteams, Formel 1, NBA, NFL und Automarken nach Passwortfreigabe')
replace(themes,'''                        V099ThemePreview(
                            vm, theme, theme.id == u.themeId, isTv,
                            onClick = { vm.selectTheme(theme.id) }
                        )''','''                        if (V131SkinArtwork.variants(androidx.compose.ui.platform.LocalContext.current, theme.id).isNotEmpty()) {
                            V131TeamCarousel(vm, theme, u.themeId, isTv)
                        } else {
                            V099ThemePreview(vm, theme, theme.id == u.themeId, isTv,
                                onClick = { vm.selectTheme(theme.id) })
                        }''')
replace(themes,'                val motorsport = categories.filter { it.group.id in setOf("formula_1", "cars") }','''                val motorsport = categories.filter { it.group.id in setOf("formula_1", "cars") }
                val american = categories.filter { it.group.id in setOf("nba", "nfl") }''')
replace(themes,'                    if (motorsport.isNotEmpty()) {','''                    if (american.isNotEmpty()) {
                        item { V099SectionHeading("BASKETBALL & AMERICAN FOOTBALL", isTv) }
                        items(american, key = { it.group.id }) { item ->
                            V099CategoryCard(item, isTv, accent) { selectedGroupId = item.group.id; V111MenuMemory.rememberText("themes-group", item.group.id) }
                        }
                    }
                    if (motorsport.isNotEmpty()) {''')
replace(themes,'Text("${item.themes.size} Original-Skins · Privat"','Text("${item.themes.size} ${if (item.group.id == \"cars\") \"Original-Skins\" else \"Teams · 3 Varianten\"} · Privat"')
home=java/'ui/V083Home.kt'
replace(home,'start = if (isTv) 48.dp else 8.dp','start = if (isTv) 80.dp else 12.dp')
replace(home,'end = if (isTv) 48.dp else 8.dp','end = if (isTv) 80.dp else 12.dp')
replace(home,'top = 2.dp,','top = if (isTv) 14.dp else 6.dp,')
replace(home,'bottom = if (isTv) 18.dp else 7.dp','bottom = if (isTv) 30.dp else 11.dp')
# Team IDs are in the groups only once; variants inherit the exact base skin.
catalog_path=root/'app/src/main/res/raw/theme_catalog.json';catalog=json.loads(catalog_path.read_text())
additions=json.loads((here/'catalog_additions.json').read_text())
existing=set(catalog['themes']);assert not existing.intersection(additions['themes'])
catalog['groups'].extend(additions['groups']);catalog['themes'].update(additions['themes'])
catalog_path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
print('Android 1.0.31: 134 sport teams, sideways variants, original scenes and smaller home cards installed')
