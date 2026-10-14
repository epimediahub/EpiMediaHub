#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"
bash build_tools/install_android_v0414_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.4.15/patch_v0415.py

grep -q 'versionName = "0.4.15"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 55' "$PROJECT_ROOT/app/build.gradle.kts"
UPDATER="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"
SCREEN="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/UpdateScreen.kt"
grep -Fq 'candidates.maxByOrNull { it.second.versionCode }' "$UPDATER"
grep -Fq 'candidate("release")' "$UPDATER"
grep -Fq 'Installiert: ${BuildConfig.VERSION_NAME} / Server:' "$SCREEN"
grep -Fq '${applicationId}.fileprovider' "$PROJECT_ROOT/app/src/main/AndroidManifest.xml"
grep -Fq 'FLAG_GRANT_READ_URI_PERMISSION' "$UPDATER"
echo "Android v0.4.15 updater diagnostics reconstructed successfully"
