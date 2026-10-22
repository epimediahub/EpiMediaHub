#!/usr/bin/env bash
# One-command guarded release of the existing EpiScene device lookup.
# Original /v1/device/skip/lookup is patched only after exact-code review,
# service-account check and isolated tests. The Python patcher saves the
# original code and rolls back on restart failure.
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1
if [[ $# -ne 1 || ( "$1" != "--apply" && "$1" != "--check" ) ]]; then
  echo "Usage: bash bootstrap_live_lookup.sh --check|--apply" >&2
  exit 2
fi
[[ "$(id -u)" -eq 0 ]] || {
  echo "STOP: use root account on EpiScene analysis Hetzner host" >&2
  exit 2
}
for cmd in python3 curl mktemp systemctl; do
  command -v "$cmd" >/dev/null || {
    echo "STOP: required local tool missing" >&2; exit 2;
  }
done

REV=37c97b4ca0091258b335e32790aace34ffed23c3
BASE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$REV/tools/episcene-learning-v1/unified-marker-bridge"
WORK="$(mktemp -d -t episcene-live-lookup.XXXXXXXX)"
trap 'rm -rf -- "$WORK"' EXIT
for f in production_lookup_cache.py patch_live_lookup.py \
         test_production_lookup_cache.py test_patch_live_lookup.py; do
  curl --fail --silent --show-error --location --retry 2 --max-time 45 \
    "$BASE/$f" --output "$WORK/$f"
  [[ -s "$WORK/$f" ]] || {
    echo "STOP: incomplete trusted GitHub release" >&2; exit 2;
  }
done

echo "=== Isolated EpiScene final playback integration tests ==="
(
 cd "$WORK"
 python3 -m py_compile production_lookup_cache.py patch_live_lookup.py \
   test_production_lookup_cache.py test_patch_live_lookup.py
 python3 -m unittest -q test_production_lookup_cache test_patch_live_lookup
)
echo "=== Validate exact original live Flask handler and private cache ==="
python3 "$WORK/patch_live_lookup.py" check \
  --dependency "$WORK/production_lookup_cache.py"
echo "CHECK PASS: no product or customer data changed."
if [[ "$1" == "--check" ]]; then
  echo "READY_FOR_CONTROLLED_RELEASE"
  exit 0
fi

echo "=== Install guarded trusted playback cache bridge ==="
echo "Only the existing provisioning API service is restarted."
python3 "$WORK/patch_live_lookup.py" apply \
  --dependency "$WORK/production_lookup_cache.py"
echo "=== Post-install status ==="
systemctl is-active episcene-unified-sync.timer
systemctl is-active episcene-trusted-sources.timer
systemctl is-active epimediahub-provisioning.service
echo "EPISCENE LIVE DEVICE LOOKUP DEPLOYMENT COMPLETE"
echo "Verify a real Fire TV episode to confirm externally sourced skip buttons."
