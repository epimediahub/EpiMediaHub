#!/usr/bin/env bash
# Install/update a dedicated Hetzner analysis host. No customer database is copied.
set -Eeuo pipefail
umask 0077
SOURCE_REF="874b5026729f00082ebb9372f3e10a692dfbf849"
CLIENT_INSTALLER_REF="50075d03418f9931a00522f81401727c895f51d5"
RAW="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$SOURCE_REF/server/epimediahub_provisioning"
CLIENT_INSTALLER="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$CLIENT_INSTALLER_REF/server/epimediahub_provisioning/deploy/install_skip_remote_client.sh"
BASE="${EPIMEDIAHUB_WORKER_DIR:-/opt/epimediahub/analysis}"
UNIT_ROOT="${EPIMEDIAHUB_SYSTEMD_DIR:-/etc/systemd/system}"
WG_ROOT="${EPIMEDIAHUB_WIREGUARD_DIR:-/etc/wireguard}"
BIN_ROOT="${EPIMEDIAHUB_ADMIN_BIN_DIR:-/usr/local/sbin}"
WG_NAME=wg-epi-analysis
WORK="$(mktemp -d)"
BACKUP="$BASE/backups/worker-$(date +%Y%m%d-%H%M%S)"
UNIT="$UNIT_ROOT/epimediahub-analysis-worker.service"
FILES=(requirements.txt skip_analysis.py skip_automation.py skip_markers.py skip_detector_v2.py skip_detector_v3.py skip_remote_client.py skip_remote_protocol.py skip_remote_worker.py)
INSTALLED=0
WAS_ACTIVE=0
systemctl is-active --quiet epimediahub-analysis-worker.service && WAS_ACTIVE=1 || true
cleanup() { rm -rf "$WORK"; }
rollback() {
  code=$?
  trap - ERR
  if [ "$INSTALLED" = 1 ]; then
    systemctl stop epimediahub-analysis-worker.service || true
    for file in "${FILES[@]}"; do
      if [ -f "$BACKUP/$file" ]; then cp -a "$BACKUP/$file" "$BASE/$file"; else rm -f "$BASE/$file"; fi
    done
    if [ -f "$BACKUP/worker.service" ]; then cp -a "$BACKUP/worker.service" "$UNIT"; else rm -f "$UNIT"; fi
    systemctl daemon-reload
    if [ "$WAS_ACTIVE" = 1 ]; then systemctl start epimediahub-analysis-worker.service || true; fi
  fi
  echo "Installation unterbrochen; ein vorheriger Worker wurde wiederhergestellt." >&2
  exit "$code"
}
trap cleanup EXIT
trap rollback ERR
if [ "$(id -u)" != 0 ]; then echo "Bitte mit sudo ausführen." >&2; exit 1; fi
if [ -f /opt/epimediahub/provisioning/app.py ]; then echo "Dieses Skript gehört auf den neuen Hetzner-Server, nicht auf den Raspberry." >&2; exit 1; fi
PUBLIC_IP="${1:-}"
python3 - "$PUBLIC_IP" <<'PY'
import ipaddress,sys
try:
    value=ipaddress.ip_address(sys.argv[1])
    assert value.version==4 and value.is_global
except (ValueError,AssertionError):
    raise SystemExit('Öffentliche IPv4 des Hetzner-Servers als Argument angeben')
PY

