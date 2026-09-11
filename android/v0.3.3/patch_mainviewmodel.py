#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_mainviewmodel.py <MainViewModel.kt>')

p = Path(sys.argv[1])
s = p.read_text()

s = s.replace('    data object WebAdmin : Screen\n', '    data object WebAdmin : Screen\n    data object Updates : Screen\n', 1)
s = s.replace(
    '    val webAdminPin: String = ""\n)',
    '    val webAdminPin: String = "",\n    val details: Map<String, MediaEntry> = emptyMap(),\n    val detailLoading: Set<String> = emptySet()\n)',
    1
)

s = s.replace(
    'set { it.copy(active = p, screen = Screen.Home, categories = emptyList(), items = emptyList(), epg = emptyMap()) }',
    'set { it.copy(active = p, screen = Screen.Home, categories = emptyList(), items = emptyList(), epg = emptyMap(), details = emptyMap(), detailLoading = emptySet()) }',
    1
)

s = s.replace(
    'set { it.copy(loading = true, items = emptyList(), epg = if (kind == MediaKind.LIVE) emptyMap() else it.epg, error = "") }',
    'set { it.copy(loading = true, items = emptyList(), epg = if (kind == MediaKind.LIVE) emptyMap() else it.epg, details = emptyMap(), detailLoading = emptySet(), error = "") }',
    1
)

marker = '    fun search(q: String) {'
if marker not in s:
    raise SystemExit('search marker missing')

insert = r'''    fun ensureDetails(item: MediaEntry) {
        if (item.kind != MediaKind.MOVIE && item.kind != MediaKind.SERIES) return
        val key = item.resumeKey
        val state = _ui.value
        if (state.details.containsKey(key) || state.detailLoading.contains(key)) return
        val profile = state.active ?: return
        if (profile.type != PlaylistType.XTREAM) return

        set { it.copy(detailLoading = it.detailLoading + key) }
        viewModelScope.launch {
            val enriched = runCatching {
                withContext(Dispatchers.IO) { XtreamClient(profile).details(item) }
            }.getOrNull()
            set {
                it.copy(
                    details = if (enriched != null) it.details + (key to enriched) else it.details,
                    detailLoading = it.detailLoading - key
                )
            }
        }
    }

    fun detailed(item: MediaEntry): MediaEntry = _ui.value.details[item.resumeKey] ?: item

'''

s = s.replace(marker, insert + marker, 1)
p.write_text(s)
print('MainViewModel.kt patched for Android v0.3.3')
