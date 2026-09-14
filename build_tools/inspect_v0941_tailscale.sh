#!/usr/bin/env bash
set -euo pipefail
# Re-run inspection for Android auto-provisioning parity.
W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.41.ipk"
T=/tmp/inspect_v0941_tailscale
rm -rf "$T"
mkdir -p "$T/ar" "$T/data"
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
