#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v0417_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.18/patch_v0418.py

grep -q 'versionName = "0.4.18"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 58' "$PROJECT_ROOT/app/build.gradle.kts"
GATE="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ProvisioningGateActivity.kt"

grep -Fq 'https://setup.epimediahub.com' "$GATE"
if grep -R -Fq 'https://epimedia.tail58077d.ts.net' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app"; then
  echo 'obsolete Funnel hostname remains in Android source' >&2
  exit 1
fi

echo "Android v0.4.18 epimediahub.com provisioning source reconstructed successfully"
