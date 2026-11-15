#!/usr/bin/env python3
from pathlib import Path
import os
import shutil

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"

RECENT = "__recently_added__"

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

# ---------------------------------------------------------------------------
# Version.
# ---------------------------------------------------------------------------
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 800', 'versionCode = 801', 'versionCode')
replace_once(gradle, 'versionName = "0.8"', 'versionName = "0.8.1"', 'versionName')

for rel in ["ui/Screens.kt", "ui/V078DashboardPairingGate.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.8", "0.8.1"))

# ---------------------------------------------------------------------------
# Shared visuals: no duplicate right-side logo, no visible TV back button.
# Home: stronger single centered continuous skin motif on TV + Mobile.
# ---------------------------------------------------------------------------
for source_name, target_rel in [
    ("V081Common.kt", "ui/Common.kt"),
    ("V081Home.kt", "ui/V081Home.kt"),
    ("V081WeatherClient.kt", "data/V070WeatherClient.kt"),
    ("V081WeatherSettings.kt", "ui/V081WeatherSettings.kt"),
]:
    src = Path(__file__).with_name(source_name)
    dst = java / target_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)

screens = java / "ui/Screens.kt"
s = screens.read_text()
if "V080HomeScreen(vm,isTv,accent)" in s:
    s = s.replace("V080HomeScreen(vm,isTv,accent)", "V081HomeScreen(vm,isTv,accent)", 1)
elif "V080HomeScreen(vm, isTv, accent)" in s:
    s = s.replace("V080HomeScreen(vm, isTv, accent)", "V081HomeScreen(vm, isTv, accent)", 1)
else:
    raise SystemExit("0.8 home delegate anchor missing")

weather_anchor = 'item{FocusCard("Bevorzugte Audiosprache"'
if weather_anchor not in s:
    raise SystemExit("settings weather insertion anchor missing")
s = s.replace(weather_anchor, 'item{V081WeatherSettingsCard(accent)};' + weather_anchor, 1)
screens.write_text(s)

# ---------------------------------------------------------------------------
# Genuine "Zuletzt hinzugefügt" for both MOVIE and SERIES.
# Xtream supplies an "added" Unix timestamp on get_vod_streams/get_series.
# ---------------------------------------------------------------------------
models = java / "model/Models.kt"
m = models.read_text()
model_anchor = '    val trailer: String = "",\n    val sourceProfileId: String = ""'
if model_anchor not in m:
    raise SystemExit("MediaEntry sourceProfileId anchor missing")
m = m.replace(
    model_anchor,
    '    val trailer: String = "",\n    val addedAt: Long = 0L,\n    val sourceProfileId: String = ""',
    1,
)
models.write_text(m)

xtream = java / "data/XtreamClient.kt"
x = xtream.read_text()
entry_anchor = '                                genre = o.optString("genre"),\n                                releaseDate = release\n'
if x.count(entry_anchor) != 2:
    raise SystemExit(f"Xtream added timestamp anchors: expected 2, found {x.count(entry_anchor)}")
x = x.replace(
    entry_anchor,
    '                                genre = o.optString("genre"),\n                                releaseDate = release,\n                                addedAt = o.optString("added").toLongOrNull() ?: 0L\n',
    2,
)
xtream.write_text(x)

prefs = java / "data/PrefsRepository.kt"
p = prefs.read_text()
persist_anchor = 'put("trailer",m.trailer);put("sourceProfileId",m.sourceProfileId)'
if persist_anchor not in p:
    raise SystemExit("Prefs addedAt persistence anchor missing")
p = p.replace(
    persist_anchor,
    'put("trailer",m.trailer);put("addedAt",m.addedAt);put("sourceProfileId",m.sourceProfileId)',
    1,
)
restore_anchor = 'releaseDate=o.optString("releaseDate"),trailer=o.optString("trailer"),sourceProfileId=o.optString("sourceProfileId")'
if restore_anchor not in p:
    raise SystemExit("Prefs addedAt restore anchor missing")
p = p.replace(
    restore_anchor,
    'releaseDate=o.optString("releaseDate"),trailer=o.optString("trailer"),addedAt=o.optLong("addedAt"),sourceProfileId=o.optString("sourceProfileId")',
    1,
)
prefs.write_text(p)

vm = java / "MainViewModel.kt"
v = vm.read_text()

