#!/usr/bin/env python3
from pathlib import Path

# Reuse the already-reviewed v0.6.3 core patch, but stop before its obsolete
# PlayerScreen anchors. PlayerScreen is patched separately against the newer
# TV keymap that is actually present in the reconstructed project.
source_path = Path(__file__).with_name("patch_v063b.py")
source = source_path.read_text()
marker = "# ---------------------------------------------------------------------------\n# Live player: no VOD seek/play/pause controller. Show our own station banner."
if marker not in source:
    raise SystemExit("v0.6.3 player section marker missing")
core = source.split(marker, 1)[0]
exec(compile(core, str(source_path) + "#core", "exec"), {"__name__": "__main__", "__file__": str(source_path)})
print("Android v0.6.3 playlist/Xtream core patch applied")
