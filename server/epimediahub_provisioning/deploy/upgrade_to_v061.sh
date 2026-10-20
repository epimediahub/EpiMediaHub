#!/usr/bin/env bash
set -Eeuo pipefail

export EPIMEDIAHUB_UPGRADE_BRANCH="${EPIMEDIAHUB_UPGRADE_BRANCH:-raspberry-v0.6.1-device-assignment}"
export EPIMEDIAHUB_TARGET_VERSION="0.6.1"
export EPIMEDIAHUB_DASHBOARD_MODULE="dashboard_v061.py"
export EPIMEDIAHUB_SMOKE_TEST="tests/smoke_v061.py"

TMP_SCRIPT="$(mktemp)"
trap 'rm -f "$TMP_SCRIPT"' EXIT
curl -fsSL "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/${EPIMEDIAHUB_UPGRADE_BRANCH}/server/epimediahub_provisioning/deploy/upgrade_to_v052.sh" -o "$TMP_SCRIPT"
exec bash "$TMP_SCRIPT"
