#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v074_source.sh
python3 android/v0.7.5/patch_v075.py

grep -Fq 'versionName = "0.7.5"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 705' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'fun V075LiveTvScreen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V075LiveTv.kt"
grep -Fq 'V075LiveTvScreen(vm, accent, isTv)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"

echo "Android v0.7.5 source reconstructed successfully"
