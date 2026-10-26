#!/usr/bin/env python3
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
here = Path(__file__).resolve().parent

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
replace_once(gradle, "versionCode = 1003", "versionCode = 1004", "versionCode")
replace_once(gradle, 'versionName = "1.0.3"', 'versionName = "1.0.4"', "versionName")

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    p = java / relative
    if p.exists():
        p.write_text(p.read_text().replace("1.0.3", "1.0.4"))

shutil.copyfile(here / "V104SmartTubeCore.kt", java / "ui/V104SmartTubeCore.kt")
shutil.copyfile(here / "V104SmartTubeShell.kt", java / "ui/V104SmartTubeShell.kt")

# SmartTube's RxJava API is exposed through SignInService, but youtubeapi
# declares RxJava as an implementation dependency. Add it explicitly to the
# host so the EpiMediaHub account UI can compile against Observable/Disposable.
g = gradle.read_text()
dep_anchor = "dependencies {\n"
if 'implementation("io.reactivex.rxjava2:rxjava:2.2.21")' not in g:
    if dep_anchor not in g:
        raise SystemExit("app dependencies anchor missing")
    g = g.replace(
        dep_anchor,
        dep_anchor
        + '    implementation("io.reactivex.rxjava2:rxjava:2.2.21")\n'
        + '    implementation("io.reactivex.rxjava2:rxandroid:2.1.1")\n',
        1,
    )
    gradle.write_text(g)

home = java / "ui/V083Home.kt"
replace_once(
    home,
    "        V100SmartTubeShell(\n",
    "        V104SmartTubeShell(\n",
    "SmartTube shell route",
)

checks = [
    (gradle, "versionCode = 1004"),
    (gradle, 'versionName = "1.0.4"'),
    (gradle, "minSdk = 25"),
    (java / "ui/V104SmartTubeCore.kt", "signInObserve"),
    (java / "ui/V104SmartTubeCore.kt", "fallbackRows"),
    (java / "ui/V104SmartTubeCore.kt", "createMpdStream"),
    (java / "ui/V104SmartTubeShell.kt", "https://yt.be/activate"),
    (java / "ui/V104SmartTubeShell.kt", "V104SmartTubeCore.resolvePlayback"),
    (home, "V104SmartTubeShell("),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing marker {marker} in {path}")

print("Android 1.0.4 SmartTube account/home/playback patch applied")