cat_load_start, cat_load_end = function_span(v, "    private fun loadCategories(")
new_load_categories = '''    private fun loadCategories(kind: MediaKind) {
        val p = _ui.value.active ?: return
        set {
            it.copy(
                loading = true,
                categories = emptyList(),
                catalogRows = emptyMap(),
                catalogRowsLoading = kind == MediaKind.MOVIE || kind == MediaKind.SERIES,
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
v = v[:cat_load_start] + new_load_categories + v[cat_load_end:]

cat_start, cat_end = function_span(v, "    private fun loadCatalogRows(")
new_catalog = '''    private fun loadCatalogRows(kind: MediaKind, categories: List<MediaCategory>) {
        if (kind != MediaKind.MOVIE && kind != MediaKind.SERIES) return
        val profile = _ui.value.active ?: return
        if (profile.type != PlaylistType.XTREAM) {
            set { it.copy(catalogRowsLoading = false) }
            return
        }
        viewModelScope.launch {
            val rows = runCatching {
                withContext(Dispatchers.IO) {
                    val out = linkedMapOf<String, List<MediaEntry>>()

                    val newest = runCatching {
                        XtreamClient(profile).entries(kind)
                            .map { it.copy(sourceProfileId = profile.id) }
                            .filter { it.addedAt > 0L }
                            .sortedByDescending { it.addedAt }
                            .take(24)
                    }.getOrDefault(emptyList())
                    if (newest.isNotEmpty()) out["__recently_added__"] = newest

                    val categoryPairs = coroutineScope {
                        categories
                            .filterNot { it.id == "__recently_added__" }
                            .take(11)
                            .map { category ->
                                async {
                                    category.id to runCatching {
                                        XtreamClient(profile).entries(kind, category.id)
                                            .map { it.copy(sourceProfileId = profile.id) }
                                            .take(24)
                                    }.getOrDefault(emptyList())
                                }
                            }.awaitAll()
                    }
                    categoryPairs.forEach { (id, entries) ->
                        if (entries.isNotEmpty()) out[id] = entries
                    }
                    out
                }
            }.getOrDefault(emptyMap())
            if (_ui.value.contentFilterKind == kind && _ui.value.active?.id == profile.id) {
                set { it.copy(catalogRows = rows, catalogRowsLoading = false) }
            }
        }
    }'''
v = v[:cat_start] + new_catalog + v[cat_end:]

items_anchor = '                        XtreamClient(p).entries(kind, cat)\n'
if items_anchor not in v:
    raise SystemExit("loadItems Xtream anchor missing")
items_replacement = '''                        if (cat == "__recently_added__" && (kind == MediaKind.MOVIE || kind == MediaKind.SERIES)) {
                            XtreamClient(p).entries(kind)
                                .filter { it.addedAt > 0L }
                                .sortedByDescending { it.addedAt }
                                .take(300)
                        } else {
                            XtreamClient(p).entries(kind, cat)
                        }
'''
v = v.replace(items_anchor, items_replacement, 1)
vm.write_text(v)

checks = [
    (gradle, 'versionName = "0.8.1"'),
    (gradle, 'versionCode = 801'),
    (java / "ui/V081Home.kt", 'fun V081HomeScreen'),
    (java / "ui/V081Home.kt", 'alpha = if (isTv) .50f else .62f'),
    (java / "ui/Common.kt", 'onBack != null && !isTvDevice'),
    (java / "ui/Common.kt", 'val bg = remember(themeId)'),
    (java / "data/V070WeatherClient.kt", 'fun saveLocation(context: Context'),
    (java / "ui/V081WeatherSettings.kt", '"Postleitzahl"'),
    (models, 'val addedAt: Long = 0L'),
    (xtream, 'addedAt = o.optString("added").toLongOrNull() ?: 0L'),
    (vm, 'MediaCategory("__recently_added__", "Zuletzt hinzugefügt")'),
    (vm, '.sortedByDescending { it.addedAt }'),
    (screens, 'V081WeatherSettingsCard(accent)'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing Android 0.8.1 marker {marker} in {path}")

if 'centerMarkRes(themeId)' in (java / "ui/Common.kt").read_text():
    raise SystemExit("duplicate global center skin mark still present")
if 'bannerMarkRes(themeId)' in (java / "ui/Common.kt").read_text():
    raise SystemExit("duplicate global right skin mark still present")

print("Android 0.8.1 skin visibility, TV topbar, postal weather and recently-added movies/series applied")
