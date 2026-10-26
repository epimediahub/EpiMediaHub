#!/usr/bin/env python3
from pathlib import Path
import os
import shutil

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


# Version.
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 705', 'versionCode = 706', 'versionCode')
replace_once(gradle, 'versionName = "0.7.5"', 'versionName = "0.7.6"', 'versionName')

home = java / "ui/V070Home.kt"
s = home.read_text().replace("0.7.5", "0.7.6")
old_tiles = '''        V070Tile("MEDIATHEK", "Sender · Sendungen · Details", R.drawable.icon_mediathek) { vm.navigate(ParityMediathekHome) },
        V070Tile("PLAYLISTS", if (u.playlists.size > 1) "${u.playlists.size} Profile · wechseln" else "Verwalten · hinzufügen", R.drawable.icon_playlist) { vm.navigate(Screen.Playlists) },
        V070Tile("EINSTELLUNGEN", "Design · QR-Websetup · Update", R.drawable.icon_settings) { vm.navigate(Screen.Settings) }
'''
new_tiles = '''        V070Tile("MEDIATHEK", "Sender · Sendungen · Details", R.drawable.icon_mediathek) { vm.navigate(ParityMediathekHome) },
        V070Tile("PLAYLISTS", if (u.playlists.size > 1) "${u.playlists.size} Profile · wechseln" else "Verwalten · hinzufügen", R.drawable.icon_playlist) { vm.navigate(Screen.Playlists) },
        V070Tile("GERÄT & DASHBOARD", "8-stelliger Code · Kundensync · Websetup", R.drawable.icon_settings) { vm.navigate(Screen.WebAdmin) },
        V070Tile("EINSTELLUNGEN", "Design · Audio · Update", R.drawable.icon_settings) { vm.navigate(Screen.Settings) }
'''
if old_tiles not in s:
    raise SystemExit("home tile anchor missing")
s = s.replace(old_tiles, new_tiles, 1)

old_grid = '''        val columns = if (isTv) 2 else 3
        val rows = if (isTv) 3 else 2
'''
new_grid = '''        val columns = if (isTv) 2 else 3
        val rows = (tiles.size + columns - 1) / columns
'''
if old_grid not in s:
    raise SystemExit("home grid anchor missing")
s = s.replace(old_grid, new_grid, 1)

old_cell = '''                                val index = row * columns + column
                                val tile = tiles[index]
                                V070TileCard(
                                    tile.title, tile.subtitle, tile.icon, skinMark, accent, isTv, compact,
                                    Modifier.weight(1f).fillMaxHeight().then(if (index == 0) Modifier.focusRequester(firstFocus) else Modifier),
                                    tile.open
                                )
'''
new_cell = '''                                val index = row * columns + column
                                if (index < tiles.size) {
                                    val tile = tiles[index]
                                    V070TileCard(
                                        tile.title, tile.subtitle, tile.icon, skinMark, accent, isTv, compact,
                                        Modifier.weight(1f).fillMaxHeight().then(if (index == 0) Modifier.focusRequester(firstFocus) else Modifier),
                                        tile.open
                                    )
                                } else {
                                    Spacer(Modifier.weight(1f).fillMaxHeight())
                                }
'''
if old_cell not in s:
    raise SystemExit("home grid cell anchor missing")
s = s.replace(old_cell, new_cell, 1)
home.write_text(s)

weather = java / "data/V070WeatherClient.kt"
if weather.exists():
    weather.write_text(weather.read_text().replace("EpiMediaHub-Android/0.7.5", "EpiMediaHub-Android/0.7.6"))

screens = java / "ui/Screens.kt"
if screens.exists():
    screens.write_text(
        screens.read_text()
        .replace("Android v0.7.5", "Android v0.7.6")
        .replace(
            'FocusCard("PC-Verwaltung im Browser",if(u.webAdminRunning)"Aktiv · ${u.webAdminUrl}" else "Xtream/M3U bequem am Computer eingeben",R.drawable.icon_playlist,accent=accent,onClick={vm.navigate(Screen.WebAdmin)})',
            'FocusCard("GERÄT & DASHBOARD",if(u.webAdminRunning)"8-stelliger Kopplungscode · 12-stelliger Code · Websetup" else "Dashboard-Kopplung und Websetup öffnen",R.drawable.icon_playlist,accent=accent,onClick={vm.navigate(Screen.WebAdmin)})'
        )
    )

# Dedicated receiver-style screen with restored category/channel position.
src = Path(__file__).with_name("V076LiveTv.kt")
dst = java / "ui/V076LiveTv.kt"
shutil.copyfile(src, dst)

app = java / "EpiMediaHubApp.kt"
replace_once(
    app,
    's.kind == de.epimediahub.app.model.MediaKind.LIVE -> V075LiveTvScreen(vm, accent, isTv)',
    's.kind == de.epimediahub.app.model.MediaKind.LIVE -> V076LiveTvScreen(vm, accent, isTv)',
    'Live TV route',
)

# Pairing/Websetup is intentionally shared between Android TV and Mobile.
web = java / "ui/V047WebAdmin.kt"
s = web.read_text()
s = s.replace('EpiTopBar("GERÄT & WEBSETUP"', 'EpiTopBar("GERÄT & DASHBOARD"')
web.write_text(s)

checks = [
    (gradle, 'versionName = "0.7.6"'),
    (gradle, 'versionCode = 706'),
    (home, '"GERÄT & DASHBOARD"'),
    (home, 'val rows = (tiles.size + columns - 1) / columns'),
    (dst, 'FocusRequester()'),
    (dst, 'railState.scrollToItem(selectedIndex)'),
    (dst, 'state.scrollToItem(selectedIndex)'),
    (app, 'V076LiveTvScreen(vm, accent, isTv)'),
    (web, 'Kopplungscode erzeugen'),
    (web, '12-stelligen Einrichtungscode verwenden'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing v0.7.6 marker {marker} in {path}")

print("Android v0.7.6 category focus restore and full TV/mobile dashboard parity applied")
