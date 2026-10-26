#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


# Promote the corrected test build to v0.6.2.
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 601', 'versionCode = 602', 'versionCode')
replace_once(gradle, 'versionName = "0.6.1"', 'versionName = "0.6.2"', 'versionName')

home = java / "ui/V044Home.kt"
text = home.read_text()
if "0.6.1" not in text:
    raise SystemExit("home version anchor missing")
home.write_text(text.replace("0.6.1", "0.6.2"))


# v0.6.1 generated a Kotlin regular string with a single backslash before the
# dot. Kotlin treats that as an illegal escape. Keep the same endpoint matcher,
# but emit the escaped backslash required by Kotlin source.
parser = java / "data/PlaylistParser.kt"
replace_once(
    parser,
    r'Regex("/(?i:get|player_api|panel_api|xmltv)\.php$")'.replace('\\"', '"'),
    r'Regex("/(?i:get|player_api|panel_api|xmltv)\\.php$")'.replace('\\"', '"'),
    "Xtream endpoint regex escape",
)

# Guard against reintroducing the broken Kotlin escape in reconstructed source.
source = parser.read_text()
broken = r'Regex("/(?i:get|player_api|panel_api|xmltv)\.php$")'.replace('\\"', '"')
fixed = r'Regex("/(?i:get|player_api|panel_api|xmltv)\\.php$")'.replace('\\"', '"')
if broken in source:
    raise SystemExit("single-backslash Xtream endpoint regex still present")
if fixed not in source:
    raise SystemExit("corrected Xtream endpoint regex missing")

print("Android v0.6.2 compile-fix patch applied")
