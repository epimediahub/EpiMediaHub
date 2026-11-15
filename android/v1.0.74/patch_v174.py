#!/usr/bin/env python3
"""v174 GalaBox-only diagnostic (no encryption policy change, no public updater)."""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
src = root / "app/src/main/java/de/epimediahub/app/vpn"

def replace(path, old, new):
    value=path.read_text()
    if value.count(old)!=1:
        raise RuntimeError(f"v174 patch needs exactly one anchor in {path}: {old[:90]!r}")
    path.write_text(value.replace(old,new,1))

gradle=root/"app/build.gradle.kts"
replace(gradle,"versionCode = 1073","versionCode = 1074")
replace(gradle,'versionName = "1.0.73"','versionName = "1.0.74"')
shutil.copyfile(here/"V174GalaBoxKeystoreProbe.kt",src/"V174GalaBoxKeystoreProbe.kt")
settings=src/"V141VpnSettings.kt"
replace(settings,
'''        V141FocusButton("Finnland-VPN verbinden / prüfen", accent, onClick = {
''',
'''        // Local-only capability probe. NEVER called on Amazon or at app startup.
        // No customer VPN credentials, keys, profiles or licenses are changed.
        if (V173GalaBoxKeyCompat.supported(context)) {
            V141FocusButton("GalaBox: Android-Keystore prüfen", accent, onClick = {
                if (!busy) {
                    busy = true
                    status = "GalaBox-Schlüsselspeicher wird lokal untersucht …"
                    scope.launch {
                        val report = withContext(Dispatchers.IO) {
                            runCatching { V174GalaBoxKeystoreProbe.summary(context) }
                        }
                        busy = false
                        status = report.getOrElse {
                            "GalaBox-Diagnose fehlgeschlagen: " + it.javaClass.simpleName
                        }
                    }
                }
            }, enabled = !busy)
        }
        V141FocusButton("Finnland-VPN verbinden / prüfen", accent, onClick = {
''')
assert "V174GalaBoxKeystoreProbe.summary(context)" in settings.read_text()
print("v174: only non-Amazon on-demand Keystore probe; VPN keys and entitlements unchanged")
