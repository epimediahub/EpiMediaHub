#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v075_source.sh
python3 android/v0.7.6/patch_v076.py

grep -Fq 'versionName = "0.7.6"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 706' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'fun V076LiveTvScreen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V076LiveTv.kt"
grep -Fq '"GERÄT & DASHBOARD"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V070Home.kt"
grep -Fq 'Kopplungscode erzeugen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V047WebAdmin.kt"

echo "Android v0.7.6 source reconstructed successfully"
