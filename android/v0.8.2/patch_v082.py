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
replace_once(gradle, 'versionCode = 801', 'versionCode = 802', 'versionCode')
replace_once(gradle, 'versionName = "0.8.1"', 'versionName = "0.8.2"', 'versionName')

for rel in ["ui/Screens.kt", "ui/V078DashboardPairingGate.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.8.1", "0.8.2"))

src = Path(__file__).with_name("V082Home.kt")
dst = java / "ui/V082Home.kt"
shutil.copyfile(src, dst)

screens = java / "ui/Screens.kt"
s = screens.read_text()
if "V081HomeScreen(vm,isTv,accent)" in s:
    s = s.replace("V081HomeScreen(vm,isTv,accent)", "V082HomeScreen(vm,isTv,accent)", 1)
elif "V081HomeScreen(vm, isTv, accent)" in s:
    s = s.replace("V081HomeScreen(vm, isTv, accent)", "V082HomeScreen(vm, isTv, accent)", 1)
else:
    raise SystemExit("0.8.1 home delegate anchor missing")
screens.write_text(s)

weather = java / "data/V070WeatherClient.kt"
if weather.exists():
    weather.write_text(weather.read_text().replace("EpiMediaHub-Android/0.8.1", "EpiMediaHub-Android/0.8.2"))

vm = java / "MainViewModel.kt"
v = vm.read_text()

# Restore LIVE catalog loading while keeping the synthetic recent category for VOD/series.
load_cat_start, load_cat_end = function_span(v, "    private fun loadCategories(")
load_categories = '''    private fun loadCategories(kind: MediaKind) {
        val p = _ui.value.active ?: return
        set {
            it.copy(
                loading = true,
                categories = emptyList(),
                catalogRows = emptyMap(),
                catalogRowsLoading = kind == MediaKind.MOVIE || kind == MediaKind.SERIES || kind == MediaKind.LIVE,
                error = ""
            )
        }
        viewModelScope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    if (p.type == PlaylistType.XTREAM) {
                        XtreamClient(p).categories(kind)
                    } else if (kind == MediaKind.LIVE) {
                        m3uResult(p).groups.map { MediaCategory(it, it) }
                    } else {
                        emptyList()
                    }
                }
            }.onSuccess { categories ->
                if (_ui.value.active?.id == p.id) {
                    val visibleCategories = if (kind == MediaKind.MOVIE || kind == MediaKind.SERIES) {
                        listOf(MediaCategory("__recently_added__", "Zuletzt hinzugefügt")) + categories
                    } else {
                        categories
                    }
                    set { it.copy(loading = false, categories = visibleCategories) }
                    loadCatalogRows(kind, visibleCategories)
                }
            }.onFailure { e ->
                if (_ui.value.active?.id == p.id) {
                    set { it.copy(loading = false, catalogRowsLoading = false, error = e.message ?: "Fehler beim Laden") }
                }
            }
        }
    }'''
v = v[:load_cat_start] + load_categories + v[load_cat_end:]

# Fast path: one Xtream library request, then group locally.
# This restores the pre-0.8.1 behavior and also fixes LIVE, which V076LiveTv
# expects to read from catalogRows.
rows_start, rows_end = function_span(v, "    private fun loadCatalogRows(")
load_rows = '''    private fun loadCatalogRows(kind: MediaKind, categories: List<MediaCategory>) {
        if (kind != MediaKind.MOVIE && kind != MediaKind.SERIES && kind != MediaKind.LIVE) return
        val profile = _ui.value.active ?: return
        if (categories.isEmpty()) {
            set { it.copy(catalogRowsLoading = false) }
            return
        }
        if (profile.type != PlaylistType.XTREAM && kind != MediaKind.LIVE) {
            set { it.copy(catalogRowsLoading = false) }
            return
        }

        viewModelScope.launch {
            val rows = runCatching {
                withContext(Dispatchers.IO) {
                    val all = when {
                        profile.type == PlaylistType.XTREAM ->
                            xtreamLibrary(profile, kind)
                        kind == MediaKind.LIVE ->
                            m3uResult(profile).entries.map { entry -> entry.copy(sourceProfileId = profile.id) }
                        else -> emptyList()
                    }

                    val out = linkedMapOf<String, List<MediaEntry>>()

                    if (kind == MediaKind.MOVIE || kind == MediaKind.SERIES) {
                        val newest = all.asSequence()
                            .filter { it.addedAt > 0L }
                            .sortedByDescending { it.addedAt }
                            .take(36)
                            .toList()
                        if (newest.isNotEmpty()) out["__recently_added__"] = newest
                    }

                    val byCategory = all.groupBy { entry -> entry.categoryId }
                    categories
                        .filterNot { it.id == "__recently_added__" }
                        .forEach { category ->
                            val row = if (category.id == "__all__") {
                                all
                            } else {
                                byCategory[category.id].orEmpty()
                            }
                            if (row.isNotEmpty()) out[category.id] = row
                        }

                    out
                }
            }.getOrDefault(emptyMap())

            if (_ui.value.contentFilterKind == kind && _ui.value.active?.id == profile.id) {
                set { it.copy(catalogRows = rows, catalogRowsLoading = false) }
            }
        }
    }'''
v = v[:rows_start] + load_rows + v[rows_end:]

old_recent = '''                        if (cat == "__recently_added__" && (kind == MediaKind.MOVIE || kind == MediaKind.SERIES)) {
                            XtreamClient(p).entries(kind)
                                .filter { it.addedAt > 0L }
                                .sortedByDescending { it.addedAt }
                                .take(300)
                        } else {
                            XtreamClient(p).entries(kind, cat)
                        }
'''
new_recent = '''                        if (cat == "__recently_added__" && (kind == MediaKind.MOVIE || kind == MediaKind.SERIES)) {
                            xtreamLibrary(p, kind)
                                .filter { it.addedAt > 0L }
                                .sortedByDescending { it.addedAt }
                                .take(300)
                        } else {
                            XtreamClient(p).entries(kind, cat)
                        }
'''
if old_recent not in v:
    raise SystemExit("recent loadItems anchor missing")
v = v.replace(old_recent, new_recent, 1)
vm.write_text(v)

checks = [
    (gradle, 'versionName = "0.8.2"'),
    (gradle, 'versionCode = 802'),
    (dst, 'fun V082HomeScreen'),
    (dst, 'fillMaxWidth(if (isTv) .67f else .82f)'),
    (dst, 'alpha = if (isTv) .64f else .72f'),
    (dst, 'ANDROID TV · 0.8.2'),
    (vm, 'catalogRowsLoading = kind == MediaKind.MOVIE || kind == MediaKind.SERIES || kind == MediaKind.LIVE'),
    (vm, 'xtreamLibrary(profile, kind)'),
    (vm, 'out["__recently_added__"] = newest'),
    (vm, 'm3uResult(profile).entries.map'),
    (vm, 'xtreamLibrary(p, kind)'),
    (screens, 'V082HomeScreen(vm'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing Android 0.8.2 marker {marker} in {path}")

if 'playlist = u.active?.name ?: "EpiMediaHub"' not in dst.read_text():
    raise SystemExit("home header playlist label missing")

print("Android 0.8.2 home/logo, fast movie-series rows and Live TV catalog restore applied")
