#!/usr/bin/env bash
# Update only Pi scheduling. The existing Hetzner computation protocol is retained.
set -Eeuo pipefail
umask 0077
SOURCE_REF="${1:-}"
[[ "$SOURCE_REF" =~ ^[0-9a-f]{40}$ ]] || { echo "Unveränderlichen Git-Commit als Argument angeben." >&2; exit 1; }
[[ "$(id -u)" == 0 ]] || { echo "Bitte mit sudo ausführen." >&2; exit 1; }
BASE="${EPIMEDIAHUB_APP_DIR:-/opt/epimediahub/provisioning}"
ENV_FILE="${EPIMEDIAHUB_ENV_FILE:-/etc/epimediahub/provisioning.env}"
PY="$BASE/.venv/bin/python"
RAW="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$SOURCE_REF/server/epimediahub_provisioning"
WORK="$(mktemp -d)"
BACKUP="$BASE/backups/interactive-priority-$(date +%Y%m%d-%H%M%S)"
FILES=(skip_catalogue.py skip_schedule.py skip_analysis_worker.py skip_markers.py skip_app_capture.py templates/skip_schedule.html)
TIMER_ACTIVE=0
STOPPED=0
INSTALLED=0
systemctl is-active --quiet epimediahub-skip-analysis.timer && TIMER_ACTIVE=1 || true
cleanup() { rm -rf "$WORK"; }
resume() {
  if [[ "$TIMER_ACTIVE" == 1 ]]; then systemctl start epimediahub-skip-analysis.timer; fi
}
rollback() {
  code=$?
  trap - ERR
  if [[ "$INSTALLED" == 1 ]]; then
    for file in "${FILES[@]}"; do cp -a "$BACKUP/$file" "$BASE/$file"; done
    systemctl restart epimediahub-provisioning.service || true
  fi
  if [[ "$STOPPED" == 1 ]]; then resume || true; fi
  echo "Update abgebrochen; vorheriger Code wiederhergestellt. Kundendaten werden nicht aus einer Sicherung überschrieben." >&2
  exit "$code"
}
trap cleanup EXIT
trap rollback ERR
test -x "$PY"
test -f "$BASE/skip_remote_client.py"
test -f "$BASE/skip_schedule.py"
cd "$BASE"
install -d -m 0700 "$WORK/templates"
for file in "${FILES[@]}"; do
  test -f "$BASE/$file"
  curl -fsSL --connect-timeout 15 --max-time 60 "$RAW/$file" -o "$WORK/$file"
done
"$PY" -m py_compile "$WORK"/*.py
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
exec 9>"$DATA_DIR/skip-analysis.lock"
flock -w 30 9
# A terminated old client loses its twelve-second lease. Do not start a second decoder.
PYTHONPATH="$BASE" "$PY" - <<'PY'
import time
from skip_remote_client import configured,health
if not configured(): raise SystemExit('Bestehende Hetzner-Rolle fehlt; Update nicht aktiviert')
deadline=time.monotonic()+30
while health().get('active'):
    if time.monotonic()>=deadline: raise SystemExit('Hetzner-Auftrag noch aktiv; später erneut versuchen')
    time.sleep(1)
PY
install -d -m 0700 "$BACKUP" "$BACKUP/templates"
for file in "${FILES[@]}"; do cp -a "$BASE/$file" "$BACKUP/$file"; done
"$PY" - "$DATA_DIR/provisioning.db" "$BACKUP/provisioning.db" <<'PY'
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as source,sqlite3.connect(sys.argv[2]) as target:
    source.backup(target)
PY
INSTALLED=1
for file in "${FILES[@]}"; do install -o root -g root -m 0644 "$WORK/$file" "$BASE/$file"; done
PYTHONPATH="$BASE" "$PY" - "$DATA_DIR/provisioning.db" <<'PY'
import sys
from skip_database import connect
from skip_markers import migrate,now
from skip_schedule import language_stage
with connect(sys.argv[1]) as con:
    migrate(con)
    con.execute("UPDATE skip_jobs SET status='queued',detail='Für neue Sprach- und Serienpriorität pausiert',updated_at=? WHERE status='running'",(now(),))
    print('Aktive Sprachgruppe:',('Deutsch / Italienisch','Türkisch','Übrige Sprachen')[language_stage(con)])
PY
systemctl restart epimediahub-provisioning.service
curl -fsS --retry 5 --retry-delay 1 --retry-connrefused http://127.0.0.1:8787/health -o "$WORK/health.json"
"$PY" - "$WORK/health.json" <<'PY'
import json,sys
with open(sys.argv[1]) as source: value=json.load(source)
assert value.get('status')=='ok' and value.get('features',{}).get('skip_interactive_priority')
PY
flock -u 9
exec 9>&-
resume
if [[ "$TIMER_ACTIVE" == 1 ]]; then systemctl start --no-block epimediahub-skip-analysis.service; fi
echo "Priorität aktiv: Deutsch/Italienisch → Türkisch → übrige Sprachen."
echo "Neue Referenzen zuerst lernen; gestartete Serien gezielt und Folgen nacheinander abarbeiten."
echo "Wiedergabeschutz, vorhandene Audiofenster und das konfigurierte Tageslimit bleiben erhalten."
echo "Sicherung: $BACKUP"
