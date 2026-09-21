#!/usr/bin/env bash
set -Eeuo pipefail

export EPIMEDIAHUB_UPGRADE_BRANCH="${EPIMEDIAHUB_UPGRADE_BRANCH:-raspberry-v0.7.0-customer-device-grid}"
export EPIMEDIAHUB_TARGET_VERSION="0.7.6"
export EPIMEDIAHUB_DASHBOARD_MODULE="dashboard_v070.py"
export EPIMEDIAHUB_SMOKE_TEST="tests/smoke_v070.py"

TMP_SCRIPT="$(mktemp)"
trap 'rm -f "$TMP_SCRIPT"' EXIT
curl -fsSL "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/${EPIMEDIAHUB_UPGRADE_BRANCH}/server/epimediahub_provisioning/deploy/upgrade_to_v052.sh" -o "$TMP_SCRIPT"
exec bash "$TMP_SCRIPT"
