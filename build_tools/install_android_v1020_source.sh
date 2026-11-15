#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"
bash build_tools/install_android_v1019_source.sh
python3 android/v1.0.20/patch_v120.py
grep -Fq 'versionCode = 1020' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.20"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'v120RememberLicenseState' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"
grep -Fq 'https://api.epimediahub.com/v1/license/status' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/V120LicenseManager.kt"
echo 'Android 1.0.20 credit and license source reconstructed successfully'
