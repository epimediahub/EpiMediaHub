#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v079_source.sh
python3 android/v0.8.0/patch_v080.py

grep -Fq 'versionName = "0.8"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 800' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'fun V080HomeScreen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V080Home.kt"
grep -Fq 'ANDROID TV · 0.8' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V080Home.kt"
grep -Fq 'val unlocked = prefs.familySkinsUnlocked()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'Dauerhaft freigeschaltet' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V079Themes.kt"
! grep -Fq '"GERÄT & DASHBOARD"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V080Home.kt"

echo "Android 0.8 source reconstructed successfully"
