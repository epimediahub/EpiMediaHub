#!/usr/bin/env bash
# Reproducible one-command deployment of trusted external sources to EpiScene.
# No IPTV streams, no edits to provisioning.db, skip_records or Android code.
set -Eeuo pipefail
umask 077
[[ "$EUID" -eq 0 ]] || { echo "STOP: root account required"; exit 2; }
for b in curl mktemp sha256sum bash python3; do
  command -v "$b" >/dev/null || { echo "STOP: missing $b"; exit 2; }
done
REV=3d1f94002d5a94d88fb7a1704911cc8b9df384a0
BASE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$REV/tools/episcene-learning-v1/unified-marker-bridge"
WORK="$(mktemp -d -t episcene-trusted.XXXXXXXX)"
trap 'rm -rf -- "$WORK"' EXIT
for f in bridge.py runtime_integration.py test_bridge.py \
         trusted_external.py trusted_external_sync.py \
         test_trusted_external.py test_trusted_external_sync.py \
         install_trusted_external.sh; do
   curl --fail --silent --show-error --location --retry 2 --max-time 45 \
    "$BASE/$f" -o "$WORK/$f"
   [[ -s "$WORK/$f" ]] || { echo "STOP: incomplete GitHub download"; exit 2; }
done
echo "=== EpiScene trusted public marker sources ==="
bash "$WORK/install_trusted_external.sh" --check
bash "$WORK/install_trusted_external.sh" --apply
echo "=== Trusted IntroDB / TheIntroDB prefetch status ==="
systemctl is-active episcene-trusted-sources.timer
systemctl is-enabled episcene-trusted-sources.timer
journalctl -u episcene-trusted-sources.service --no-pager -n 20 -o cat \
  | grep -E 'status|analysed|trusted_segments|conflicting|source|missing_canonical|no_ip_streams_opened|production_database_written' \
  | tail -n 12 || true
echo "TRUSTED EXTERNAL SOURCE PREFETCH INSTALLED"
echo "Playback API still requires server-side identity/authorization wiring."
