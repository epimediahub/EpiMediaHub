#!/usr/bin/env bash
set -Eeuo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Bitte mit sudo ausführen." >&2
  exit 1
fi

CONFIG=/etc/cloudflared/config.yml
HOST=reseller.epimediahub.com
SERVICE_URL=http://127.0.0.1:8787
STAMP="$(date +%Y%m%d-%H%M%S)"

test -f "$CONFIG"
cp -a "$CONFIG" "$CONFIG.bak-$STAMP"

python3 - "$CONFIG" "$HOST" "$SERVICE_URL" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
host = sys.argv[2]
service = sys.argv[3]
text = path.read_text()

if f"hostname: {host}" not in text:
    lines = text.splitlines()
    insert_at = None
    for i, line in enumerate(lines):
        if line.strip() == "- service: http_status:404":
            insert_at = i
            break
    if insert_at is None:
        raise SystemExit("Cloudflare ingress fallback '- service: http_status:404' nicht gefunden.")
    lines[insert_at:insert_at] = [
        f"  - hostname: {host}",
        f"    service: {service}",
    ]
    path.write_text("\n".join(lines) + "\n")
PY

if cloudflared tunnel ingress validate "$CONFIG" >/dev/null 2>&1; then
  echo "Cloudflare ingress-Konfiguration ist gültig."
else
  cp -f "$CONFIG.bak-$STAMP" "$CONFIG"
  echo "Cloudflare ingress-Konfiguration ungültig; Backup wurde wiederhergestellt." >&2
  exit 1
fi

TUNNEL="$(awk '/^tunnel:/ {print $2; exit}' "$CONFIG")"
if [ -z "$TUNNEL" ]; then
  echo "Tunnel-ID konnte aus $CONFIG nicht gelesen werden." >&2
  exit 1
fi

cloudflared tunnel route dns "$TUNNEL" "$HOST" >/dev/null 2>&1 || true
systemctl restart cloudflared
systemctl is-active --quiet cloudflared

echo "Reseller-Subdomain aktiviert: https://$HOST"
echo "Backup: $CONFIG.bak-$STAMP"
