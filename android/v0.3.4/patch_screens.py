#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_screens.py <Screens.kt>')

path = Path(sys.argv[1])
s = path.read_text()
s = s.replace('Android v0.3.3', 'Android v0.3.4')
s = s.replace('Listenansicht · Xtream-Metadaten · sichtbarer App-Updater', 'Update-Test · Listenansicht · Xtream-Metadaten · sichtbarer App-Updater')
path.write_text(s)
print('Screens.kt patched for Android v0.3.4')
