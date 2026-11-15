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


# Version.
build = root / "app/build.gradle.kts"
replace_once(build, 'versionCode = 614', 'versionCode = 615', 'hotfix12 versionCode')
replace_once(build, 'versionName = "0.6.4.11"', 'versionName = "0.6.4.12"', 'hotfix12 versionName')

home = java / "ui/V044Home.kt"
replace_once(home, "0.6.4.11", "0.6.4.12", "hotfix12 visible version")


# Movie/series catalog rows were still capped to 24 entries even after all
# categories became visible in v0.6.4.10. Keep every provider item in each
# category. LazyRow only composes visible posters, so the UI remains lazy.
vm = java / "MainViewModel.kt"
s = vm.read_text()
old = '''                        val row = if (category.id == "__all__") {
                            all.take(24)
                        } else {
                            byCategory[category.id].orEmpty().take(24)
                        }
'''
new = '''                        val row = if (category.id == "__all__") {
                            all
                        } else {
                            byCategory[category.id].orEmpty()
                        }
'''
if old not in s:
    raise SystemExit("catalog 24-item data cap anchor missing")
s = s.replace(old, new, 1)
vm.write_text(s)


# The cinematic poster row itself independently truncated every list to 24.
hub = java / "ui/V060CinematicHub.kt"
s = hub.read_text()
old_ui = '            items(entries.take(24), key = { it.resumeKey }) { item -> V060Poster(item, accent, isTv) { onItem(item) } }\n'
new_ui = '            items(entries, key = { it.resumeKey }) { item -> V060Poster(item, accent, isTv) { onItem(item) } }\n'
if old_ui not in s:
    raise SystemExit("cinematic poster-row 24-item UI cap anchor missing")
s = s.replace(old_ui, new_ui, 1)
hub.write_text(s)

checks = [
    (build, 'versionName = "0.6.4.12"'),
    (build, 'versionCode = 615'),
    (vm, 'val byCategory = all.groupBy { entry -> entry.categoryId }'),
    (vm, 'byCategory[category.id].orEmpty()'),
    (hub, 'items(entries, key = { it.resumeKey })'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing hotfix12 marker {marker} in {path}")

if 'all.take(24)' in vm.read_text() or 'byCategory[category.id].orEmpty().take(24)' in vm.read_text():
    raise SystemExit("catalog data still contains a 24-item row cap")
if 'items(entries.take(24)' in hub.read_text():
    raise SystemExit("cinematic UI still contains a 24-item row cap")

print("Android v0.6.4.12 unlimited movie/series horizontal catalog rows applied")
