#!/usr/bin/env bash
set -euo pipefail
# Inspection trigger 2.
T=/tmp/inspect_android_base
rm -rf "$T" && mkdir -p "$T"
cat android/source_parts/source_* > "$T/source.b64"
base64 --decode "$T/source.b64" > "$T/source.tar.gz"
tar -xzf "$T/source.tar.gz" -C "$T"
ROOT="$(find "$T" -maxdepth 4 -name settings.gradle.kts -printf '%h\n' | head -n1)"
echo '=== MainViewModel head ==='
sed -n '1,180p' "$ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
echo '=== MainViewModel webadmin area ==='
grep -n -C 20 -E 'startWebAdmin|LocalWebAdmin|class MainViewModel|PrefsRepository' "$ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt" || true
echo '=== Manifest ==='
cat "$ROOT/app/src/main/AndroidManifest.xml"
