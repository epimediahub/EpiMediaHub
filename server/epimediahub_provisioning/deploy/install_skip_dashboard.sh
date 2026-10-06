#!/usr/bin/env bash
# Update only dashboard reads and snapshots; retain the paired Hetzner protocol.
set -Eeuo pipefail
umask 0077
SOURCE_REF="${1:-}"
[[ "$SOURCE_REF" =~ ^[0-9a-f]{40}$ ]] || { echo "Unveränderlichen Git-Commit als Argument angeben." >&2; exit 1; }
[[ "$(id -u)" == 0 ]] || { echo "Bitte mit sudo ausführen." >&2; exit 1; }
BASE="${EPIMEDIAHUB_APP_DIR:-/opt/epimediahub/provisioning}"
UNIT_ROOT="${EPIMEDIAHUB_SYSTEMD_DIR:-/etc/systemd/system}"
PROGRESS_UNIT="$UNIT_ROOT/epimediahub-skip-progress.service"
ENV_FILE="${EPIMEDIAHUB_ENV_FILE:-/etc/epimediahub/provisioning.env}"
PY="$BASE/.venv/bin/python"
RAW="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$SOURCE_REF/server/epimediahub_provisioning"
WORK="$(mktemp -d)"
BACKUP="$BASE/backups/dashboard-read-$(date +%Y%m%d-%H%M%S)"
FILES=(skip_catalogue.py skip_schedule.py skip_markers.py skip_dashboard_stats.py skip_progress_worker.py templates/skip_schedule.html templates/skip_markers.html deploy/check_skip_latency.py deploy/epimediahub-skip-progress.service)
PROGRESS_ACTIVE=0
TIMER_ACTIVE=0
STOPPED=0
INSTALLED=0
systemctl is-active --quiet epimediahub-skip-analysis.timer && TIMER_ACTIVE=1 || true
systemctl is-active --quiet epimediahub-skip-progress.timer && PROGRESS_ACTIVE=1 || true
cleanup() { rm -rf "$WORK"; }
resume() {
  if [[ "$TIMER_ACTIVE" == 1 ]]; then systemctl start epimediahub-skip-analysis.timer; fi
}
rollback() {
  code=$?
  trap - ERR
  if [[ "$INSTALLED" == 1 ]]; then
    for file in "${FILES[@]}"; do
      if [[ -f "$BACKUP/$file" ]]; then cp -a "$BACKUP/$file" "$BASE/$file"; else rm -f "$BASE/$file"; fi
    done
    cp -a "$BACKUP/progress.service" "$PROGRESS_UNIT"
    systemctl daemon-reload
    systemctl restart epimediahub-provisioning.service || true
  fi
  if [[ "$STOPPED" == 1 ]]; then
    resume || true
    [[ "$PROGRESS_ACTIVE" != 1 ]] || systemctl start epimediahub-skip-progress.timer || true
  fi
  echo "Update abgebrochen; vorheriger Code wiederhergestellt. Kundendaten werden nicht aus einer Sicherung überschrieben." >&2
  exit "$code"
}
trap cleanup EXIT
trap rollback ERR
test -x "$PY"
test -f "$BASE/skip_remote_client.py"
test -f "$BASE/skip_schedule.py"
test -f "$BASE/skip_progress_worker.py"
test -f "$PROGRESS_UNIT"
cd "$BASE"
install -d -m 0700 "$WORK/templates" "$WORK/deploy"
for file in "${FILES[@]}"; do
  curl -fsSL --connect-timeout 15 --max-time 60 "$RAW/$file" -o "$WORK/$file"
