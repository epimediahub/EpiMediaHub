#!/usr/bin/env bash
# One command for the private EpiScene snapshot integration only.
# Does NOT change player APK, customer streams or public marker API.
set -Eeuo pipefail
umask 077

[[ "$(id -u)" -eq 0 ]] || { echo "STOP: run this on analysis Hetzner as root" >&2; exit 2; }
for tool in curl mktemp bash systemctl;do
  command -v "$tool" >/dev/null || { echo "STOP: missing $tool" >&2; exit 2; }
done

# Reviewed and tested commit, never download mutable HEAD during an install.
REV=96847633793d69b72c682dca5ab7d4bb0210f3c6
BASE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$REV/tools/episcene-learning-v1/unified-marker-bridge"
TEMP="$(mktemp -d -t episcene-unified-bootstrap.XXXXXXXX)"
trap 'rm -rf -- "$TEMP"' EXIT

for filename in bridge.py runtime_integration.py test_bridge.py test_runtime_integration.py install_unified.sh; do
  curl --fail --silent --show-error --location --retry 2 --max-time 45 \
    "$BASE/$filename" --output "$TEMP/$filename"
  [[ -s "$TEMP/$filename" ]] || {
    echo "STOP: missing GitHub release component" >&2; exit 2;
  }
done

echo "=== EpiScene safe preflight ==="
bash "$TEMP/install_unified.sh" --check
echo "=== EpiScene private snapshot setup ==="
bash "$TEMP/install_unified.sh" --apply
echo "=== Service checks ==="
systemctl is-active episcene-unified-sync.timer
systemctl is-enabled episcene-unified-sync.timer
systemctl is-failed episcene-unified-sync.service --quiet && {
  echo "STOP: last verified snapshot update reported failure" >&2; exit 2;
}
echo "EPISCENE SNAPSHOT INSTALL SUCCESS"
echo "NOTE: Android player and public playback endpoint not included in this stage."
