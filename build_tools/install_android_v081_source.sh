#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v080_source.sh
python3 android/v0.8.1/patch_v081.py

grep -Fq 'versionName = "0.8.1"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 801' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'fun V081HomeScreen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V081Home.kt"
grep -Fq 'alpha = if (isTv) .50f else .62f' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V081Home.kt"
grep -Fq 'onBack != null && !isTvDevice' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Common.kt"
grep -Fq 'fun saveLocation(context: Context' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/V070WeatherClient.kt"
grep -Fq 'V081WeatherSettingsCard(accent)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
grep -Fq 'val addedAt: Long = 0L' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/model/Models.kt"
grep -Fq 'MediaCategory("__recently_added__", "Zuletzt hinzugefügt")' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq '.sortedByDescending { it.addedAt }' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
! grep -Fq 'centerMarkRes(themeId)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Common.kt"
! grep -Fq 'bannerMarkRes(themeId)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Common.kt"

echo "Android 0.8.1 source reconstructed successfully"
