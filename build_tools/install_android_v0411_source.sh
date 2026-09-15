#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v0410_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.11/patch_v0411.py

grep -q 'versionName = "0.4.11"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 51' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'showRemoteUnlock = true' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V047WebAdmin.kt"
grep -Fq 'Text("Tailscale anmelden"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V047WebAdmin.kt"
grep -Fq 'Phase.AUTH_REQUIRED' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V047WebAdmin.kt"
grep -Fq 'Notifier.browseToURL.value' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"
grep -Fq 'client.startLoginInteractive' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"

if grep -Eq 'epimedia\.local:8787|192\.168\.0\.207:8787|localProvisionerCandidates|/v1/enroll|TS_OAUTH' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"; then
  echo 'ERROR: legacy Raspberry HTTP/OAuth bootstrap remains in Android runtime' >&2
  exit 1
fi

if grep -Eqi 'wg-quick|wireguard\.conf|PrivateKey[[:space:]]*=' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"; then
  echo 'ERROR: raw WireGuard configuration detected' >&2
  exit 1
fi

if grep -Fq '←/→ Episode oder ±10 s' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"; then
  echo 'ERROR: persistent player help overlay returned' >&2
  exit 1
fi

echo "Android v0.4.11 Tailscale login-action recovery source reconstructed successfully"
