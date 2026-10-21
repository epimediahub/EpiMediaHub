#!/usr/bin/env bash
# Pinned EpiScene existing IMDb/TMDB identity source repair.
# No IPTV streams, no modification of production marker records or Android.
set -Eeuo pipefail
umask 077
[[ "$EUID" -eq 0 ]] || { echo "STOP: root required" >&2; exit 2; }
for b in curl mktemp bash; do
  command -v "$b" >/dev/null || { echo "STOP: missing $b" >&2; exit 2; }
done
NEW=766aa467f1eeb6725b096d770ae7fed1a390ec2d
OLD=3d1f94002d5a94d88fb7a1704911cc8b9df384a0
ROOT="https://raw.githubusercontent.com/epimediahub/EpiMediaHub"
PATH_PART="tools/episcene-learning-v1/unified-marker-bridge"
WORK="$(mktemp -d -t episcene-existing-id.XXXXXXXX)"
trap 'rm -rf -- "$WORK"' EXIT
mkdir -m 700 -- "$WORK/baseline"
for f in bridge.py runtime_integration.py trusted_external.py trusted_external_sync.py \
         analysis_identity.py test_bridge.py test_trusted_external.py \
         test_trusted_external_sync.py test_analysis_identity.py \
         install_existing_identity_fix.sh; do
  curl --fail --silent --show-error --location --retry 2 --max-time 45 \
    "$ROOT/$NEW/$PATH_PART/$f" -o "$WORK/$f"
  [[ -s "$WORK/$f" ]] || {
    echo "STOP: incomplete reviewed GitHub release" >&2; exit 2;
  }
done
for f in bridge.py trusted_external.py trusted_external_sync.py; do
  curl --fail --silent --show-error --location --retry 2 --max-time 45 \
    "$ROOT/$OLD/$PATH_PART/$f" -o "$WORK/baseline/$f"
  [[ -s "$WORK/baseline/$f" ]] || {
    echo "STOP: prior release baseline unavailable" >&2; exit 2;
  }
done
echo "=== Safe metadata-only source repair ==="
bash "$WORK/install_existing_identity_fix.sh" --check
bash "$WORK/install_existing_identity_fix.sh" --apply
echo "=== EpiScene trusted external source summary ==="
systemctl is-active episcene-trusted-sources.timer
systemctl is-enabled episcene-trusted-sources.timer
journalctl --no-pager -u episcene-trusted-sources.service -n 30 -o cat \
  | grep -E '"(status|analysed|trusted_segments|identity_candidates_checked|identity_conflicts_skipped|conflicting_segment_types|no_ip_streams_opened|production_database_written)"' \
  | tail -n 14 || true
echo "EPISCENE TRUSTED IDENTITY SOURCES UPGRADED"
echo "NOTE: this enables external prefetched marker cache; playback API not changed."
