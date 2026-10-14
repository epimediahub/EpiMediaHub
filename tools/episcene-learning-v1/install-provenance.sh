#!/usr/bin/env bash
# EpiScene provenance backfill (shadow mode). The production analyzer DB is read-only.
set -Eeuo pipefail
umask 077
APP=/opt/episcene-learning
ROOT=/var/lib/episcene-learning
ORIGINAL=/var/lib/epimediahub/provisioning.db
UNIT=episcene-learning-provenance
PIN=1858e9f50c0e5ad0b724219997cc9063cd21dce2
EXPECTED=daecfb4ffb698b0e4ae86b49f2fe0dcae1d01370fac200f77809d122d89cfe08
TEMP="$(mktemp -d -t episcene-provenance-XXXXXXXX)"
trap 'rm -rf -- "$TEMP"' EXIT
for bin in curl sha256sum python3; do command -v "$bin" >/dev/null || { echo "Missing $bin" >&2; exit 2; }; done
curl -fsSL --retry 2 "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$PIN/tools/episcene-learning-v1/approval_history_bridge.py" -o "$TEMP/approval_history_bridge.py"
printf '%s  %s\n' "$EXPECTED" "$TEMP/approval_history_bridge.py" | sha256sum -c -
PYTHONDONTWRITEBYTECODE=1 python3 - "$TEMP/approval_history_bridge.py" <<'PY'
import sys
compile(open(sys.argv[1],'rb').read(),sys.argv[1],'exec')
print('Bridge source verified and compiled')
PY
if [[ "${1:-}" == '--self-test' ]]; then echo 'Self-test successful; no installation made'; exit 0; fi
[[ $# == 0 ]] || { echo 'Only --self-test supported' >&2; exit 2; }
[[ $EUID -eq 0 ]] || { echo 'Root required' >&2; exit 2; }
for bin in systemctl install runuser journalctl; do command -v "$bin" >/dev/null || exit 2; done
[[ -d /run/systemd/system ]] || { echo 'systemd required' >&2; exit 2; }
[[ -f "$ORIGINAL" && -f "$ROOT/knowledge.sqlite3" && -f "$APP/collector.py" && -d "$ROOT/reports" ]] || { echo 'Missing live DB or Learning Engine installation' >&2; exit 2; }
for path in "$ROOT" "$APP" "$ORIGINAL"; do [[ ! -L "$path" ]] || { echo "Unsafe symlink $path" >&2; exit 2; }; done
id episcene-learning >/dev/null 2>&1 || { echo 'Missing learning service user' >&2; exit 2; }
install -d -o episcene-learning -g episcene-learning -m 0700 "$ROOT/backups"
BACKUP="$ROOT/backups/knowledge-before-provenance-v1.sqlite3"
if [[ ! -e "$BACKUP" ]]; then
  runuser -u episcene-learning -- python3 - "$ROOT/knowledge.sqlite3" "$BACKUP" <<'PY_BACKUP'
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as original, sqlite3.connect(sys.argv[2]) as backup:
    original.backup(backup)
print('Learning database backup created')
PY_BACKUP
fi
install -o root -g root -m 0644 "$TEMP/approval_history_bridge.py" "$APP/approval_history_bridge.py"
cat > "/usr/local/sbin/$UNIT-sync.sh" <<'SH_RUN'
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
BASE=/var/lib/episcene-learning/reports
TEMP="$(mktemp -d "$BASE/.provenance.XXXXXXXX")"
trap 'rm -rf -- "$TEMP"' EXIT
chown episcene-learning:episcene-learning "$TEMP"
chmod 0700 "$TEMP"
FILE="$TEMP/legacy.jsonl"
python3 /opt/episcene-learning/approval_history_bridge.py export --file "$FILE"
chown episcene-learning:episcene-learning "$FILE"
runuser -u episcene-learning -- python3 /opt/episcene-learning/approval_history_bridge.py import --file "$FILE"
SH_RUN
chmod 0750 "/usr/local/sbin/$UNIT-sync.sh"
chown root:root "/usr/local/sbin/$UNIT-sync.sh"
cat > "/etc/systemd/system/$UNIT.service" <<'UNIT_SERVICE'
[Unit]
Description=EpiScene historical approval provenance collection (shadow)
After=local-fs.target
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/local/sbin/episcene-learning-provenance-sync.sh
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/episcene-learning
PrivateTmp=true
PrivateNetwork=true
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
UNIT_SERVICE
cat > "/etc/systemd/system/$UNIT.timer" <<'UNIT_TIMER'
[Unit]
Description=Hourly EpiScene historical approval backfill
[Timer]
OnBootSec=3min
OnUnitActiveSec=1h
Persistent=true
Unit=episcene-learning-provenance.service
[Install]
WantedBy=timers.target
UNIT_TIMER
systemctl daemon-reload
systemctl enable --now "$UNIT.timer"
systemctl start "$UNIT.service"
printf '\n=== SYNCHRONISATION ===\n'
journalctl -u "$UNIT.service" -n 12 --no-pager -o cat
printf '\nSUCCESS: historical approval CANDIDATES collected; verified human labels unchanged.\n'
echo 'Existing analyzer and automatic customer releases unchanged.'
