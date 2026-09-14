#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Bitte mit sudo/root starten." >&2
  exit 1
fi

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
install -d -m 0755 /opt/epimediahub
install -m 0755 "$SRC_DIR/epimediahub-provisioner.py" /opt/epimediahub/epimediahub-provisioner.py
install -m 0644 "$SRC_DIR/epimediahub-provisioner.service" /etc/systemd/system/epimediahub-provisioner.service

if [ ! -f /etc/epimediahub-provisioner.env ]; then
  cat > /etc/epimediahub-provisioner.env <<'EOF'
# Tailscale OAuth client with scope: auth_keys
# The OAuth client must be allowed to create tag:epimediahub-family.
TS_OAUTH_CLIENT_ID=
TS_OAUTH_CLIENT_SECRET=
TS_TAILNET=-
TS_DEVICE_TAG=tag:epimediahub-family

# Raspberry LAN bootstrap endpoint. This is deliberately LAN-only.
EPI_PROVISION_HOST=192.168.0.207
EPI_PROVISION_PORT=8787
EPI_PROVISION_LAN=192.168.0.0/24

# Separate fixed EpiMediaHub Fernwartungs-PIN hash (PIN itself is not stored).
EPI_REMOTE_PIN_HASH=7a866153fcd1a9ed6c44f051287622547d959709cd49731684a70dbfac852c58
TS_AUTHKEY_EXPIRY_SECONDS=300
EOF
  chmod 0600 /etc/epimediahub-provisioner.env
  echo "Konfiguration angelegt: /etc/epimediahub-provisioner.env"
  echo "Bitte TS_OAUTH_CLIENT_ID und TS_OAUTH_CLIENT_SECRET eintragen und dieses Script erneut starten."
  exit 2
fi

set -a
# shellcheck disable=SC1091
. /etc/epimediahub-provisioner.env
set +a
if [ -z "${TS_OAUTH_CLIENT_ID:-}" ] || [ -z "${TS_OAUTH_CLIENT_SECRET:-}" ]; then
  echo "TS_OAUTH_CLIENT_ID/TS_OAUTH_CLIENT_SECRET fehlen in /etc/epimediahub-provisioner.env" >&2
  exit 2
fi

systemctl daemon-reload
systemctl enable --now epimediahub-provisioner.service
sleep 1
systemctl --no-pager --full status epimediahub-provisioner.service || true

echo
echo "Provisioner aktiv. Test im Heimnetz:"
echo "  curl http://${EPI_PROVISION_HOST:-192.168.0.207}:${EPI_PROVISION_PORT:-8787}/health"
