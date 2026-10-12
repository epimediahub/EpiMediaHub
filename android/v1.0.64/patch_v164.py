#!/usr/bin/env python3
"""Android 1.0.64: explicit ANNUAL_ACTIVE / ANNUAL_EXPIRED app license handling.

Run only after the reviewed v1.0.63 reconstruction patches.
No automatic rollout, updater edits or VPN/playback changes.
"""
from pathlib import Path
import os

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"


def replace(path, old, new):
    content = path.read_text()
    assert content.count(old) == 1, f"Expected exactly one v164 anchor in {path}: {old[:100]!r}"
    path.write_text(content.replace(old, new, 1))


gradle = root / "app/build.gradle.kts"
replace(gradle, "versionCode = 1063", "versionCode = 1064")
replace(gradle, 'versionName = "1.0.63"', 'versionName = "1.0.64"')

manager = java / "data/V120LicenseManager.kt"
gate = java / "ui/V120LicenseGate.kt"

replace(manager,
    "CHECKING, TRIAL_ACTIVE, TRIAL_EXPIRED, LIFETIME_ACTIVE, ERROR",
    "CHECKING, TRIAL_ACTIVE, TRIAL_EXPIRED, ANNUAL_ACTIVE, ANNUAL_EXPIRED, LIFETIME_ACTIVE, ERROR")
replace(manager,
    "kind == V120LicenseKind.TRIAL_ACTIVE || kind == V120LicenseKind.LIFETIME_ACTIVE",
    "kind == V120LicenseKind.TRIAL_ACTIVE || kind == V120LicenseKind.ANNUAL_ACTIVE || kind == V120LicenseKind.LIFETIME_ACTIVE")
replace(manager,
    '.put("platform", "android")\n',
    '.put("platform", "android")\n                .put("supported_entitlements", org.json.JSONArray().put("ANNUAL"))\n')
replace(manager, '"EpiMediaHub-Android/1.0.20"', '"EpiMediaHub-Android/1.0.64"')
replace(manager,
    'cached.kind == V120LicenseKind.LIFETIME_ACTIVE || cached.kind == V120LicenseKind.TRIAL_EXPIRED',
    'cached.kind == V120LicenseKind.LIFETIME_ACTIVE || cached.kind == V120LicenseKind.TRIAL_EXPIRED || cached.kind == V120LicenseKind.ANNUAL_EXPIRED')
replace(manager,
    'cached.kind != V120LicenseKind.TRIAL_ACTIVE',
    'cached.kind != V120LicenseKind.TRIAL_ACTIVE && cached.kind != V120LicenseKind.ANNUAL_ACTIVE')
replace(manager,
    'else cached.copy(kind = V120LicenseKind.TRIAL_EXPIRED, remainingSeconds = 0L)',
    'else cached.copy(kind = if (cached.kind == V120LicenseKind.ANNUAL_ACTIVE) V120LicenseKind.ANNUAL_EXPIRED else V120LicenseKind.TRIAL_EXPIRED, remainingSeconds = 0L)')
replace(manager,
    '"LIFETIME_ACTIVE" -> V120LicenseState(V120LicenseKind.LIFETIME_ACTIVE, null, expires)',
    '"LIFETIME_ACTIVE" -> V120LicenseState(V120LicenseKind.LIFETIME_ACTIVE, null, expires)\n'
    '            "ANNUAL_ACTIVE" -> V120LicenseState(V120LicenseKind.ANNUAL_ACTIVE, remaining, json.optString("annual_expires_at"))\n'
    '            "ANNUAL_EXPIRED" -> V120LicenseState(V120LicenseKind.ANNUAL_EXPIRED, 0L, json.optString("annual_expires_at"))')

replace(gate,
    'V120LicenseKind.TRIAL_ACTIVE -> {',
    'V120LicenseKind.TRIAL_ACTIVE, V120LicenseKind.ANNUAL_ACTIVE -> {')
replace(gate,
    'val expired = state.kind == V120LicenseKind.TRIAL_EXPIRED',
    'val expired = state.kind == V120LicenseKind.TRIAL_EXPIRED || state.kind == V120LicenseKind.ANNUAL_EXPIRED')
replace(gate,
    'V120LicenseKind.TRIAL_EXPIRED -> "TESTPHASE BEENDET"',
    'V120LicenseKind.TRIAL_EXPIRED -> "TESTPHASE BEENDET"\n'
    '                        V120LicenseKind.ANNUAL_EXPIRED -> "JAHRESLIZENZ BEENDET"')
replace(gate,
    'if (expired) "Deine 7-tägige Testphase ist beendet."',
    'if (state.kind == V120LicenseKind.ANNUAL_EXPIRED) "Deine Jahreslizenz ist abgelaufen."\n'
    '                    else if (expired) "Deine 7-tägige Testphase ist beendet."')
replace(gate,
    'if (expired) "Dauerhaft aktivieren für einmalig 10 € pro Gerät. Bitte wende dich an deinen Anbieter."',
    'if (state.kind == V120LicenseKind.ANNUAL_EXPIRED) "Bitte wende dich für eine Verlängerung an deinen Anbieter."\n'
    '                    else if (expired) "Dauerhaft aktivieren für einmalig 10 € pro Gerät. Bitte wende dich an deinen Anbieter."')
replace(gate,
    'if (state?.kind != V120LicenseKind.TRIAL_ACTIVE) return',
    'if (state?.kind != V120LicenseKind.TRIAL_ACTIVE && state?.kind != V120LicenseKind.ANNUAL_ACTIVE) return')
replace(gate,
    'text = if (days == 1L) "TESTVERSION · NOCH 1 TAG" else "TESTVERSION · NOCH $days TAGE",',
    'text = if (state.kind == V120LicenseKind.ANNUAL_ACTIVE) {\n'
    '                if (days == 1L) "APP-LIZENZ · NOCH 1 TAG" else "APP-LIZENZ · NOCH $days TAGE"\n'
    '            } else {\n'
    '                if (days == 1L) "TESTVERSION · NOCH 1 TAG" else "TESTVERSION · NOCH $days TAGE"\n'
    '            },')

# Separate privacy option. Disabled by default, no customer content collected.
import shutil
shutil.copyfile(Path(__file__).resolve().parent / "V164Diagnostics.kt", java / "ui/V164Diagnostics.kt")

settings = java / "ui/Screens.kt"
replace(settings,
    '            item {\\n                V163BootSettingsCard(accent)\\n            }',
    '            item {\\n                V163BootSettingsCard(accent)\\n            }\\n'
    '            item {\\n                V164DiagnosticsCard(accent)\\n            }')

entry = java / "EpiMediaHubApp.kt"
replace(entry,
    '    var v120LicenseRefresh by remember { mutableStateOf(0) }',
    '    LaunchedEffect(Unit) {\\n'
    '        de.epimediahub.app.ui.V164Diagnostics.installCrashMarker(context.applicationContext)\\n'
    '        de.epimediahub.app.ui.V164Diagnostics.uploadPending(context.applicationContext)\\n'
    '    }\\n'
    '    var v120LicenseRefresh by remember { mutableStateOf(0) }')

assert 'versionCode = 1064' in gradle.read_text()
assert 'ANNUAL_ACTIVE' in manager.read_text() and 'ANNUAL_EXPIRED' in gate.read_text()
print("Android 1.0.64: annual license and optional anonymous crash counters enabled")
