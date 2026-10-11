#!/usr/bin/env python3
"""v1.0.60: cinematic 10s intro + bounded concurrent Live metadata warmup.

Requires v1.0.59. This patch does not modify stream URLs, playback engines,
existing VPN route decisions, device data or in-app update endpoints.
"""
from pathlib import Path
import os
import shutil
import subprocess
import sys

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
java = root / "app/src/main/java/de/epimediahub/app"

def replace(path, old, new, count=1):
    src = path.read_text()
    actual = src.count(old)
    if actual != count:
        raise SystemExit(f"v160 anchor failed {path} ({actual} != {count}): {old[:150]}")
    path.write_text(src.replace(old, new, count))

gradle = root / "app/build.gradle.kts"
replace(gradle, "versionCode = 1059", "versionCode = 1060")
replace(gradle, 'versionName = "1.0.59"', 'versionName = "1.0.60"')

# Replace original Compose intro while retaining its keyboard skip, lifecycle
# handling and familiar branded heartbeat sound.
shutil.copyfile(here.parent / "v1.0.21/V121Intro.kt", java / "ui/V070Intro.kt")
shutil.copyfile(here / "V160IntroTimeline.kt", java / "ui/V121IntroTimeline.kt")
for name in ("V160IntroWorlds.kt", "V160IntroWarmupPolicy.kt"):
    shutil.copyfile(here / name, java / "ui" / name)
intro = java / "ui/V070Intro.kt"
replace(intro,
    '        if (world > 0f) Text("The whole world\\nof multimedia",',
    '        V160IntroWorlds(elapsedMs, accent, unit)\n'
    '        if (world > 0f) Text("The whole world\\nof multimedia",')

# The final 5.8s of the soundtrack stay bit-identical to the old mix.
# New 4.2s prologue lets the screen tell the multimedia and VPN story.
subprocess.run([sys.executable, str(here / "build_intro_audio.py"),
    str(root / "app/src/main/res/raw/epimedia_intro_heartbeat_cinema.wav")], check=True)

# Share the existing LIVE category cache with foreground browsing; no player
# or stream is opened. Background work is cancellable and time-limited.
vm = java / "MainViewModel.kt"
replace(vm,
    '    fun refreshPlaylistsAtAppStart() {',
    (here / "V160LiveWarmup.inc").read_text() + '    fun refreshPlaylistsAtAppStart() {')
replace(vm,
    '        if (list != _ui.value.playlists) {\n            libraryLoadGeneration++; libraryLoadJob?.cancel()',
    '        if (list != _ui.value.playlists) {\n            v160CancelLiveIntroWarmup()\n            libraryLoadGeneration++; libraryLoadJob?.cancel()')
replace(vm, '        prefs.activePlaylistId = id\n        back.clear()',
    '        prefs.activePlaylistId = id\n        v160CancelLiveIntroWarmup()\n        back.clear()')

app = java / "EpiMediaHubApp.kt"
replace(app,
    '    val v134Ready = de.epimediahub.app.vpn.v134RouteReady(context, u.active?.id?.toString())\n'
    '    MaterialTheme(colorScheme = scheme, shapes = shapes) {',
    '    val v134Ready = de.epimediahub.app.vpn.v134RouteReady(context, u.active?.id?.toString())\n'
    '    // Start at most one low-priority metadata warmup during the intro, only\n'
    '    // after pairing, licensing and the existing VPN / DIRECT route gate.\n'
    '    LaunchedEffect(showIntro, dashboardPaired, v120LicenseState.allowsUse, v134Ready, u.active?.id) {\n'
    '        if (V160IntroWarmupPolicy.allowed(showIntro, dashboardPaired,\n'
    '                v120LicenseState.allowsUse, v134Ready, u.active != null)) {\n'
    '            vm.v160WarmLiveDuringIntro()\n'
    '        }\n'
    '    }\n'
    '    MaterialTheme(colorScheme = scheme, shapes = shapes) {')

test_dir = root / "app/src/test/java/de/epimediahub/app/ui"
test_dir.mkdir(parents=True, exist_ok=True)
shutil.copyfile(here / "V160IntroWarmupPolicyTest.kt",
    test_dir / "V160IntroWarmupPolicyTest.kt")
shutil.copyfile(here / "V160IntroTest.kt", test_dir / "V121IntroTest.kt")

assert "V160IntroWorlds(elapsedMs, accent, unit)" in intro.read_text()
assert "v160WarmLiveDuringIntro()" in vm.read_text()
assert "V160IntroWarmupPolicy.allowed" in app.read_text()
assert "V153DirectPolicy.canPlay" in (java / "vpn/V134VpnSession.kt").read_text()
print("v1.0.60 source patch applied: cinematic 10s intro and bounded LIVE metadata warmup.")
print("No media streams started; existing VPN gate preserved. No release publication.")
