#!/usr/bin/env bash
set -euo pipefail
W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.41.ipk"
T=/tmp/inspect_v0941_tailscale
rm -rf "$T"
mkdir -p "$T/ar" "$T/data" "$T/android"
cd "$T/ar"
ar x "$B"
tar -xzf data.tar.gz -C ../data
P="$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub/plugin.py"
echo '=== plugin version ==='
grep -n 'PLUGIN_VERSION' "$P" | head -n 5 || true
echo '=== tailscale contexts ==='
grep -ni -C 35 'tailscale' "$P" || true
echo '=== remote access contexts ==='
grep -ni -C 20 -E 'Fernzugriff|Anmeldelink|login.*link|auth.*url|remote access' "$P" || true
cd "$W"
cat android/source_parts/source_* > "$T/android/source.b64"
base64 --decode "$T/android/source.b64" > "$T/android/source.tar.gz"
tar -xzf "$T/android/source.tar.gz" -C "$T/android"
ROOT="$(find "$T/android" -maxdepth 4 -name settings.gradle.kts -printf '%h\n' | head -n1)"
echo '=== Android MainViewModel head ==='
sed -n '1,190p' "$ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
echo '=== Android web admin anchors ==='
grep -n -C 25 -E 'startWebAdmin|LocalWebAdmin|class MainViewModel|PrefsRepository' "$ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt" || true
echo '=== Android manifest ==='
cat "$ROOT/app/src/main/AndroidManifest.xml"
