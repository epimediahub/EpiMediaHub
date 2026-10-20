#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash deploy/install_backend.sh" >&2
  exit 1
fi

SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR=/opt/epimediahub/provisioning
DATA_DIR=/var/lib/epimediahub
ETC_DIR=/etc/epimediahub
SERVICE=/etc/systemd/system/epimediahub-provisioning.service

apt-get update
apt-get install -y python3 python3-venv python3-pip rsync openssl curl ca-certificates

if ! id epimediahub >/dev/null 2>&1; then
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin epimediahub
fi

mkdir -p "$APP_DIR" "$DATA_DIR" "$ETC_DIR"
rsync -a --delete --exclude deploy "$SRC_DIR/" "$APP_DIR/"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [ ! -f "$ETC_DIR/provisioning.env" ]; then
  ADMIN_TOKEN="$(openssl rand -hex 32)"
  ADMIN_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
  SECRET_KEY="$(openssl rand -hex 48)"
  cat > "$ETC_DIR/provisioning.env" <<EOF
EPIMEDIAHUB_PUBLIC_URL=https://setup.epimediahub.com
EPIMEDIAHUB_DATA_DIR=$DATA_DIR
EPIMEDIAHUB_ADMIN_TOKEN=$ADMIN_TOKEN
EPIMEDIAHUB_ADMIN_PASSWORD=$ADMIN_PASSWORD
EPIMEDIAHUB_SECRET_KEY=$SECRET_KEY
PORT=8787
EOF
  chmod 600 "$ETC_DIR/provisioning.env"
  cat > /root/epimediahub-admin-credentials.txt <<EOF
EpiMediaHub Admin
URL: https://admin.epimediahub.com/admin/login
Password: $ADMIN_PASSWORD
API token: $ADMIN_TOKEN
EOF
  chmod 600 /root/epimediahub-admin-credentials.txt
  echo "Admin credentials saved to /root/epimediahub-admin-credentials.txt"
fi

chown -R epimediahub:epimediahub "$APP_DIR" "$DATA_DIR"
cp "$SRC_DIR/deploy/epimediahub-provisioning.service" "$SERVICE"
systemctl daemon-reload
systemctl enable --now epimediahub-provisioning.service
sleep 2
curl --fail --silent http://127.0.0.1:8787/health
printf '\nEpiMediaHub backend installed and listening only on 127.0.0.1:8787\n'
