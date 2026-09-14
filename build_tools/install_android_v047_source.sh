#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

rm -rf "$PROJECT_ROOT/app/src/main/java"
rm -f "$PROJECT_ROOT/app/src/main/AndroidManifest.xml"
for v in v0.3.0 v0.3.1 v0.3.2 v0.3.3 v0.3.4 v0.3.5 v0.3.6 v0.4.0 v0.4.1 v0.4.2 v0.4.3 v0.4.4 v0.4.5 v0.4.6 v0.4.7; do
  cp -a "android/$v/app/." "$PROJECT_ROOT/app/"
done

python3 - <<'PY'
import os
from pathlib import Path
p = Path(os.environ['PROJECT_ROOT']) / 'app/src/main/java/de/epimediahub/app/ui/Screens.kt'
s = p.read_text()
s = s.replace('onClick={if(kind==MediaKind.SERIES){{vm.navigate(Screen.Episodes(m))}}else{{vm.play(m)}}}', 'onClick={if(kind==MediaKind.SERIES) vm.navigate(Screen.Episodes(m)) else vm.play(m)}')
s = s.replace('onClick={if(m.kind==MediaKind.SERIES){{vm.navigate(Screen.Episodes(m))}}else{{vm.play(m)}}}', 'onClick={if(m.kind==MediaKind.SERIES) vm.navigate(Screen.Episodes(m)) else vm.play(m)}')
s = s.replace('LinearProgressIndicator({it},Modifier.fillMaxWidth().padding(top=6.dp))', 'LinearProgressIndicator(progress={it},modifier=Modifier.fillMaxWidth().padding(top=6.dp))')
p.write_text(s)
PY

python3 android/v0.3.2/patch_screens.py "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
python3 android/v0.3.3/patch_mainviewmodel.py "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
python3 android/v0.3.3/patch_screens.py "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
python3 android/v0.3.4/patch_screens.py "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
python3 android/v0.3.5/patch_mainviewmodel.py "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
python3 android/v0.3.5/patch_screens.py "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
python3 android/v0.3.6/patch_screens.py "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.0/patch_v040.py
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.1/patch_v041.py
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.2/fix_v042_source.py
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.2/patch_v042.py
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.3/patch_v043.py
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.4/patch_v044.py
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.5/patch_v045.py
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.6/patch_v046.py
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.7/patch_v047.py

grep -q 'versionName = "0.4.7"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 47' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'RemoteTailscaleManager' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -q 'provisionAndConnect(pin)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -q 'fun V047WebAdminScreen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V047WebAdmin.kt"
grep -q 'V047WebAdminScreen(vm, accent, isTv)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"
grep -q 'VpnService.prepare' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"
grep -q '192.168.0.207:8787' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"
grep -q 'com.tailscale.ipn.IPNService' "$PROJECT_ROOT/app/src/main/AndroidManifest.xml"
grep -q 'com.tailscale.ipn.App' "$PROJECT_ROOT/app/src/main/AndroidManifest.xml"
grep -q 'verifyFixedRemoteMaintenancePin' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/PrefsRepository.kt"
grep -q 'SCREEN_ORIENTATION_SENSOR_LANDSCAPE' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainActivity.kt"
grep -q 'KEYCODE_NUMPAD_5' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"

echo "Android v0.4.7 source reconstructed successfully"
