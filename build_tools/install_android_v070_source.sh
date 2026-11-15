#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v06415_source.sh
python3 android/v0.7.0/patch_v070.py

grep -Fq 'versionName = "0.7.0"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 700' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'fun V070HomeScreen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V070Home.kt"
grep -Fq 'fun V070PlaylistsScreen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V070Playlists.kt"
grep -Fq 'fun V070IntroScreen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V070Intro.kt"
grep -Fq 'height(if (isTv) 68.dp else 78.dp)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/BrowserRows.kt"
grep -Fq 'android:banner="@drawable/tv_launcher_banner"' "$PROJECT_ROOT/app/src/main/AndroidManifest.xml"
grep -Fq 'releases/tags/v0.7.0-test' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/UpdateManager.kt"

echo "Android v0.7.0 source reconstructed successfully"
