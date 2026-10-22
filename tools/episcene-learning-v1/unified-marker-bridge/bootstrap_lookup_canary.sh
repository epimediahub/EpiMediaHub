#!/usr/bin/env bash
# EpiScene trusted external skip marker SHADOW check, no deployment.
# Download only vetted source from the immutable merged commit.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || {
  echo "STOP: run as root on the EpiScene analysis server" >&2; exit 2;
}
for name in curl mktemp python3; do
  command -v "$name" >/dev/null || {
    echo "STOP: missing $name" >&2; exit 2;
  }
done
[[ -f /opt/episcene-learning/unified/analysis_identity.py ]] || {
  echo "STOP: installed EpiScene identity resolver not found" >&2; exit 2;
}
REV=8cb742a56924761de4ff8b8815fc779f045cd073
BASE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$REV/tools/episcene-learning-v1/unified-marker-bridge"
TEMP="$(mktemp -d -t episcene-shadow.XXXXXXXX)"
trap 'rm -rf -- "$TEMP"' EXIT
for filename in production_lookup_cache.py canary_trusted_lookup.py; do
  curl -fsSL --retry 2 --max-time 30 "$BASE/$filename" -o "$TEMP/$filename"
  [[ -s "$TEMP/$filename" ]] || {
    echo "STOP: missing verified GitHub canary file" >&2; exit 2;
  }
done
python3 -m py_compile "$TEMP/production_lookup_cache.py" "$TEMP/canary_trusted_lookup.py"
echo "=== EpiScene: read-only trusted marker preview ==="
PYTHONPATH="$TEMP:/opt/episcene-learning/unified" \
  python3 "$TEMP/canary_trusted_lookup.py"
echo "=== No service, approval records, customer inventory or IPTV stream modified ==="
