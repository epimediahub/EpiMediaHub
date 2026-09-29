#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v099_source.sh
bash build_tools/prepare_smarttube_core_v100.sh
python3 android/v1.0.0/patch_v100.py

grep -Fq 'versionCode = 1000' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.0"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq '"SMARTTUBE"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V083Home.kt"
grep -Fq 'val newest = u.catalogRows["__recently_added__"]' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
echo "Android 1.0.0 development source reconstructed successfully"
