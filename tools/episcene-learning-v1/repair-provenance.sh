#!/usr/bin/env bash
# EpiScene provenance service repair. Production database remains read-only.
set -Eeuo pipefail
umask 077
BASE=/var/lib/episcene-learning
APP=/opt/episcene-learning
SOURCE=/var/lib/epimediahub/provisioning.db
SYNC=episcene-learning-provenance
PIN=65caeb51e547feb82c5e69f95a0c688691e2b507
SOURCE_SHA=7498064806ab89af5d14e7cef9023510ae494f07975fe736cd394c3f2d8d308b
TMP=$(mktemp -d -t episcene-repair.XXXXXXXX)
trap 'rm -rf -- "$TMP"' EXIT
[[ $EUID -eq 0 ]] || { echo 'Bitte als root ausfuehren.' >&2; exit 2; }
for bin in curl sha256sum install python3 systemctl; do command -v "$bin" >/dev/null || { echo "Missing: $bin" >&2; exit 2; }; done
[[ -f "$SOURCE" && -f "$BASE/knowledge.sqlite3" && -d "$APP" ]] || { echo 'Original-DB oder Learning Engine fehlen.' >&2; exit 2; }
id episcene-learning >/dev/null 2>&1 || { echo 'Servicebenutzer fehlt.' >&2; exit 2; }
for p in "$SOURCE" "$BASE" "$APP"; do [[ ! -L "$p" ]] || { echo "Unsafe symlink: $p" >&2; exit 2; }; done
curl --fail --silent --show-error --location --retry 2 --max-time 30 \
 "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$PIN/tools/episcene-learning-v1/approval_history_bridge.py" \
 -o "$TMP/approval_history_bridge.py"
printf '%s  %s\n' "$SOURCE_SHA" "$TMP/approval_history_bridge.py" | sha256sum -c -
PYTHONDONTWRITEBYTECODE=1 python3 - "$TMP/approval_history_bridge.py" <<'PY'
import sys
compile(open(sys.argv[1],'rb').read(),sys.argv[1],'exec')
print('Python bridge verified')
PY

# Store one extra online snapshot before first repaired import, without touching source.
install -d -o episcene-learning -g episcene-learning -m 0700 "$BASE/backups"
backup="$BASE/backups/knowledge-before-provenance-repair.sqlite3"
if [[ ! -e "$backup" ]]; then
  python3 - "$BASE/knowledge.sqlite3" "$backup" <<'PY_BACKUP'
import sqlite3,sys,os,pwd
src,dest=sys.argv[1:]
with sqlite3.connect(src) as inp, sqlite3.connect(dest) as out:
    inp.backup(out)
user=pwd.getpwnam('episcene-learning')
os.chown(dest,user.pw_uid,user.pw_gid)
os.chmod(dest,0o600)
print('Learning database backup created')
PY_BACKUP
fi

# The old service invoked runuser while sandboxed. Split into separate systemd identities.
install -d -o root -g episcene-learning -m 0750 "$BASE/provenance"
install -o root -g root -m 0644 "$TMP/approval_history_bridge.py" "$APP/approval_history_bridge.py"
cat > /usr/local/sbin/episcene-learning-provenance-export.sh <<'EXPORT'
#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
BASE=/var/lib/episcene-learning/provenance
TMP="$(mktemp -d "$BASE/.export.XXXXXXXX")"
trap 'rm -rf -- "$TMP"' EXIT
python3 /opt/episcene-learning/approval_history_bridge.py export --file "$TMP/latest.jsonl"
chgrp episcene-learning "$TMP/latest.jsonl"
chmod 0640 "$TMP/latest.jsonl"
mv -f -- "$TMP/latest.jsonl" "$BASE/latest.jsonl"
EXPORT
chmod 0750 /usr/local/sbin/episcene-learning-provenance-export.sh
chown root:root /usr/local/sbin/episcene-learning-provenance-export.sh

cat > "/etc/systemd/system/$SYNC.service" <<'EXPORT_UNIT'
[Unit]
Description=EpiScene Learning provenance source export (shadow / read-only)
After=local-fs.target
OnSuccess=episcene-learning-provenance-import.service
[Service]
Type=oneshot
User=root
Group=root
UMask=0077
ExecStart=/usr/local/sbin/episcene-learning-provenance-export.sh
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/episcene-learning/provenance
PrivateTmp=true
PrivateNetwork=true
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
EXPORT_UNIT

cat > "/etc/systemd/system/$SYNC-import.service" <<'IMPORT_UNIT'
[Unit]
Description=EpiScene Learning provenance import as restricted service user
After=local-fs.target
[Service]
Type=oneshot
User=episcene-learning
Group=episcene-learning
UMask=0077
ExecStart=/usr/bin/python3 /opt/episcene-learning/approval_history_bridge.py import --file /var/lib/episcene-learning/provenance/latest.jsonl
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/episcene-learning
PrivateTmp=true
PrivateNetwork=true
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
IMPORT_UNIT

systemctl daemon-reload
systemctl reset-failed "$SYNC.service" "$SYNC-import.service" >/dev/null 2>&1 || true
systemctl start "$SYNC.service"
# Run once synchronously so import errors become visible immediately. OnSuccess
# may already have started it; importing snapshots again is idempotent.
systemctl start "$SYNC-import.service"
systemctl enable --now "$SYNC.timer" >/dev/null
printf '\n===== LIVE EXPORT =====\n'
journalctl -u "$SYNC.service" -n 8 --no-pager -o cat || true
printf '\n===== LIVE IMPORT =====\n'
journalctl -u "$SYNC-import.service" -n 12 --no-pager -o cat || true
printf '\n===== SCHEDULING =====\n'
systemctl is-enabled "$SYNC.timer"
echo 'DONE: historical candidates synced in shadow mode; no human labels or customer approvals changed.'
