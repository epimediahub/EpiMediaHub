#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v062_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.6.3/patch_v063.py

grep -q 'versionName = "0.6.3"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 603' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'sourceProfileId' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/model/Models.kt"
grep -Fq 'sourceProfile ?: _ui.value.active' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'catalogRows = emptyMap()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'urls += "$server/live/$user/$pass/$id"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'useController=item.kind!=MediaKind.LIVE' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'if(item.kind==MediaKind.LIVE && controls)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'EpiMediaHub beenden?' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"

echo "Android v0.6.3 source reconstructed successfully"
