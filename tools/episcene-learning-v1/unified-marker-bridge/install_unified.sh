#!/usr/bin/env bash
# Guarded installation of the EpiScene read-only unified knowledge sync.
# This does NOT install a new customer-facing marker endpoint or Android APK.
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

if [[ $# -ne 1 || ( "$1" != "--check" && "$1" != "--apply" ) ]]; then
  echo "Usage: sudo bash install_unified.sh --check|--apply" >&2; exit 2
fi
[[ "$EUID" -eq 0 ]] || { echo "STOP: root required" >&2; exit 2; }

SOURCE_DIR="$(cd -- "$(dirname -- "$0")" && pwd -P)"
SRC_DB=/var/lib/epimediahub/provisioning.db
FEEDBACK=/var/lib/episcene-learning/reference-round-40/feedback.sqlite3
STORE=/var/lib/episcene-learning/unified-markers.sqlite3
TARGET_DIR=/opt/episcene-learning/unified
SERVICE=/etc/systemd/system/episcene-unified-sync.service
TIMER=/etc/systemd/system/episcene-unified-sync.timer
# Standard-library-only sync does not depend on the application virtualenv.
PYTHON="$(command -v python3 || true)"

for tool in python3 systemctl install mktemp stat readlink; do
  command -v "$tool" >/dev/null || { echo "STOP: missing $tool" >&2; exit 2; }
done
[[ -f "$SRC_DB" && ! -L "$SRC_DB" ]] || {
  echo "STOP: production database missing or symlink" >&2; exit 2;
}
[[ -f "$FEEDBACK" && ! -L "$FEEDBACK" ]] || {
  echo "STOP: authenticated feedback database missing or symlink" >&2; exit 2;
}
[[ -n "$PYTHON" ]] || { echo "STOP: system python3 not found" >&2; exit 2; }
PYTHON_EXE="$(readlink -f -- "$PYTHON")"
[[ -f "$PYTHON_EXE" && -x "$PYTHON_EXE" ]] || {
  echo "STOP: system Python interpreter unusable" >&2; exit 2;
}
"$PYTHON_EXE" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required"' || {
  echo "STOP: Python 3.10 or newer required" >&2; exit 2;
}
echo "Preflight: production and authenticated feedback databases present; Python found."
[[ -d /run/systemd/system ]] || { echo "STOP: systemd not active" >&2; exit 2; }
[[ ! -L "$TARGET_DIR" && ! -L "$STORE" && ! -L "$SERVICE" && ! -L "$TIMER" ]] ||
  { echo "STOP: symlink at target path" >&2; exit 2; }
[[ ! -e "$SERVICE" && ! -e "$TIMER" ]] ||
  { echo "STOP: existing unit requires manual review" >&2; exit 2; }
[[ "$(stat -c '%a' /var/lib/episcene-learning)" == "700" ]] ||
  { echo "STOP: knowledge directory must have permissions 0700" >&2; exit 2; }
[[ -f "$SOURCE_DIR/bridge.py" && -f "$SOURCE_DIR/runtime_integration.py" &&
   -f "$SOURCE_DIR/test_bridge.py" && -f "$SOURCE_DIR/test_runtime_integration.py" ]] ||
  { echo "STOP: incomplete checked-out bundle" >&2; exit 2; }

echo "=== Local backend syntax and regression suite ==="
(cd "$SOURCE_DIR" && "$PYTHON_EXE" -m py_compile bridge.py runtime_integration.py)
(cd "$SOURCE_DIR" && "$PYTHON_EXE" -m unittest -q test_bridge test_runtime_integration)

WORK="$(mktemp -d -t episcene-unified-install.XXXXXXXX)"
trap 'rm -rf -- "$WORK"' EXIT
echo "=== Read-only verification of authenticated feedback ==="
"$PYTHON_EXE" "$SOURCE_DIR/bridge.py" sync-verified \
  --feedback "$FEEDBACK" --production "$SRC_DB" --store "$WORK/verified.sqlite3"
echo "CHECK OK: production source DBs not modified."
if [[ "$1" == "--check" ]]; then exit 0; fi

[[ ! -e "$TARGET_DIR" && ! -e "$STORE" ]] || {
  echo "STOP: existing install requires review before replacement" >&2; exit 2;
}
install -d -m 0755 -o root -g root "$TARGET_DIR"
install -m 0644 -o root -g root "$SOURCE_DIR/bridge.py" "$TARGET_DIR/bridge.py"
install -m 0644 -o root -g root "$SOURCE_DIR/runtime_integration.py" "$TARGET_DIR/runtime_integration.py"
install -m 0600 -o root -g root "$WORK/verified.sqlite3" "$STORE"

cat > "$SERVICE" <<SERVICE_UNIT
[Unit]
Description=EpiScene verified knowledge sync (read-only production input)
After=local-fs.target

[Service]
Type=oneshot
User=root
Group=root
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=$PYTHON_EXE /opt/episcene-learning/unified/bridge.py sync-verified --feedback /var/lib/episcene-learning/reference-round-40/feedback.sqlite3 --production /var/lib/epimediahub/provisioning.db --store /var/lib/episcene-learning/unified-markers.sqlite3
PrivateNetwork=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ReadWritePaths=/var/lib/episcene-learning
TimeoutStartSec=90
SERVICE_UNIT

cat > "$TIMER" <<'TIMER_UNIT'
[Unit]
Description=Hourly EpiScene authenticated marker synchronization

[Timer]
OnCalendar=hourly
Persistent=true
Unit=episcene-unified-sync.service

[Install]
WantedBy=timers.target
TIMER_UNIT

chmod 0644 "$SERVICE" "$TIMER"
systemctl daemon-reload
systemctl enable --now episcene-unified-sync.timer
systemctl start episcene-unified-sync.service
systemctl is-active --quiet episcene-unified-sync.timer
echo "INSTALL OK: verified marker sync active in a separate private store."
echo "IMPORTANT: Customer-facing API and TV-player source NOT modified."
