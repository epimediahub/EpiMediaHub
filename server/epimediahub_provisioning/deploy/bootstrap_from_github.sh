#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash" >&2
  exit 1
fi

BRANCH="android-v0.4.18-domain-provisioning"
REPO="https://github.com/epimediahub/EpiMediaHub.git"
TMP="$(mktemp -d /tmp/epimediahub-bootstrap.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

apt-get update
apt-get install -y git ca-certificates

git clone --depth 1 --branch "$BRANCH" "$REPO" "$TMP/repo"
cd "$TMP/repo/server/epimediahub_provisioning"
bash deploy/install_backend.sh

echo
systemctl --no-pager --full status epimediahub-provisioning.service || true
echo
curl --fail --silent http://127.0.0.1:8787/health && echo

echo "Bootstrap completed. Admin credentials: /root/epimediahub-admin-credentials.txt"
