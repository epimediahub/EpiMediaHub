#!/usr/bin/env python3
"""v1.0.58 candidate on top of v1.0.57: truthful recent content and live version label.

Playback, VPN routing, provider credentials, Fire-TV/GalaBox stream candidates,
parental controls, and client data are intentionally untouched.
"""
from pathlib import Path
import os, re, shutil

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
java = root / "app/src/main/java/de/epimediahub/app"
tests = root / "app/src/test/java/de/epimediahub/app"

def replace_once(path: Path, old: str, new: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: anchor count {count} (expected 1): {old[:100]}")
    path.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
replace_once(gradle, "versionCode = 1057", "versionCode = 1058")
replace_once(gradle, 'versionName = "1.0.57"', 'versionName = "1.0.58"')

# Use only provider-provided timestamps; do not show "old random titles"
# when a provider omitted an added date or returned unordered results.
shutil.copyfile(here / "V158RecentlyAdded.kt", java / "data/V158RecentlyAdded.kt")
shutil.copyfile(here / "V158RecentlyAddedTest.kt", tests / "data/V158RecentlyAddedTest.kt")
vm = java / "MainViewModel.kt"
replace_once(vm, "V157RecentlyAdded.select(all, 36)", "V158RecentlyAdded.select(all, 36)")
replace_once(vm, "V157RecentlyAdded.select(all, 300)", "V158RecentlyAdded.select(all, 300)")

# Xtream movies usually send "added"; series commonly send "last_modified".
# v1.0.57 dropped the latter field entirely, hiding genuine recent series.
xtream = java / "data/XtreamClient.kt"
source = xtream.read_text()
old_date = 'addedAt = o.optString("added").toLongOrNull() ?: 0L'
if source.count(old_date) != 2:
    raise SystemExit(f"Expected exactly 2 Xtream MOVIE/SERIES date fields, got {source.count(old_date)}")
xtream.write_text(source.replace(old_date, 'addedAt = V158ProviderDates.fromRow(o, kind)'))
shutil.copyfile(here / "V158ProviderDates.kt", java / "data/V158ProviderDates.kt")
shutil.copyfile(here / "V158ProviderDatesTest.kt", tests / "data/V158ProviderDatesTest.kt")

# Always offer the real recent section as a category as well as on the
# movie/series overview; avoid duplicate synthetic rows in the category rail.
hub = java / "ui/V060CinematicHub.kt"
replace_once(
    hub,
    '''    val visibleCategories = remember(u.categories, u.hiddenCategoryIds, u.catalogRows) {
        u.categories.filter {
            it.id != "__recently_added__" && it.id !in u.hiddenCategoryIds && u.catalogRows[it.id].orEmpty().isNotEmpty()
        }
    }''',
    '''    val visibleCategories = remember(kind, u.categories, u.hiddenCategoryIds, u.catalogRows) {
        val providerCategories = u.categories.filter {
            it.id != "__recently_added__" &&
                it.id !in u.hiddenCategoryIds &&
                u.catalogRows[it.id].orEmpty().isNotEmpty()
        }
        val recentItems = u.catalogRows["__recently_added__"].orEmpty()
            .filter { it.categoryId !in u.hiddenCategoryIds }
        val recentCategory = if ((kind == MediaKind.MOVIE || kind == MediaKind.SERIES) &&
            recentItems.isNotEmpty()) {
            de.epimediahub.app.model.MediaCategory("__recently_added__", "Zuletzt hinzugefügt")
        } else null
        listOfNotNull(recentCategory) + providerCategories
    }'''
)

# Add a real remote-control shortcut to the already existing Weiterschauen
# row. This does NOT start another playback session or download another catalog.
replace_once(
    hub,
    '''    onOverview: () -> Unit,
    onCategory: (Int, MediaCategory) -> Unit
) {''',
    '''    onOverview: () -> Unit,
    onCategory: (Int, MediaCategory) -> Unit,
    showContinue: Boolean,
    onContinue: () -> Unit
) {'''
)
replace_once(
    hub,
    '''            itemsIndexed(categories, key = { _, category -> "rail:" + category.id }, contentType = { _, _ -> "category" })''',
    '''            if (showContinue) {
                item(key = "rail-continue") {
                    V071CategoryRailItem(
                        title = "Weiterschauen",
                        selected = selectedId == "__continue__",
                        accent = accent,
                        modifier = if (selectedId == "__continue__") Modifier.focusRequester(selectedFocus) else Modifier,
                        onClick = onContinue
                    )
                }
            }
            itemsIndexed(categories, key = { _, category -> "rail:" + category.id }, contentType = { _, _ -> "category" })'''
)
replace_once(
    hub,
    '''                        categories = visibleCategories,
                        selectedId = selectedCategoryId,
                        accent = accent,
                        onOverview = {''',
    '''                        categories = visibleCategories,
                        selectedId = selectedCategoryId,
                        accent = accent,
                        showContinue = continueItems.isNotEmpty(),
                        onContinue = {
                            selectedCategoryId = "__continue__"
                            // Hero and actions precede the existing Weiterschauen row.
                            scrollToCategory((if (hero != null) 1 else 0) + 1)
                        },
                        onOverview = {'''
)

# The header got stuck on 1.0.33 because it was copied from a static UI string.
# Read the actual installed APK version instead of perpetually patching text.
home = java / "ui/V083Home.kt"
header = home.read_text()
pattern = r'if \(isTv\) "ANDROID TV · [0-9.]+" else "ANDROID MOBILE · [0-9.]+"'
replacement = (
    'if (isTv) "ANDROID TV · ${de.epimediahub.app.BuildConfig.VERSION_NAME}" '
    'else "ANDROID MOBILE · ${de.epimediahub.app.BuildConfig.VERSION_NAME}"'
)
header, count = re.subn(pattern, lambda _: replacement, header)
if count != 1:
    raise SystemExit(f"Expected one static Android header version, got {count}")
home.write_text(header)

# Existing fixture deliberately omits provider added dates. Since that is no
# longer proof of a recent addition, the fake section must remain empty.
catalogue_test = tests / "ui/V128CatalogueLoadingTest.kt"
replace_once(catalogue_test,
    '            assertEquals(2, vm.ui.value.catalogRows["__recently_added__"].orEmpty().size)',
    '            assertTrue(vm.ui.value.catalogRows["__recently_added__"].orEmpty().isEmpty())'
)

assert "V158RecentlyAdded.select(all, 36)" in vm.read_text()
assert "V158RecentlyAdded.select(all, 300)" in vm.read_text()
assert "V158ProviderDates.fromRow(o, kind)" in xtream.read_text()
assert "showContinue = continueItems.isNotEmpty()" in hub.read_text()
assert 'title = "Weiterschauen"' in hub.read_text()
assert "V156ExactM3uCache.resolve(" in xtream.read_text()
assert "${de.epimediahub.app.BuildConfig.VERSION_NAME}" in home.read_text()
print("v1.0.58 candidate: corrected Xtream provider dates, recent category, Weiterschauen rail and real APK version.")
print("Live TV URL handling and VPN controls were not changed.")
