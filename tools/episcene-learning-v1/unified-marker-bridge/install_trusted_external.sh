#!/usr/bin/env bash
# Safe, idempotent activation of trusted external EpiScene marker prefetch.
# Does not change existing endpoint, player, provisioning DB or learned markers.
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

[[ $# -eq 1 && ( "$1" == "--check" || "$1" == "--apply" ) ]] || {
  echo "Usage: bash install_trusted_external.sh --check|--apply" >&2; exit 2;
}
[[ "$EUID" -eq 0 ]] || { echo "STOP: root required" >&2; exit 2; }
SOURCE_DIR="$(cd -- "$(dirname -- "$0")" && pwd -P)"
DEST=/opt/episcene-learning/unified
DATA=/var/lib/episcene-learning
PROD=/var/lib/epimediahub/provisioning.db
SERVICE=/etc/systemd/system/episcene-trusted-sources.service
TIMER=/etc/systemd/system/episcene-trusted-sources.timer
for bin in python3 systemctl install sha256sum readlink stat; do
  command -v "$bin" >/dev/null || { echo "STOP: missing $bin" >&2; exit 2; }
done
PYTHON="$(readlink -f "$(command -v python3)")"
[[ -x "$PYTHON" && -f "$PYTHON" ]] || { echo "STOP: python3 invalid" >&2; exit 2; }
"$PYTHON" -c 'import sys; assert sys.version_info >= (3,10)' || {
  echo "STOP: Python 3.10+ required" >&2; exit 2;
}
[[ -d "$DEST" && ! -L "$DEST" && -d "$DATA" && ! -L "$DATA" ]] || {
  echo "STOP: existing EpiScene knowledge install missing" >&2; exit 2;
}
[[ "$(stat -c '%a' "$DATA")" == 700 ]] || {
  echo "STOP: EpiScene knowledge directory must be private 0700" >&2; exit 2;
}
[[ -f "$PROD" && ! -L "$PROD" ]] || {
  echo "STOP: production data source missing or symbolic link" >&2; exit 2;
}
for f in bridge.py runtime_integration.py trusted_external.py trusted_external_sync.py \
         test_bridge.py test_trusted_external.py test_trusted_external_sync.py; do
  [[ -f "$SOURCE_DIR/$f" && ! -L "$SOURCE_DIR/$f" ]] || {
    echo "STOP: missing reviewed release file $f" >&2; exit 2;
  }
done
for f in bridge.py runtime_integration.py; do
  [[ -f "$DEST/$f" && ! -L "$DEST/$f" ]] || {
    echo "STOP: EpiScene server dependency missing" >&2; exit 2;
  }
  cmp -s "$DEST/$f" "$SOURCE_DIR/$f" || {
    echo "STOP: server has different $f revision; no changes made" >&2; exit 2;
  }
done
echo "=== Isolated external trusted source tests ==="
(cd "$SOURCE_DIR" &&
 "$PYTHON" -m py_compile trusted_external.py trusted_external_sync.py &&
 "$PYTHON" -m unittest -q test_trusted_external test_trusted_external_sync)
[[ -d /run/systemd/system ]] || {
  echo "STOP: systemd is not active" >&2; exit 2;
}
[[ ! -L "$SERVICE" && ! -L "$TIMER" ]] || {
  echo "STOP: unexpected systemd symbolic link" >&2; exit 2;
}
if [[ -f "$SERVICE" || -f "$TIMER" ]]; then
  echo "STOP: existing trusted source service requires manual review" >&2; exit 2
fi
for f in trusted_external.py trusted_external_sync.py; do
  if [[ -e "$DEST/$f" ]]; then
    echo "STOP: already installed $f; no overwrite" >&2; exit 2
  fi
done
echo "PRECHECK OK: trusted source integration can be installed independently."
if [[ "$1" == "--check" ]]; then exit 0; fi

install -m 0644 -o root -g root "$SOURCE_DIR/trusted_external.py" "$DEST/trusted_external.py"
install -m 0644 -o root -g root "$SOURCE_DIR/trusted_external_sync.py" "$DEST/trusted_external_sync.py"

cat > "$SERVICE" <<SERVICE_UNIT
[Unit]
Description=EpiScene trusted IntroDB and TheIntroDB metadata-only prefetch
After=network-online.target episcene-unified-sync.service
Wants=network-online.target

[Service]
Type=oneshot
User=root
Group=root
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=$PYTHON $DEST/trusted_external_sync.py --limit 40
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelModules=true
ProtectKernelTunables=true
ProtectControlGroups=true
PrivateDevices=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
ReadWritePaths=$DATA
TimeoutStartSec=300
SERVICE_UNIT
cat > "$TIMER" <<'TIMER_UNIT'
[Unit]
Description=EpiScene trusted external marker refresh every hour
[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=180
Unit=episcene-trusted-sources.service
[Install]
WantedBy=timers.target
TIMER_UNIT
chmod 0644 "$SERVICE" "$TIMER"
systemctl daemon-reload
systemctl enable --now episcene-trusted-sources.timer
systemctl start episcene-trusted-sources.service
systemctl is-active --quiet episcene-trusted-sources.timer
echo "EPISCENE TRUSTED EXTERNAL PREFETCH INSTALL SUCCESS"
echo "Existing approved markers and customer-facing playback endpoint unchanged."
echo "The current metadata source must provide actual IMDb/TVDB IDs to fetch markers."
