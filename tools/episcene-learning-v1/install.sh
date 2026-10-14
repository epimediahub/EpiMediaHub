#!/usr/bin/env bash
# EpiScene Learning Engine V1 — öffentliches Codepaket, keine privaten Daten
# Installation: shadow only, never touches existing EpiScene services, DBs or markers.
set -Eeuo pipefail
umask 077
APP=/opt/episcene-learning
DATA=/var/lib/episcene-learning
CFGDIR=/etc/episcene-learning
QUEUE=/var/spool/episcene-learning/inbox
USR=episcene-learning
COL=episcene-learning-collector
SYNC=episcene-learning-report-sync
ARCHIVE_SHA256='66046163e388e2eb8298deb3bf94dcbd18164080f82aaa8b8094cabe18166017'
TMP=''
trap '[[ -z "$TMP" ]] || rm -rf -- "$TMP"' EXIT
TASK=install
if [[ "${1:-}" == '--self-test' ]]; then TASK=test; shift; fi
if [[ "${1:-}" == '--status' ]]; then
  systemctl --no-pager status "$COL.timer" || true
  [[ ! -f "$DATA/last-collection.json" ]] || cat "$DATA/last-collection.json"
  exit 0
fi
if (( $# != 0 )); then echo 'Only --self-test or --status supported' >&2; exit 2; fi
for exe in bash python3 tar base64 sha256sum mktemp; do
  command -v "$exe" >/dev/null || { echo "Required tool missing: $exe" >&2; exit 2; }
done
TMP=$(mktemp -d -t episcene-public.XXXXXXXX)
mkdir -m 0700 "$TMP/package"
base64 -d > "$TMP/code.tgz" <<'__PAYLOAD_END__'
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
__PAYLOAD_END__
if [[ "$(sha256sum "$TMP/code.tgz" | cut -d ' ' -f 1)" != "$ARCHIVE_SHA256" ]]; then
  echo 'ERROR: code archive checksum mismatch' >&2; exit 3
fi
python3 - "$TMP/code.tgz" <<'PY_VERIFY'
import tarfile,sys
expected={'episcene_learning.py','collector.py','feedback_queue.py','app_backend_hook.py','test_install.py','report_sync.py'}
with tarfile.open(sys.argv[1],mode='r:gz') as tf:
    members=tf.getmembers()
    assert len(members)==len(expected) and {m.name for m in members}==expected
    assert all(m.isfile() and 0<=m.size<200000 for m in members)
PY_VERIFY
tar -xzf "$TMP/code.tgz" --no-same-owner --no-same-permissions -C "$TMP/package"
(cd "$TMP/package" && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_install.py)
python3 - "$TMP/package" <<'PY_COMPILE'
import pathlib,sys
for p in pathlib.Path(sys.argv[1]).glob('*.py'):
  compile(p.read_bytes(),str(p),'exec')
print('Python source validated')
PY_COMPILE
if [[ "$TASK" == test ]]; then
  echo 'SELF-TEST OK — code verified, learning tests passed'; exit 0
fi
if [[ $EUID -ne 0 ]]; then echo 'Administratorrechte benötigt (sudo oder root)' >&2; exit 2; fi
for exe in systemctl useradd install runuser; do
  command -v "$exe" >/dev/null || { echo "Missing server prerequisite: $exe" >&2; exit 2; }
done
[[ -d /run/systemd/system ]] || { echo 'Server does not run systemd; installation aborted' >&2; exit 2; }
for dir in "$APP" "$DATA" "$CFGDIR" "$QUEUE" "$DATA/reports"; do
  [[ ! -L "$dir" ]] || { echo "Unsafe symlink target: $dir" >&2; exit 2; }
done
if ! id "$USR" >/dev/null 2>&1; then
  useradd --system --user-group --home-dir "$DATA" --shell /usr/sbin/nologin "$USR"
fi
install -d -o root -g root -m 0755 "$APP" "$CFGDIR"
install -d -o "$USR" -g "$USR" -m 0700 "$DATA" "$DATA/reports"
install -d -o "$USR" -g "$USR" -m 2770 "$QUEUE"
# Existing knowledge DB and config are NEVER overwritten. No customer data on GitHub.
if [[ -f "$DATA/knowledge.sqlite3" ]]; then
  echo 'Existing local knowledge database preserved.'
fi
for src in episcene_learning.py collector.py feedback_queue.py app_backend_hook.py test_install.py report_sync.py; do
  install -o root -g root -m 0644 "$TMP/package/$src" "$APP/$src"
done
if [[ ! -f "$CFGDIR/config.json" ]]; then
  python3 - "$CFGDIR/config.json" "$DATA" "$QUEUE" <<'PY_CONFIG'
import json,sys,os
path,data,queue=sys.argv[1:]
config={'db_path':data+'/knowledge.sqlite3',
        'reports_directory':data+'/reports',
        'feedback_queue_directory':queue,
        'mode':'shadow','autopublish_enabled':False}
with open(path,'x',encoding='utf-8') as f:
    json.dump(config,f,indent=2);f.write('\n')
os.chmod(path,0o644)
PY_CONFIG
fi
cat > /etc/systemd/system/"$SYNC.service" <<'UNIT_SYNC'
[Unit]
Description=EpiScene Learning - read-only discovery of local report files
After=local-fs.target
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/bin/python3 /opt/episcene-learning/report_sync.py
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/episcene-learning/reports
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
UNIT_SYNC
cat > /etc/systemd/system/"$COL.service" <<'UNIT_COL'
[Unit]
Description=EpiScene Learning Engine V1 - shadow evidence collector
After=local-fs.target episcene-learning-report-sync.service
Wants=episcene-learning-report-sync.service
[Service]
Type=oneshot
User=episcene-learning
Group=episcene-learning
UMask=0077
ExecStart=/usr/bin/python3 /opt/episcene-learning/collector.py --config /etc/episcene-learning/config.json
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/episcene-learning /var/spool/episcene-learning/inbox
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
UNIT_COL
cat > /etc/systemd/system/"$COL.timer" <<'UNIT_TIMER'
[Unit]
Description=Hourly EpiScene Learning Engine V1 collection
[Timer]
OnBootSec=2min
OnUnitActiveSec=1h
Persistent=true
Unit=episcene-learning-collector.service
[Install]
WantedBy=timers.target
UNIT_TIMER
systemctl daemon-reload
systemctl enable --now "$COL.timer"
if ! systemctl start "$COL.service"; then
  echo 'Collector start failed (old EpiScene services were not touched).' >&2
  journalctl -u "$COL.service" -n 25 --no-pager >&2 || true
  exit 4
fi
if [[ -r "$DATA/last-collection.json" ]]; then
  python3 - "$DATA/last-collection.json" <<'PY_RESULT'
import json,sys
s=json.load(open(sys.argv[1]))
print('LEARNING ENGINE INSTALLED — SHADOW MODE')
print('Reports imported this run:',s.get('import',{}).get('files_imported',0))
print('New marker events:',s.get('import',{}).get('events_added',0))
print('Saved evidence:',s.get('stats',{}).get('marker_events',0))
print('Auto-publication enabled:',s.get('autopublish_enabled',False))
print('App feedback hook connected:',s.get('app_feedback_hook_connected',False))
PY_RESULT
fi
printf '\nDONE. Log: journalctl -u %s.service -n 40 --no-pager\n' "$COL"
echo 'NOTE: Existing app/manual approvals are not yet connected to the real backend.'
echo 'NOTE: If this server does not save EpiScene-*.json locally, reports must be connected separately.'
