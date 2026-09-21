#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at reconstructed Android project}"

bash build_tools/install_android_v076_source.sh
python3 android/v0.7.7/patch_v077.py

grep -Fq 'versionName = "0.7.7"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionCode = 707' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'data object Revoked' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
grep -Fq 'config.optJSONArray("playlists")' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
grep -Fq 'repo.savePlaylists(emptyList())' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/SetupCodeProvisioning.kt"
grep -Fq 'SetupCodeProvisioning.sessionToken(context.applicationContext) == null' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"

echo "Android v0.7.7 source reconstructed successfully"
