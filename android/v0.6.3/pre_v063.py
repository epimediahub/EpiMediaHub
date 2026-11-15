#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
path = root / "app/src/main/java/de/epimediahub/app/MainViewModel.kt"
s = path.read_text()

needle = "    fun selectPlaylist(id: String) {"
start = s.find(needle)
if start < 0:
    raise SystemExit("selectPlaylist function not found")
brace = s.find("{", start)
if brace < 0:
    raise SystemExit("selectPlaylist opening brace not found")

depth = 0
end = None
for i in range(brace, len(s)):
    ch = s[i]
    if ch == "{":
        depth += 1
    elif ch == "}":
        depth -= 1
        if depth == 0:
            end = i + 1
            break
if end is None:
    raise SystemExit("selectPlaylist closing brace not found")

normalized = '''    fun selectPlaylist(id: String) {
        val p = _ui.value.playlists.firstOrNull { it.id == id } ?: return
        prefs.activePlaylistId = id
        set { it.copy(active = p, screen = Screen.Home, categories = emptyList(), items = emptyList(), epg = emptyMap()) }
    }'''

path.write_text(s[:start] + normalized + s[end:])
print("selectPlaylist normalized for v0.6.3 patch")
