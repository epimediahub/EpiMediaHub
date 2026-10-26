#!/usr/bin/env python3
"""Safety isolation for Fire TV cadence crash in the v184 QA build only.

Keep cadence metrics active, but do not change the Android display mode for
Live TV. This is temporary diagnostic containment, NOT a final judder fix.
"""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
surface = root / "app/src/main/java/de/epimediahub/app/ui/V121VodSurface.kt"
source = surface.read_text(encoding="utf-8")
old = "request = displayLease.match(fps, view, allow1080p = false, liveTv = true)"
new = 'request = "Live-TV: Display-Moduswechsel in dieser Diagnoseversion deaktiviert"'
assert source.count(old) == 1, "STOP: live display mode switch anchor changed; do not build unsafe QA"
source = source.replace(old, new, 1)
assert old not in source
surface.write_text(source, encoding="utf-8")
print("Crash-safe QA guard: Live-TV automatic display mode requests disabled; metrics retained.")
