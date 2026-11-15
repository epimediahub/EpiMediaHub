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
replace_once(gradle, 'versionCode = 708', 'versionCode = 709', 'versionCode')
replace_once(gradle, 'versionName = "0.7.8"', 'versionName = "0.7.9"', 'versionName')

for rel in ["ui/Screens.kt", "ui/V078DashboardPairingGate.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.7.8", "0.7.9"))

for source_name, target_rel in [
    ("V079Common.kt", "ui/Common.kt"),
    ("V079Focus.kt", "ui/V070Focus.kt"),
    ("V079WeatherClient.kt", "data/V070WeatherClient.kt"),
    ("V079Home.kt", "ui/V079Home.kt"),
    ("V079Themes.kt", "ui/V079Themes.kt"),
]:
    src = Path(__file__).with_name(source_name)
    dst = java / target_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)

screens = java / "ui/Screens.kt"
s = screens.read_text()
if "V070HomeScreen(vm,isTv,accent)" in s:
    s = s.replace("V070HomeScreen(vm,isTv,accent)", "V079HomeScreen(vm,isTv,accent)", 1)
elif "V070HomeScreen(vm, isTv, accent)" in s:
    s = s.replace("V070HomeScreen(vm, isTv, accent)", "V079HomeScreen(vm, isTv, accent)", 1)
else:
    raise SystemExit("home screen delegate anchor missing")
screens.write_text(s)

app = java / "EpiMediaHubApp.kt"
a = app.read_text()
route_candidates = [
    "Screen.Themes -> V046ThemesScreen(vm, accent, isTv)",
    "Screen.Themes -> V045ThemesScreen(vm, accent, isTv)",
    "Screen.Themes -> ThemesScreen(vm, accent, isTv)",
]
for old in route_candidates:
    if old in a:
        a = a.replace(old, "Screen.Themes -> V079ThemesScreen(vm, accent, isTv)", 1)
        break
else:
    raise SystemExit("themes route anchor missing")
app.write_text(a)

vm = java / "MainViewModel.kt"
v = vm.read_text()

gate_start, gate_end = function_span(v, "    private fun enforceFamilyThemeGate()")
new_gate = '''    private fun enforceFamilyThemeGate() {
        // Private skins are session-scoped. Every app start locks them again.
        prefs.setFamilySkinsUnlocked(false)
        val state = _ui.value
        val privateSelected = state.themeCatalog?.themes?.get(state.themeId)?.family == true
        if (privateSelected) prefs.themeId = "default"
        _ui.value = state.copy(
            themeId = if (privateSelected) "default" else state.themeId,
            familySkinsUnlocked = false
        )
    }'''
v = v[:gate_start] + new_gate + v[gate_end:]

unlock_start, unlock_end = function_span(v, "    fun unlockFamilySkins(")
lock_method = '''

    fun lockPrivateSkins() {
        prefs.setFamilySkinsUnlocked(false)
        val state = _ui.value
        val privateSelected = state.themeCatalog?.themes?.get(state.themeId)?.family == true
        if (privateSelected) prefs.themeId = "default"
        set {
            it.copy(
                themeId = if (privateSelected) "default" else it.themeId,
                familySkinsUnlocked = false,
                error = ""
            )
        }
    }'''
v = v[:unlock_end] + lock_method + v[unlock_end:]
vm.write_text(v)

checks = [
    (gradle, 'versionName = "0.7.9"'),
    (gradle, 'versionCode = 709'),
    (java / "ui/Common.kt", "alpha = .075f"),
    (java / "ui/V070Focus.kt", "1.035f"),
    (java / "data/V070WeatherClient.kt", "val city: String"),
    (java / "data/V070WeatherClient.kt", "Accept-Language"),
    (java / "ui/V079Home.kt", "ANDROID MOBILE · 0.7.9"),
    (java / "ui/V079Themes.kt", "PRIVATE DESIGNS"),
    (java / "ui/V079Themes.kt", "filterNot { it.family }"),
    (vm, "fun lockPrivateSkins()"),
    (vm, "prefs.setFamilySkinsUnlocked(false)"),
    (screens, "V079HomeScreen(vm"),
    (app, "Screen.Themes -> V079ThemesScreen(vm, accent, isTv)"),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing v0.7.9 marker {marker} in {path}")

print("Android v0.7.9 professional skins, private themes and localized city weather applied")
