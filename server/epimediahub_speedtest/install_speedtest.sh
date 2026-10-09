#!/usr/bin/env bash
# Install only the loopback EpiMediaHub Speedtest. DOES NOT publish it or edit DNS,
# UFW, Caddy, WireGuard, Cloudflare tunnel, EpiScene, or any other existing service.
set -euo pipefail
if [ "$EUID" -ne 0 ]; then echo 'Bitte als root ausfuehren.' >&2; exit 1; fi
umask 022

APP_DIR=/opt/epimediahub/speedtest
SERVICE=/etc/systemd/system/epimediahub-speedtest.service
SERVER_COMMIT=10a25ccfcec9962abe8407d0217ec5e9e56560e6
SOURCE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$SERVER_COMMIT/server/epimediahub_speedtest/server.py"

command -v python3 >/dev/null || { echo "python3 fehlt (Abbruch)" >&2; exit 1; }
command -v curl >/dev/null || { echo "curl fehlt (Abbruch)" >&2; exit 1; }
command -v systemctl >/dev/null || { echo "systemd fehlt (Abbruch)" >&2; exit 1; }

echo "EpiMediaHub Speedtest: bereite abgesicherten lokalen Dienst vor"
if [ -e "$SERVICE" ] && ! grep -q '/opt/epimediahub/speedtest/server.py' "$SERVICE"; then
  echo "Anderer Dienst verwendet diesen systemd-Namen; keine Aenderung." >&2
  exit 1
fi
if ss -lntH '( sport = :8792 )' 2>/dev/null | grep -q ':8792'; then
  if ! systemctl is-active --quiet epimediahub-speedtest.service; then
    echo "Port 8792 bereits belegt; keine Aenderung." >&2
    exit 1
  fi
fi

TMP=$(mktemp --suffix=.py)
trap 'rm -f "$TMP"' EXIT
curl -fLSsS --connect-timeout 8 --max-time 40 "$SOURCE" -o "$TMP"
python3 -m py_compile "$TMP"

install -d -m 0755 "$APP_DIR"
if [ -f "$APP_DIR/server.py" ]; then
  cp -a "$APP_DIR/server.py" "$APP_DIR/server.py.backup.$(date +%Y%m%d%H%M%S)"
fi
install -m 0644 "$TMP" "$APP_DIR/server.py"
if [ ! -e "$APP_DIR/test-payload.bin" ]; then
  # Sparse zero file: appears as 128 MiB but uses almost no physical disk.
  truncate -s 134217728 "$APP_DIR/test-payload.bin"
fi
if [ "$(stat -c '%s' "$APP_DIR/test-payload.bin")" -lt 134217728 ]; then
  echo "Testdatei ist unvollstaendig; Installation abgebrochen" >&2
  exit 1
fi

cat > "$SERVICE" <<'UNIT'
[Unit]
Description=EpiMediaHub isolated self-hosted speedtest (loopback only)
Documentation=https://github.com/epimediahub/EpiMediaHub
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
DynamicUser=yes
ExecStart=/usr/bin/python3 /opt/epimediahub/speedtest/server.py
WorkingDirectory=/opt/epimediahub/speedtest
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
MemoryMax=256M
CPUQuota=150%
TasksMax=96
Nice=5
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now epimediahub-speedtest.service
systemctl restart epimediahub-speedtest.service

for attempt in $(seq 1 20); do
  if curl -fsS --max-time 2 http://127.0.0.1:8792/v1/health >/dev/null; then break; fi
  sleep 1
done

echo "=== Lokaler Healthcheck ==="
curl -fsS --max-time 3 http://127.0.0.1:8792/v1/health
echo

echo "=== Integritaetsprobe: echte Download/Upload-Daten ==="
python3 - <<'PY'
import json, urllib.request
base = 'http://127.0.0.1:8792'
with urllib.request.urlopen(urllib.request.Request(
    base+'/v1/session', data=b'', method='POST'), timeout=5) as result:
    token=json.load(result)['session']
auth={'Authorization': 'Bearer '+token}
with urllib.request.urlopen(urllib.request.Request(
    base+'/v1/down?bytes=1048576&stream=0', headers=auth), timeout=10) as result:
    data=result.read()
    assert result.status==200 and len(data)==1048576
payload=b'x'*(256*1024)
with urllib.request.urlopen(urllib.request.Request(
    base+'/v1/up', data=payload, headers=auth, method='POST'), timeout=10) as result:
    assert json.load(result)['received']==len(payload)
print('PASS: 1 MiB Download + 256 KiB Upload; Sessionauthentifizierung aktiv')
PY

echo "=== Dienst ==="
systemctl --no-pager --full status epimediahub-speedtest.service | sed -n '1,13p'
echo
echo "Erfolgreich. Nur an 127.0.0.1:8792 erreichbar."
echo "Keine Firewall, DNS, VPN, EpiScene oder oeffentliche HTTPS-Freigabe geaendert."
