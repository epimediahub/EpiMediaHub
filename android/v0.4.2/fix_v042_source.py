#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
p = root / "app/src/main/java/de/epimediahub/app/data/MediathekClient.kt"
s = p.read_text()
s = s.replace(r"\\s", r"\s").replace(r'\\"', r'"')
p.write_text(s)
print("Normalized v0.4.2 Mediathek artwork regex")
