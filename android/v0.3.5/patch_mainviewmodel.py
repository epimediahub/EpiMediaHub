#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_mainviewmodel.py <MainViewModel.kt>')

p = Path(sys.argv[1])
s = p.read_text()

# Add the currently scoped library kind for in-library search/favorites.
s = s.replace(
    '    val details: Map<String, MediaEntry> = emptyMap(),\n    val detailLoading: Set<String> = emptySet()\n)',
    '    val details: Map<String, MediaEntry> = emptyMap(),\n    val detailLoading: Set<String> = emptySet(),\n    val contentFilterKind: MediaKind? = null\n)',
    1
)

# Browser memory: category + exact row/scroll position, kept in the ViewModel while the app is alive.
anchor = '    private var webAdmin: LocalWebAdmin? = null\n'
insert = '''    private var webAdmin: LocalWebAdmin? = null\n    private var pendingAutoOpenKind: MediaKind? = null\n    private val lastLibraryCategory = mutableMapOf<String, String>()\n    private val browsePositions = mutableMapOf<String, Int>()\n    private val browseSelections = mutableMapOf<String, String>()\n\n    private fun libraryKey(kind: MediaKind): String = "${_ui.value.active?.id.orEmpty()}|${kind.name}"\n    private fun browseKey(kind: MediaKind, categoryId: String): String = "${libraryKey(kind)}|$categoryId"\n\n    fun rememberBrowserPosition(kind: MediaKind, categoryId: String, index: Int, itemId: String) {\n        val key = browseKey(kind, categoryId)\n        browsePositions[key] = index.coerceAtLeast(0)\n        browseSelections[key] = itemId\n    }\n\n    fun browserPosition(kind: MediaKind, categoryId: String): Int = browsePositions[browseKey(kind, categoryId)] ?: 0\n    fun browserSelectedId(kind: MediaKind, categoryId: String): String = browseSelections[browseKey(kind, categoryId)].orEmpty()\n\n    fun openLibrary(kind: MediaKind) {\n        pendingAutoOpenKind = kind\n        set { it.copy(contentFilterKind = kind) }\n        navigate(Screen.Categories(kind))\n    }\n\n    fun switchLibraryCategory(kind: MediaKind, category: MediaCategory) {\n        lastLibraryCategory[libraryKey(kind)] = category.id\n        set { it.copy(contentFilterKind = kind) }\n        navigate(Screen.Items(kind, category), remember = false)\n    }\n\n    fun openKindSearch(kind: MediaKind) {\n        set { it.copy(contentFilterKind = kind, searchResults = emptyList()) }\n        navigate(Screen.Search)\n    }\n\n    fun openKindFavorites(kind: MediaKind) {\n        set { it.copy(contentFilterKind = kind) }\n        navigate(Screen.Favorites)\n    }\n'''
if anchor not in s:
    raise SystemExit('webAdmin anchor missing')
s = s.replace(anchor, insert, 1)

# Remember the currently selected category whenever Items is opened.
s = s.replace(
    '            is Screen.Items -> loadItems(screen.kind, screen.category.id)\n',
    '            is Screen.Items -> {\n                lastLibraryCategory[libraryKey(screen.kind)] = screen.category.id\n                set { it.copy(contentFilterKind = screen.kind) }\n                loadItems(screen.kind, screen.category.id)\n            }\n',
    1
)

# After categories are loaded from Home, open the last used category (or first category)
# without inserting an extra back-stack level. Back from the browser therefore returns Home.
old_success = '''            }.onSuccess { categories ->\n                set { it.copy(loading = false, categories = categories) }\n            }.onFailure { e ->'''
new_success = '''            }.onSuccess { categories ->\n                set { it.copy(loading = false, categories = categories) }\n                if (pendingAutoOpenKind == kind && _ui.value.screen == Screen.Categories(kind) && categories.isNotEmpty()) {\n                    pendingAutoOpenKind = null\n                    val rememberedId = lastLibraryCategory[libraryKey(kind)]\n                    val category = categories.firstOrNull { it.id == rememberedId } ?: categories.first()\n                    navigate(Screen.Items(kind, category), remember = false)\n                } else if (pendingAutoOpenKind == kind) {\n                    pendingAutoOpenKind = null\n                }\n            }.onFailure { e ->'''
if old_success not in s:
    raise SystemExit('loadCategories success block missing')
s = s.replace(old_success, new_success, 1)

# Scope Search to the library section from which it was opened.
old_search_head = '''    fun search(q: String) {\n        val p = _ui.value.active ?: return\n        if (q.length < 2) {'''
new_search_head = '''    fun search(q: String) {\n        val p = _ui.value.active ?: return\n        val filterKind = _ui.value.contentFilterKind\n        if (q.length < 2) {'''
if old_search_head not in s:
    raise SystemExit('search head missing')
s = s.replace(old_search_head, new_search_head, 1)

old_xtream = '''                        (c.entries(MediaKind.LIVE) + c.entries(MediaKind.MOVIE) + c.entries(MediaKind.SERIES))\n                            .filter { it.name.contains(q, true) }\n                            .take(250)'''
new_xtream = '''                        (c.entries(MediaKind.LIVE) + c.entries(MediaKind.MOVIE) + c.entries(MediaKind.SERIES))\n                            .filter { item ->\n                                val matchesKind = filterKind == null || item.kind == filterKind ||\n                                    (filterKind == MediaKind.SERIES && item.kind == MediaKind.EPISODE)\n                                matchesKind && item.name.contains(q, true)\n                            }\n                            .take(250)'''
if old_xtream not in s:
    raise SystemExit('Xtream search block missing')
s = s.replace(old_xtream, new_xtream, 1)

old_m3u = '''                        m3uResult(p).entries.filter { it.name.contains(q, true) }.take(250)'''
new_m3u = '''                        m3uResult(p).entries.filter { item ->\n                            val matchesKind = filterKind == null || item.kind == filterKind ||\n                                (filterKind == MediaKind.SERIES && item.kind == MediaKind.EPISODE)\n                            matchesKind && item.name.contains(q, true)\n                        }.take(250)'''
if old_m3u not in s:
    raise SystemExit('M3U search block missing')
s = s.replace(old_m3u, new_m3u, 1)

p.write_text(s)
print('MainViewModel.kt patched for Android v0.3.5 browser navigation')