done
"$PY" -m py_compile "$WORK"/*.py "$WORK/deploy/check_skip_latency.py"
DATA_DIR="$("$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
import os,shlex,sys
value=os.environ.get('EPIMEDIAHUB_DATA_DIR','/var/lib/epimediahub')
if Path(sys.argv[1]).exists():
    for line in Path(sys.argv[1]).read_text().splitlines():
        key,sep,text=line.partition('=')
        if sep and key.strip()=='EPIMEDIAHUB_DATA_DIR':
            parts=shlex.split(text,comments=True)
            if len(parts)!=1: raise SystemExit('Ungültiges Datenverzeichnis')
            value=parts[0]
if not Path(value).is_absolute(): raise SystemExit('Absolutes Datenverzeichnis erforderlich')
print(value)
PY
)"
test -f "$DATA_DIR/provisioning.db"
echo "Auftragssteuerung kurz anhalten; laufende Remote-Analyse pausieren …"
systemctl stop epimediahub-skip-analysis.timer
STOPPED=1
systemctl stop epimediahub-skip-analysis.service
systemctl stop epimediahub-skip-progress.timer
systemctl stop epimediahub-skip-progress.service
exec 9>"$DATA_DIR/skip-analysis.lock"
flock -w 30 9
# A terminated old client loses its twelve-second lease. Do not start a second decoder.
PYTHONPATH="$BASE" "$PY" -P - <<'PY'
import time
from skip_remote_client import configured,health
if not configured(): raise SystemExit('Bestehende Hetzner-Rolle fehlt; Update nicht aktiviert')
deadline=time.monotonic()+30
while health().get('active'):
    if time.monotonic()>=deadline: raise SystemExit('Hetzner-Auftrag noch aktiv; später erneut versuchen')
    time.sleep(1)
PY
install -d -m 0700 "$BACKUP" "$BACKUP/templates" "$BACKUP/deploy"
cp -a "$PROGRESS_UNIT" "$BACKUP/progress.service"
for file in "${FILES[@]}"; do [[ ! -f "$BASE/$file" ]] || cp -a "$BASE/$file" "$BACKUP/$file"; done
"$PY" - "$DATA_DIR/provisioning.db" "$BACKUP/provisioning.db" <<'PY'
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as source,sqlite3.connect(sys.argv[2]) as target:
    source.backup(target)
PY
INSTALLED=1
for file in "${FILES[@]}"; do install -o root -g root -m 0644 "$WORK/$file" "$BASE/$file"; done
PYTHONPATH="$BASE" "$PY" -P - "$DATA_DIR/provisioning.db" <<'PY'
import sys
from skip_database import connect
from skip_markers import migrate,now
from skip_dashboard_stats import refresh
with connect(sys.argv[1]) as con:
    migrate(con)
    con.execute("UPDATE skip_jobs SET status='queued',detail='Nach Dashboard-Update fortsetzen',updated_at=? WHERE status='running'",(now(),))
with connect(sys.argv[1]) as con:
    refresh(con,force=True)
PY
"$PY" - "$PROGRESS_UNIT" <<'PY'
from pathlib import Path
import re,sys
p=Path(sys.argv[1]);text=p.read_text()
if re.search(r'^TimeoutStartSec=.*$',text,re.M):text=re.sub(r'^TimeoutStartSec=.*$','TimeoutStartSec=120',text,flags=re.M)
else:
    assert '[Service]' in text
    text=text.replace('[Service]','[Service]\nTimeoutStartSec=120',1)
p.write_text(text)
PY
systemctl daemon-reload
systemctl restart epimediahub-provisioning.service
curl -fsS --retry 5 --retry-delay 1 --retry-connrefused http://127.0.0.1:8787/health -o "$WORK/health.json"
"$PY" - "$WORK/health.json" <<'PY'
import json,sys
with open(sys.argv[1]) as source: value=json.load(source)
assert value.get('status')=='ok' and value.get('features',{}).get('skip_dashboard_cached_statistics')
PY
"$PY" "$BASE/deploy/check_skip_latency.py" "$DATA_DIR/provisioning.db"
flock -u 9
exec 9>&-
[[ "$PROGRESS_ACTIVE" != 1 ]] || systemctl start epimediahub-skip-progress.timer
systemctl start --no-block epimediahub-skip-progress.service
resume
if [[ "$TIMER_ACTIVE" == 1 ]]; then systemctl start --no-block epimediahub-skip-analysis.service; fi
echo "Dashboard aktualisiert: Katalogstatistik und Queueplanung laufen außerhalb des Seitenaufrufs."
echo "Hetzner bleibt verbunden; Sprachprioritäten und Tagesbudget bleiben erhalten."
echo "Wiedergabeschutz, vorhandene Audiofenster und das konfigurierte Tageslimit bleiben erhalten."
echo "Sicherung: $BACKUP"
