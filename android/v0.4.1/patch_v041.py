#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"

screens = java / "ui/Screens.kt"
s = screens.read_text()
if s.count("V040HomeScreen(vm,isTv,accent)") != 1:
    raise SystemExit(f"v0.4.0 home delegate anchor mismatch: {s.count('V040HomeScreen(vm,isTv,accent)')}")
s = s.replace("V040HomeScreen(vm,isTv,accent)", "V041HomeScreen(vm,isTv,accent)", 1)
s = s.replace("Android v0.4.0", "Android v0.4.1")
screens.write_text(s)

print("Android v0.4.1 landscape/dashboard/remote patch applied")
