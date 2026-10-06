#!/usr/bin/env bash
# Prepare the private Pi connection; local computation remains active until activation.
set -Eeuo pipefail
umask 0077
SOURCE_REF="82c6588b006b63b30581d102247570f16700592e"
RAW="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$SOURCE_REF/server/epimediahub_provisioning"
BASE="${EPIMEDIAHUB_APP_DIR:-/opt/epimediahub/provisioning}"
WG_ROOT="${EPIMEDIAHUB_WIREGUARD_DIR:-/etc/wireguard}"
BIN_ROOT="${EPIMEDIAHUB_ADMIN_BIN_DIR:-/usr/local/sbin}"
STAGE="$BASE/remote-analysis-stage"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
if [ "$(id -u)" != 0 ]; then echo "Bitte mit sudo ausführen." >&2; exit 1; fi
PY="$BASE/.venv/bin/python"
test -x "$PY"
test -f "$BASE/skip_catalogue.py"
REFRESH=0
if [ "${1:-}" = --refresh-code ]; then
  [ "$#" = 1 ]
  test -f "$WG_ROOT/epimediahub-analysis-client.key"
  "$PY" - "$WG_ROOT/wg-epi-analysis.conf" <<'PY'
from pathlib import Path
import sys
if not Path(sys.argv[1]).read_text().startswith('# EpiMediaHub private analysis client\n'):
    raise SystemExit('Keine vorhandene verwaltete Analyseverbindung')
PY
  systemctl is-active --quiet wg-quick@wg-epi-analysis.service
  REFRESH=1
else
"$PY" - "${1:-}" "${2:-}" <<'PY'
import ipaddress,base64,sys
try:
    address=ipaddress.ip_address(sys.argv[1])
    assert address.version==4 and address.is_global
    assert len(base64.b64decode(sys.argv[2],validate=True))==32
except (ValueError,AssertionError):
    raise SystemExit('Hetzner-IPv4 und öffentlichen Server-WireGuard-Schlüssel angeben')
PY
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends wireguard-tools curl
FILES=(skip_analysis.py skip_automation.py skip_analysis_worker.py skip_detector_v2.py skip_detector_v3.py skip_remote_client.py skip_remote_protocol.py skip_remote_verify.py skip_catalogue.py skip_schedule.py skip_app_capture.py skip_release.py skip_markers.py templates/skip_markers.html templates/skip_schedule.html skip_database.py skip_progress.py skip_progress_worker.py templates/skip_progress.html static/skip_dashboard.js deploy/epimediahub-skip-progress.service deploy/epimediahub-skip-progress.timer deploy/check_skip_latency.py)
install -d -m 0700 "$WORK/templates" "$WORK/static" "$WORK/deploy"
for file in "${FILES[@]}"; do curl -fsSL --connect-timeout 15 --max-time 90 "$RAW/$file" -o "$WORK/$file"; done
curl -fsSL --connect-timeout 15 --max-time 90 "$RAW/deploy/activate_skip_remote.sh" -o "$WORK/activate.sh"
"$PY" -m py_compile "$WORK"/*.py
bash -n "$WORK/activate.sh"
"$PY" "$WORK/skip_detector_v3.py" --selftest
install -d -m 0700 "$STAGE" "$STAGE/templates" "$STAGE/static" "$STAGE/deploy" "$WG_ROOT"
install -d -m 0755 "$BIN_ROOT"
for file in "${FILES[@]}"; do install -m 0644 "$WORK/$file" "$STAGE/$file"; done
install -m 0755 "$WORK/activate.sh" "$BIN_ROOT/epimediahub-activate-remote-analysis"
if [ "$REFRESH" = 1 ]; then
  echo "Neuer Analysecode vorbereitet; bestehende private Verbindung und Schlüssel erhalten."
  echo "Danach auf dem Raspberry: sudo $BIN_ROOT/epimediahub-activate-remote-analysis --provider-via-raspberry"
  exit 0
fi
KEY="$WG_ROOT/epimediahub-analysis-client.key"
CONF="$WG_ROOT/wg-epi-analysis.conf"
if [ ! -f "$KEY" ]; then
  if [ -f "$CONF" ]; then echo "Vorhandener Tunnel ohne Schlüsseldatei; keine automatische Änderung." >&2; exit 1; fi
  wg genkey > "$KEY"
fi
chmod 0600 "$KEY"
"$PY" - "$KEY" "$CONF" "$1" "$2" <<'PY'
from pathlib import Path
import sys
key,conf=map(Path,sys.argv[1:3])
marker='# EpiMediaHub private analysis client'
if conf.exists():
    text=conf.read_text()
    if not text.startswith(marker+'\n'):
        raise SystemExit('Gleichnamiger Tunnel gehört nicht zur Analyse')
    conf.with_suffix('.conf.previous').write_text(text)
conf.write_text(marker+'\n[Interface]\nAddress = 10.87.26.2/32\nPrivateKey = '+key.read_text().strip()+
               '\n\n[Peer]\nPublicKey = '+sys.argv[4]+'\nEndpoint = '+sys.argv[3]+':51820\nAllowedIPs = 10.87.26.1/32\nPersistentKeepalive = 25\n')
conf.chmod(0o600)
PY
systemctl enable --now wg-quick@wg-epi-analysis.service
systemctl restart wg-quick@wg-epi-analysis.service
PUBLIC_KEY="$(wg pubkey < "$KEY")"
echo "Verbindung vorbereitet. Die bisherige lokale Analyse wurde nicht abgeschaltet."
echo "Auf Hetzner ausführen:"
echo "sudo $BIN_ROOT/epimediahub-allow-raspberry '$PUBLIC_KEY'"
echo "Danach auf dem Raspberry: sudo $BIN_ROOT/epimediahub-activate-remote-analysis"
