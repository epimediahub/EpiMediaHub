#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

# Reuse the fully guarded v0.4.8 reconstruction, then apply only the v0.4.9
# delta. This keeps all prior Enigma parity features and makes the new fixes
# independently auditable.
bash build_tools/install_android_v048_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.9/patch_v049.py

grep -q 'versionName = "0.4.9"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 49' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'ExecutorCompletionService' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"
grep -Fq 'NetworkInterface.getNetworkInterfaces' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"
grep -Fq 'localProvisionerCandidates()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"
grep -Fq 'json.optString("service") == "epimediahub-provisioner"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"
grep -Fq 'EpiMediaHub-Android/0.4.9' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"

if grep -Fq '←/→ Episode oder ±10 s' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"; then
  echo 'ERROR: persistent player help overlay still present' >&2
  exit 1
fi

grep -q 'KEYCODE_NUMPAD_5' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -q 'KEYCODE_NUMPAD_1' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -q 'KEYCODE_NUMPAD_3' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"

echo "Android v0.4.9 source reconstructed successfully"
