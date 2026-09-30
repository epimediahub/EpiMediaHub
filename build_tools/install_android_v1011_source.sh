#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v1010_source.sh
python3 android/v1.0.11/patch_v111.py
python3 android/v1.0.11/patch_navigation_memory_v111.py

grep -Fq 'versionCode = 1011' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.11"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V111SmartTubeShell(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V083Home.kt"
grep -Fq 'V111SmartTubeSidebar(' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V111SmartTubeShell.kt"
grep -Fq 'V097SkinEnvironment(smartTubeSkinWorld, accent)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V111SmartTubeShell.kt"
grep -Fq '.height(if (isTv) 330.dp else 245.dp)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V111SmartTubePlayer.kt"
grep -Fq 'fontSize = if (isTv) 30.sp' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V111SmartTubePlayer.kt"
grep -Fq 'v111FormatPlaybackTime(positionMs)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V111SmartTubePlayer.kt"
grep -Fq 'memoryKey = "search:"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V035Screens.kt"
grep -Fq 'V111MenuMemory.id(homeMemoryKey)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V083Home.kt"
grep -Fq 'val memoryKey = "settings"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
grep -Fq '"mediathek:countries"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/ParityScreens.kt"
grep -Fq 'v111RememberLazyListState("livetv-categories")' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V076LiveTv.kt"

echo "Android 1.0.11 development source reconstructed successfully"
