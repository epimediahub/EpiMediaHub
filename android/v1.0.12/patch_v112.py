#!/usr/bin/env python3
"""Install the 1.0.12 changes on the verified 1.0.11 project."""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
here = Path(__file__).resolve().parent


def replace(path, old, new, label):
    text = path.read_text()
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected one anchor, found {text.count(old)}")
    path.write_text(text.replace(old, new, 1))


gradle = root / "app/build.gradle.kts"
replace(gradle, "versionCode = 1011", "versionCode = 1012", "version code")
replace(gradle, 'versionName = "1.0.11"', 'versionName = "1.0.12"', "version name")
replace(gradle, "dependencies {\n", 'dependencies {\n    testImplementation("junit:junit:4.13.2")\n', "safety tests")

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    path = java / relative
    path.write_text(path.read_text().replace("1.0.11", "1.0.12"))

for name in ("V108SmartTubeCore.kt", "V112SmartTubeShell.kt", "V112SmartTubePlayer.kt",
             "V112SmartTubeSuggestions.kt", "V112SmartTubeWatchHistory.kt", "V112PlaylistHealth.kt"):
    shutil.copyfile(here / name, java / "ui" / name)
shutil.copyfile(here / "V112PlaylistProbe.kt", java / "data/V112PlaylistProbe.kt")

replace(java / "ui/V083Home.kt", "        V111SmartTubeShell(\n", "        V112SmartTubeShell(\n", "active SmartTube route")

playlist = java / "ui/V070Playlists.kt"
replace(playlist, "    val u by vm.ui.collectAsState()\n", "    val u by vm.ui.collectAsState()\n    val playlistHealth = rememberV112PlaylistHealth(u.playlists)\n", "playlist health")
replace(playlist, "                        type = playlist.type.name,\n", "                        type = playlist.type.name,\n                        status = playlistHealth[playlist.id] ?: V112PlaylistStatus.CHECKING,\n", "row status")
replace(playlist, "private fun V070PlaylistCard(name: String, type: String, active: Boolean", "private fun V070PlaylistCard(name: String, type: String, status: V112PlaylistStatus, active: Boolean", "card status argument")
replace(playlist, "        Spacer(Modifier.width(18.dp))\n", "        Spacer(Modifier.width(12.dp))\n        V112PlaylistStatusLight(status)\n        Spacer(Modifier.width(18.dp))\n", "visible health light")

tests = root / "app/src/test/java/de/epimediahub/app/ui"
tests.mkdir(parents=True, exist_ok=True)
shutil.copyfile(here / "V112SmartTubeSafetyTest.kt", tests / "V112SmartTubeSafetyTest.kt")

core = (java / "ui/V108SmartTubeCore.kt").read_text()
assert "getShortsObserve" not in core
assert 'SHORTS("Shorts"' not in core
assert "service.continueGroupObserve" in core
assert "invokeOnCancellation" in core
assert "historyAccountKey = auth.accountKey" in (java / "ui/V112SmartTubeShell.kt").read_text()
assert "reportProgress(video, historyAccountKey" in (java / "ui/V112SmartTubePlayer.kt").read_text()
assert "rememberV112PlaylistHealth(u.playlists)" in playlist.read_text()
print("Android 1.0.12: Shorts disabled, asynchronous playlist reachability lights, persistent watched filter and bounded replacements installed")
