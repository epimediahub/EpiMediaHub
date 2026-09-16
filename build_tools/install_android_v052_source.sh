#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v051_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.5.2/patch_v052.py

grep -q 'versionName = "0.5.2"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 502' "$PROJECT_ROOT/app/build.gradle.kts"
PIN="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V046Themes.kt"
DIALOG="$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V051DashboardConnect.kt"

grep -Fq 'Steuerkreuz bedienen' "$PIN"
grep -Fq 'val keys = listOf("1","2","3"' "$PIN"
grep -Fq 'BackHandler(enabled = true)' "$PIN"
grep -Fq 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789' "$DIALOG"
grep -Fq 'Die Fire-TV-Tastatur wird nicht geöffnet' "$DIALOG"
grep -Fq 'BackHandler(enabled = true)' "$DIALOG"
! grep -Fq 'OutlinedTextField(' "$DIALOG"

echo "Android v0.5.2 Fire TV D-pad setup navigation reconstructed successfully"
