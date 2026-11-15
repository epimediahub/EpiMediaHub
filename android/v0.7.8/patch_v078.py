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

gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 707', 'versionCode = 708', 'versionCode')
replace_once(gradle, 'versionName = "0.7.7"', 'versionName = "0.7.8"', 'versionName')

for rel in ["ui/V070Home.kt", "ui/Screens.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.7.7", "0.7.8"))
weather = java / "data/V070WeatherClient.kt"
if weather.exists():
    weather.write_text(weather.read_text().replace("EpiMediaHub-Android/0.7.7", "EpiMediaHub-Android/0.7.8"))

src = Path(__file__).with_name("V078DashboardPairingGate.kt")
dst = java / "ui/V078DashboardPairingGate.kt"
shutil.copyfile(src, dst)

app = java / "EpiMediaHubApp.kt"
s = app.read_text()

old_startup = '''    var initialDashboardRedirectDone by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        if (!initialDashboardRedirectDone &&
            SetupCodeProvisioning.sessionToken(context.applicationContext) == null
        ) {
            initialDashboardRedirectDone = true
            vm.navigate(Screen.WebAdmin)
        }
    }
'''
new_startup = '''    var dashboardPaired by remember {
        mutableStateOf(SetupCodeProvisioning.sessionToken(context.applicationContext) != null)
    }
    LaunchedEffect(Unit) {
        while (true) {
            val pairedNow = SetupCodeProvisioning.sessionToken(context.applicationContext) != null
            if (dashboardPaired != pairedNow) dashboardPaired = pairedNow
            delay(1_000L)
        }
    }
'''
if old_startup not in s:
    raise SystemExit("v0.7.7 startup redirect anchor missing")
s = s.replace(old_startup, new_startup, 1)

old_revoked = '''                DeviceSyncResult.Revoked -> {
                    vm.refreshProfiles()
                    vm.navigate(Screen.WebAdmin)
                }
'''
new_revoked = '''                DeviceSyncResult.Revoked -> {
                    dashboardPaired = false
                    vm.refreshProfiles()
                }
'''
if old_revoked not in s:
    raise SystemExit("revoked route anchor missing")
s = s.replace(old_revoked, new_revoked, 1)

old_theme = '''    MaterialTheme(colorScheme = scheme, shapes = shapes) {
        if (showIntro) {
            V070IntroScreen(accent = accent) { showIntro = false }
        } else ThemeBackdrop(vm.themeRepo(), info, u.themeId) {'''
new_theme = '''    MaterialTheme(colorScheme = scheme, shapes = shapes) {
        if (!dashboardPaired) {
            de.epimediahub.app.ui.V078DashboardPairingGate(
                vm = vm,
                accent = accent,
                isTv = isTv,
                onConnected = {
                    dashboardPaired = true
                    vm.refreshProfiles()
                }
            )
        } else if (showIntro) {
            V070IntroScreen(accent = accent) { showIntro = false }
        } else ThemeBackdrop(vm.themeRepo(), info, u.themeId) {'''
if old_theme not in s:
    raise SystemExit("root MaterialTheme anchor missing")
s = s.replace(old_theme, new_theme, 1)
app.write_text(s)

checks = [
    (gradle, 'versionName = "0.7.8"'),
    (gradle, 'versionCode = 708'),
    (dst, 'fun V078DashboardPairingGate'),
    (dst, 'ANDROID MOBILE · 0.7.8'),
    (app, 'var dashboardPaired by remember'),
    (app, 'if (!dashboardPaired)'),
    (app, 'V078DashboardPairingGate'),
    (app, 'dashboardPaired = false'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing v0.7.8 marker {marker} in {path}")

print("Android v0.7.8 mandatory TV/mobile pairing gate applied")
