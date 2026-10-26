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

def function_span(text: str, signature: str):
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"function not found: {signature}")
    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"opening brace missing: {signature}")
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise SystemExit(f"closing brace missing: {signature}")

gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 709', 'versionCode = 800', 'versionCode')
replace_once(gradle, 'versionName = "0.7.9"', 'versionName = "0.8"', 'versionName')

for rel in ["ui/Screens.kt", "ui/V078DashboardPairingGate.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.7.9", "0.8"))

weather = java / "data/V070WeatherClient.kt"
if weather.exists():
    weather.write_text(weather.read_text().replace("EpiMediaHub-Android/0.7.9", "EpiMediaHub-Android/0.8"))

# Home: exactly six tiles and one single continuous centered skin motif.
src = Path(__file__).with_name("V080Home.kt")
dst = java / "ui/V080Home.kt"
shutil.copyfile(src, dst)

screens = java / "ui/Screens.kt"
s = screens.read_text()
if "V079HomeScreen(vm,isTv,accent)" in s:
    s = s.replace("V079HomeScreen(vm,isTv,accent)", "V080HomeScreen(vm,isTv,accent)", 1)
elif "V079HomeScreen(vm, isTv, accent)" in s:
    s = s.replace("V079HomeScreen(vm, isTv, accent)", "V080HomeScreen(vm, isTv, accent)", 1)
else:
    raise SystemExit("v0.7.9 home delegate anchor missing")
screens.write_text(s)

# The global backdrop watermark stays extremely subtle. The main skin artwork
# now lives once, centered behind the six home tiles.
common = java / "ui/Common.kt"
c = common.read_text()
c = c.replace(".graphicsLayer { alpha = .075f }", ".graphicsLayer { alpha = .025f }", 1)
c = c.replace(".graphicsLayer { alpha = .035f }", ".graphicsLayer { alpha = .018f }", 1)
common.write_text(c)

# Private designs stay unlocked across app restarts once the password has been
# entered successfully. Explicit "Private sperren" still locks them again.
vm = java / "MainViewModel.kt"
v = vm.read_text()
start, end = function_span(v, "    private fun enforceFamilyThemeGate()")
persistent_gate = '''    private fun enforceFamilyThemeGate() {
        val state = _ui.value
        val unlocked = prefs.familySkinsUnlocked()
        val privateSelected = state.themeCatalog?.themes?.get(state.themeId)?.family == true

        if (!unlocked && privateSelected) {
            prefs.themeId = "default"
            _ui.value = state.copy(
                themeId = "default",
                familySkinsUnlocked = false
            )
        } else {
            _ui.value = state.copy(familySkinsUnlocked = unlocked)
        }
    }'''
v = v[:start] + persistent_gate + v[end:]
vm.write_text(v)

themes = java / "ui/V079Themes.kt"
t = themes.read_text()
t = t.replace(
    "Private Skins sind vollständig verborgen. Gib das Private-Passwort ein, um sie für diese Sitzung sichtbar zu machen.",
    "Private Skins sind vollständig verborgen. Nach korrekter Passwortfreigabe bleiben sie sichtbar, bis du sie bewusst wieder sperrst."
)
t = t.replace(
    "Nur nach Passwortfreigabe sichtbar",
    "Dauerhaft freigeschaltet · bis zum manuellen Sperren"
)
themes.write_text(t)

checks = [
    (gradle, 'versionName = "0.8"'),
    (gradle, 'versionCode = 800'),
    (dst, 'fun V080HomeScreen'),
    (dst, 'ANDROID TV · 0.8'),
    (dst, 'ANDROID MOBILE · 0.8'),
    (dst, 'val rows = 3.takeIf { isTv } ?: 2'),
    (dst, 'fillMaxWidth(if (isTv) .58f else .62f)'),
    (dst, 'alpha = if (isTv) .22f else .19f'),
    (dst, '"EINSTELLUNGEN"'),
    (screens, 'V080HomeScreen(vm'),
    (vm, 'val unlocked = prefs.familySkinsUnlocked()'),
    (themes, 'Dauerhaft freigeschaltet'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing Android 0.8 marker {marker} in {path}")

if '"GERÄT & DASHBOARD"' in dst.read_text():
    raise SystemExit("Android 0.8 home must contain exactly six tiles without dashboard tile")

print("Android 0.8 six-tile continuous skin home and persistent private designs applied")
