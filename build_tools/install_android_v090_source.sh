#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"
bash build_tools/install_android_v089_source.sh
python3 android/v0.9.0/patch_v090.py
grep -Fq 'versionCode = 900' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "0.9.0"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'androidx.media3:media3-exoplayer:1.9.4' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'private var searchJob: kotlinx.coroutines.Job? = null' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
! grep -Fq 'mutableStateOf(V072UseVlcLiveFallback(item))' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
echo "Android 0.9.0 source reconstructed successfully"
