#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$APP_DIR/.venv"
SERVICE_FILE="/etc/systemd/system/epimediahub-public-gateway.service"

if [ ! -x "$VENV/bin/python" ]; then
  echo "Virtualenv fehlt: $VENV" >&2
  exit 1
fi

TAILSCALE_IP="$(tailscale ip -4 | head -n1)"
if [ -z "$TAILSCALE_IP" ]; then
  echo "Keine Tailscale IPv4 gefunden." >&2
  exit 1
fi

sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=EpiMediaHub public provisioning gateway
After=network-online.target tailscaled.service epimediahub.service
Wants=network-online.target tailscaled.service
Requires=epimediahub.service

[Service]
Type=simple
User=epi
WorkingDirectory=$APP_DIR
Environment=EPIMEDIAHUB_INTERNAL_URL=http://$TAILSCALE_IP:8787
Environment=PORT=8790
ExecStart=$VENV/bin/python $APP_DIR/public_gateway.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now epimediahub-public-gateway.service
sleep 1

echo
echo "Gateway service:"
sudo systemctl --no-pager --full status epimediahub-public-gateway.service | sed -n '1,14p'

echo
echo "Local health check:"
curl -fsS http://127.0.0.1:8790/health
echo

echo
echo "Next: expose ONLY this gateway with Tailscale Funnel:"
echo "  sudo tailscale funnel --bg 8790"
echo "  sudo tailscale funnel status"
