#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v052_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.6.0/patch_v060.py

grep -q 'versionName = "0.6.0"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 600' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'fun V060CinematicHubScreen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
grep -Fq 'ZULETZT GESEHEN' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V060CinematicHub.kt"
grep -Fq 'catalogRows' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'skinMarkRes' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/BrowserRows.kt"
grep -Fq 'Trailer ansehen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V043Details.kt"

echo "Android v0.6.0 cinematic UI source reconstructed successfully"
