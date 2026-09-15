#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/EpiMediaHub_v0.9.41.ipk"
OUT="$ROOT/EpiMediaHub_v0.9.42.ipk"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/ar" "$WORK/root"
cd "$WORK/ar"
ar x "$SRC"
CONTROL_ARCHIVE=""
DATA_ARCHIVE=""
for f in control.tar.gz control.tar.xz control.tar.zst; do [[ -f "$f" ]] && CONTROL_ARCHIVE="$f"; done
for f in data.tar.gz data.tar.xz data.tar.zst; do [[ -f "$f" ]] && DATA_ARCHIVE="$f"; done
[[ -n "$CONTROL_ARCHIVE" && -n "$DATA_ARCHIVE" ]] || { echo "Unsupported IPK archives"; exit 1; }
mkdir "$WORK/control" "$WORK/data"
tar -xf "$CONTROL_ARCHIVE" -C "$WORK/control"
tar -xf "$DATA_ARCHIVE" -C "$WORK/data"
PLUGIN="$WORK/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub"
python3 "$ROOT/build_tools/patch_v0942_receiver_sync.py" "$PLUGIN/plugin.py"
cp "$ROOT/enigma_sync/receiver_sync_client.py" "$PLUGIN/receiver_sync_client.py"
# Update package metadata without disturbing dependencies/architecture.
sed -i 's/^Version: .*/Version: 0.9.42/' "$WORK/control/control"
# Repack using gzip for broad opkg compatibility.
cd "$WORK/control" && tar -czf "$WORK/control.tar.gz" .
cd "$WORK/data" && tar -czf "$WORK/data.tar.gz" .
printf '2.0\n' > "$WORK/debian-binary"
cd "$WORK"
ar r "$OUT" debian-binary control.tar.gz data.tar.gz >/dev/null
# Build-time safety checks.
mkdir "$WORK/verify" && cd "$WORK/verify"
ar x "$OUT"
mkdir data && tar -xzf data.tar.gz -C data
VP="data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub"
grep -q 'PLUGIN_VERSION = "0.9.42"' "$VP/plugin.py"
grep -q '_start_receiver_config_sync()' "$VP/plugin.py"
grep -q '/v1/device/config' "$VP/receiver_sync_client.py"
grep -q '/v1/device/sync-result' "$VP/receiver_sync_client.py"
grep -q '/v1/device/bootstrap' "$VP/receiver_sync_client.py"
echo "Built $OUT"
sha256sum "$OUT"
