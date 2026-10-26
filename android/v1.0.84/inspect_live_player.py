#!/usr/bin/env python3
"""Private QA-only inspection of reconstructed v1.0.84 playback routing.

Prints source-code structure (no playlist data, credentials, or runtime URLs).
Does not change, compile, or execute any playback classes.
"""
import os
import re
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
ui = root / "app/src/main/java/de/epimediahub/app/ui"
app = root / "app/src/main/java/de/epimediahub/app"

patterns = {
    "PlayerScreen.kt": (r"fun PlayerScreen\b|fun V071VlcLivePlayer\b|useVlc|manualPlayerChoice|V121VodSurface|V071VlcLivePlayer|ExoPlayer|MediaKind\.LIVE|android.player|Playertyp|Player ausw|Player wechseln|\.setMediaItem|\.prepare\(", 8, 14, 325),
    "V121VodSurface.kt": (r"fun V121VodSurface|fun bind\(|fun update|class V121|fun schedule\(|fun match\(|frameRate|onVideoFrame|onRendered|request =|matchingMode|measuredFps|onVideoSizeChanged|onVideoInputFormatChanged|override fun close\(", 4, 10, 260),
    "V170LiveCadencePolicy.kt": (r".", 0, 0, 140),
    "EpiMediaHubApp.kt": (r"PlayerScreen\(|V164PlayerHost|Screen.Player", 6, 8, 65),
}
for filename, (regex, before, after, limit) in patterns.items():
    path = (app if filename == "EpiMediaHubApp.kt" else ui) / filename
    if not path.is_file():
        print("INSPECT_MISSING", filename)
        continue
    lines = path.read_text(encoding="utf-8").splitlines()
    chosen = set()
    for n, s in enumerate(lines):
        if re.search(regex, s, re.I):
            chosen.update(range(max(0, n-before), min(len(lines), n+after+1)))
    if filename == "PlayerScreen.kt":
        chosen.update(range(min(len(lines), 100)))
    print(f"\n======== {filename} ({len(lines)} lines, {len(chosen)} selected) ========")
    last = -2
    for n in sorted(chosen)[:limit]:
        if n > last + 1: print(" ...")
        print(f"{n+1:04d} {lines[n]}")
        last = n
    if len(chosen) > limit:
        print(f"... {len(chosen)-limit} source lines omitted")
print("LIVE_PLAYER_SOURCE_INSPECTION_COMPLETE")