echo "Pakete für private Verbindung und Audioanalyse installieren …"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends python3-venv ffmpeg libchromaprint1 libchromaprint-tools wireguard-tools curl ca-certificates ufw
install -d -m 0755 "$BASE" "$UNIT_ROOT" "$BIN_ROOT"
install -d -m 0700 "$WG_ROOT"
for file in "${FILES[@]}"; do curl -fsSL --connect-timeout 15 --max-time 90 "$RAW/$file" -o "$WORK/$file"; done
if ! getent passwd epimediahub-worker >/dev/null; then useradd --system --home-dir "$BASE" --shell /usr/sbin/nologin epimediahub-worker; fi
umask 0022
python3 -m venv "$BASE/.venv"
"$BASE/.venv/bin/python" -m pip install --disable-pip-version-check -r "$WORK/requirements.txt"
umask 0077
"$BASE/.venv/bin/python" -m py_compile "$WORK"/*.py
"$BASE/.venv/bin/python" "$WORK/skip_detector_v3.py" --selftest
"$BASE/.venv/bin/python" - <<'PY'
import ctypes.util,shutil
assert ctypes.util.find_library('chromaprint') and shutil.which('ffmpeg')
PY
install -d -m 0700 "$BACKUP"
for file in "${FILES[@]}"; do [ ! -f "$BASE/$file" ] || cp -a "$BASE/$file" "$BACKUP/$file"; done
[ ! -f "$UNIT" ] || cp -a "$UNIT" "$BACKUP/worker.service"
if [ -f "$UNIT" ]; then systemctl stop epimediahub-analysis-worker.service; fi
INSTALLED=1
for file in "${FILES[@]}"; do install -o root -g root -m 0644 "$WORK/$file" "$BASE/$file"; done

KEY="$WG_ROOT/epimediahub-analysis-server.key"
CONF="$WG_ROOT/$WG_NAME.conf"
if [ ! -f "$KEY" ]; then
  if [ -f "$CONF" ]; then echo "Vorhandene Tunnelkonfiguration ohne Schlüsseldatei; keine automatische Änderung." >&2; false; fi
  wg genkey > "$KEY"
fi
chmod 0600 "$KEY"
python3 - "$KEY" "$CONF" <<'PY'
from pathlib import Path
import sys
key,conf=map(Path,sys.argv[1:])
marker='# EpiMediaHub private analysis server'
if conf.exists():
    if not conf.read_text().startswith(marker+'\n'):
        raise SystemExit('Gleichnamiger Tunnel gehört nicht zu diesem Worker')
else:
    conf.write_text(marker+'\n[Interface]\nAddress = 10.87.26.1/32\nListenPort = 51820\nPrivateKey = '+key.read_text().strip()+'\n')
conf.chmod(0o600)
PY
cat > "$BIN_ROOT/epimediahub-allow-raspberry" <<'SH'
#!/usr/bin/env bash
set -Eeuo pipefail
umask 0077
if [ "$(id -u)" != 0 ]; then echo "Bitte mit sudo ausführen." >&2; exit 1; fi
key="${1:-}"
root="${EPIMEDIAHUB_WIREGUARD_DIR:-/etc/wireguard}"
conf="$root/wg-epi-analysis.conf"
python3 - "$conf" "$key" <<'PY'
from pathlib import Path
import base64,sys
conf=Path(sys.argv[1]); public=sys.argv[2]
try:
    assert len(base64.b64decode(public,validate=True))==32
except (ValueError,AssertionError):
    raise SystemExit('Gültigen öffentlichen Raspberry-WireGuard-Schlüssel angeben')
text=conf.read_text()
if not text.startswith('# EpiMediaHub private analysis server\n'):
    raise SystemExit('Keine verwaltete Serverkonfiguration')
conf.with_suffix('.conf.previous').write_text(text)
conf.write_text(text.split('[Peer]',1)[0].rstrip()+'\n\n[Peer]\nPublicKey = '+public+'\nAllowedIPs = 10.87.26.2/32\n')
conf.chmod(0o600)
PY
systemctl restart wg-quick@wg-epi-analysis.service
systemctl restart epimediahub-analysis-worker.service
echo "Raspberry-Peer freigegeben. Jetzt auf dem Raspberry die Remote-Analyse aktivieren."
SH
chmod 0755 "$BIN_ROOT/epimediahub-allow-raspberry"
cat > "$UNIT" <<EOF
[Unit]
Description=EpiMediaHub private Hetzner audio and fingerprint worker
After=network-online.target wg-quick@$WG_NAME.service
Requires=wg-quick@$WG_NAME.service
[Service]
Type=simple
User=epimediahub-worker
WorkingDirectory=$BASE
ExecStart=$BASE/.venv/bin/python $BASE/skip_remote_worker.py
Restart=on-failure
RestartSec=3
Environment=OPENBLAS_NUM_THREADS=1
CPUQuota=350%
MemoryMax=3G
TasksMax=128
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
[Install]
WantedBy=multi-user.target
EOF
chmod 0644 "$UNIT"
# The HTTP API is bound only to WireGuard; never open TCP 8790 publicly.
ufw allow 22/tcp
ufw allow 51820/udp
ufw allow in on "$WG_NAME" from 10.87.26.2 to 10.87.26.1 port 8790 proto tcp
ufw --force enable
systemctl daemon-reload
systemctl enable --now "wg-quick@$WG_NAME.service"
systemctl enable --now epimediahub-analysis-worker.service
curl -fsS --retry 5 --retry-delay 2 --retry-connrefused http://10.87.26.1:8790/health -o "$WORK/health.json"
"$BASE/.venv/bin/python" - "$WORK/health.json" <<'PY'
import json,sys
assert json.load(open(sys.argv[1])).get('status')=='ok'
PY
PUBLIC_KEY="$(wg pubkey < "$KEY")"
echo "Hetzner-Worker gesund. Öffentlicher WireGuard-Schlüssel: $PUBLIC_KEY"
echo "Auf dem Raspberry ausführen:"
if "$BASE/.venv/bin/python" - "$CONF" <<'PY'
from pathlib import Path
import sys
raise SystemExit(0 if '[Peer]' in Path(sys.argv[1]).read_text() else 1)
PY
then
  echo "curl -fsSL '$CLIENT_INSTALLER' -o /tmp/epimediahub-remote-client.sh && sudo bash /tmp/epimediahub-remote-client.sh --refresh-code"
  echo "Bestehende Peer-Freigabe erhalten. Danach auf dem Raspberry: sudo /usr/local/sbin/epimediahub-activate-remote-analysis --provider-via-raspberry"
else
  echo "curl -fsSL '$CLIENT_INSTALLER' -o /tmp/epimediahub-remote-client.sh && sudo bash /tmp/epimediahub-remote-client.sh '$PUBLIC_IP' '$PUBLIC_KEY'"
fi
echo "Nur öffentliche Schlüssel werden angezeigt; private Schlüssel bleiben auf den jeweiligen Geräten."
