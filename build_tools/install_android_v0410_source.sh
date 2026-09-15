#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

# Build on the signed/released v0.4.9 source and replace only the remote-access
# bootstrap. All player/UI fixes from v0.4.9 remain intact.
bash build_tools/install_android_v049_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.10/patch_v0410.py

grep -q 'versionName = "0.4.10"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 50' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'com.tailscale.ipn.ui.notifier.Notifier' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"
grep -Fq 'Notifier.browseToURL.value' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"
grep -Fq 'client.startLoginInteractive' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"
grep -Fq 'Phase.AUTH_REQUIRED' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V047WebAdmin.kt"
grep -Fq 'ParityQrCode(ts.authUrl)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V047WebAdmin.kt"
grep -Fq 'peer.HostName.equals("epimedia"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"

# v0.4.10 must not depend on the old LAN provisioner at runtime.
if grep -Eq 'epimedia\.local:8787|192\.168\.0\.207:8787|localProvisionerCandidates|/v1/enroll|TS_OAUTH' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"; then
  echo 'ERROR: legacy Raspberry HTTP/OAuth bootstrap remains in Android runtime' >&2
  exit 1
fi

# This is Tailscale-native. No manual WireGuard configuration may be added.
if grep -Eqi 'wg-quick|wireguard\.conf|PrivateKey[[:space:]]*=' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/RemoteTailscaleManager.kt"; then
  echo 'ERROR: raw WireGuard configuration detected' >&2
  exit 1
fi

# Keep the v0.4.9 player cleanup and remote key mappings.
if grep -Fq '←/→ Episode oder ±10 s' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"; then
  echo 'ERROR: persistent player help overlay returned' >&2
  exit 1
fi
grep -q 'KEYCODE_NUMPAD_5' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"

echo "Android v0.4.10 direct Tailscale source reconstructed successfully"
