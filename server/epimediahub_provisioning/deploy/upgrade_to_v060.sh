#!/usr/bin/env bash
set -Eeuo pipefail

export EPIMEDIAHUB_UPGRADE_BRANCH="${EPIMEDIAHUB_UPGRADE_BRANCH:-raspberry-v0.6.0-dashboard}"
export EPIMEDIAHUB_TARGET_VERSION="0.6.0"
export EPIMEDIAHUB_DASHBOARD_MODULE="dashboard_v060.py"
export EPIMEDIAHUB_SMOKE_TEST="tests/smoke_v060.py"

CORE_SCRIPT="$(mktemp)"
SYNC_SCRIPT="$(mktemp)"
trap 'rm -f "$CORE_SCRIPT" "$SYNC_SCRIPT"' EXIT

RAW="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/${EPIMEDIAHUB_UPGRADE_BRANCH}/server/epimediahub_provisioning/deploy"

curl -fsSL "$RAW/upgrade_to_v052.sh" -o "$CORE_SCRIPT"
bash "$CORE_SCRIPT"

curl -fsSL "$RAW/install_android_release_sync.sh" -o "$SYNC_SCRIPT"
bash "$SYNC_SCRIPT"

echo
echo "Dashboard und automatische Android-Release-Synchronisierung sind aktuell."
