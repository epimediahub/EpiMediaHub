#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v078_source.sh
python3 android/v0.7.9/patch_v079.py

grep -Fq 'versionName = "0.7.9"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 709' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'fun V079HomeScreen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V079Home.kt"
grep -Fq 'fun V079ThemesScreen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V079Themes.kt"
grep -Fq 'PRIVATE DESIGNS' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V079Themes.kt"
grep -Fq 'val city: String' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/V070WeatherClient.kt"
grep -Fq 'Accept-Language' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/V070WeatherClient.kt"
grep -Fq 'fun lockPrivateSkins()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"

echo "Android v0.7.9 source reconstructed successfully"
