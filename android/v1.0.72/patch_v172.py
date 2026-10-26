#!/usr/bin/env python3
"""v1.0.72: remove permanent VOD diagnostics watermark, retain opt-in player info.

The top-right 'Player / Diagnose' action was temporarily added during v168
player troubleshooting. All settings/diagnostics remain accessible through
Audio & Untertitel -> Wiedergabe-Info, and MENU/INFO on TV remotes.
Keep v171 remote focus and v170 frame matching unchanged.
"""
import os
from pathlib import Path

root=Path(os.environ["PROJECT_ROOT"])
app=root/"app"
ui=app/"src/main/java/de/epimediahub/app/ui"

def replace_once(file,old,new):
    value=file.read_text()
    matches=value.count(old)
    if matches!=1:
        raise SystemExit(f"v172 incompatible {file}: found {matches} anchors for {old[:110]}")
    file.write_text(value.replace(old,new,1))

gradle=app/"build.gradle.kts"
replace_once(gradle,"versionCode = 1071","versionCode = 1072")
replace_once(gradle,'versionName = "1.0.71"','versionName = "1.0.72"')

player=ui/"PlayerScreen.kt"
replace_once(player,'''            if (!covered) TextButton(onClick = { showPlaybackInfo = true },
                modifier = Modifier.align(Alignment.TopEnd).padding(10.dp).v114FocusRing()) {
                Text("Player / Diagnose")
            }
''', '')
chrome=ui/"V115PlayerChrome.kt"
source=chrome.read_text()
assert 'if (dialog == "info") V122PlaybackInfoDialog' in source
assert 'onInfo = { dialog = "info" }' in source
assert 'focusProperties { right = outroNextFocus }' in source
assert 'Player / Diagnose' not in player.read_text()
assert 'showPlaybackInfo = true' in player.read_text()
assert 'if (!cinemaVod)' in (ui/"V121VodSurface.kt").read_text()
print("v172: permanent diagnostic overlay removed; settings and MENU still expose info.")
