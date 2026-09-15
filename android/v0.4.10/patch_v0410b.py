#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
p = root / "app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"
s = p.read_text()
old = '''        val raspberryName = raspberry?.HostName?.ifBlank {\n            raspberry.DNSName.substringBefore('.').ifBlank { "Raspberry" }\n        }.orEmpty()'''
new = '''        val raspberryName = raspberry?.let { peer ->\n            peer.HostName.ifBlank { peer.DNSName.substringBefore('.').ifBlank { "Raspberry" } }\n        }.orEmpty()'''
if s.count(old) != 1:
    raise SystemExit("v0.4.10 Raspberry peer-name anchor missing")
p.write_text(s.replace(old, new, 1))
print("Android v0.4.10 peer-name compile hardening applied")
