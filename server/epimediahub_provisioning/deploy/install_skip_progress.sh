#!/usr/bin/env bash
# Update the installed V3.1 worker without replacing the credit/license backend.
set -euo pipefail
umask 0077
BASE="${EPIMEDIAHUB_APP_DIR:-/opt/epimediahub/provisioning}"
ENV_FILE="${EPIMEDIAHUB_ENV_FILE:-/etc/epimediahub/provisioning.env}"
UNIT_ROOT="${EPIMEDIAHUB_SYSTEMD_DIR:-/etc/systemd/system}"
PY="$BASE/.venv/bin/python"
SOURCE_REF="raspberry-v0.8.2-skip-progress"
RAW="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$SOURCE_REF/server/epimediahub_provisioning"
TASK="$(mktemp -d /tmp/epimediahub-skip-progress.XXXXXX)"
BACKUP="$BASE/backups/skip-progress-$(date +%Y%m%d-%H%M%S)"
FILES=(skip_analysis_worker.py skip_automation.py skip_markers.py skip_release.py skip_detector_v3.py)
SERVICE_DROPIN="$UNIT_ROOT/epimediahub-skip-analysis.service.d/progress.conf"
TIMER_DROPIN="$UNIT_ROOT/epimediahub-skip-analysis.timer.d/progress.conf"
INSTALLED=0
TIMER_ACTIVE=0
TIMER_STOPPED=0
systemctl is-active --quiet epimediahub-skip-analysis.timer && TIMER_ACTIVE=1 || true

cleanup() { rm -rf "$TASK"; }
rollback() {
  code=$?
  if [ "$INSTALLED" = 1 ]; then
    for file in "${FILES[@]}"; do
      if [ -f "$BACKUP/$file" ]; then cp -a "$BACKUP/$file" "$BASE/$file"; else rm -f "$BASE/$file"; fi
    done
    for pair in "service:$SERVICE_DROPIN" "timer:$TIMER_DROPIN"; do
      name="${pair%%:*}"; target="${pair#*:}"
      if [ -f "$BACKUP/$name.conf" ]; then cp -a "$BACKUP/$name.conf" "$target"; else rm -f "$target"; fi
    done
    systemctl daemon-reload
    systemctl restart epimediahub-provisioning.service || true
    echo "Update fehlgeschlagen; vorherigen Code und Timerkonfiguration wiederhergestellt." >&2
  fi
  if [ "$TIMER_STOPPED" = 1 ] && [ "$TIMER_ACTIVE" = 1 ]; then systemctl start epimediahub-skip-analysis.timer || true; fi
  cleanup
  exit "$code"
}
trap rollback ERR
trap cleanup EXIT
if [ "$(id -u)" != 0 ]; then echo "Bitte mit sudo ausführen." >&2; exit 1; fi
test -x "$PY"
test -f "$BASE/skip_catalogue.py"
test -f "$ENV_FILE"

echo "Aktualisierten Worker und V3.1-Modul laden und prüfen …"
for file in "${FILES[@]}"; do curl -fsSL --connect-timeout 15 --max-time 90 "$RAW/$file" -o "$TASK/$file"; done
"$PY" -c 'import numpy'
"$PY" -m py_compile "${FILES[@]/#/$TASK/}"
"$PY" "$TASK/skip_detector_v3.py" --selftest
PYTHONPATH="$TASK:$BASE" "$PY" - <<'PY'
import skip_automation
from skip_analysis_worker import process_batch
assert skip_automation.DETECTOR_POLICY == 'chromaprint_fft_v3_1'
assert callable(process_batch)
PY

DATA_DIR="$("$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
import shlex, sys
value = '/var/lib/epimediahub'
for line in Path(sys.argv[1]).read_text().splitlines():
    key, sep, text = line.partition('=')
    if sep and key.strip() == 'EPIMEDIAHUB_DATA_DIR':
        parsed = shlex.split(text, comments=True)
        if len(parsed) != 1 or not Path(parsed[0]).is_absolute():
            raise SystemExit('Ungültiges Datenverzeichnis')
        value = parsed[0]
print(value)
PY
)"
test -f "$DATA_DIR/provisioning.db"
echo "Laufenden Auftrag auslaufen lassen und Backup erstellen …"
systemctl stop epimediahub-skip-analysis.timer
TIMER_STOPPED=1
exec 9>"$DATA_DIR/skip-analysis.lock"
if ! flock -w 900 9; then
  echo "Der laufende Analyseauftrag hat die Updatesperre nicht freigegeben. Code unverändert." >&2
  if [ "$TIMER_ACTIVE" = 1 ]; then systemctl start epimediahub-skip-analysis.timer; fi
  exit 1
fi
mkdir -p "$BACKUP"
for file in "${FILES[@]}"; do [ ! -f "$BASE/$file" ] || cp -a "$BASE/$file" "$BACKUP/$file"; done
for pair in "service:$SERVICE_DROPIN" "timer:$TIMER_DROPIN"; do
  name="${pair%%:*}"; target="${pair#*:}"
  [ ! -f "$target" ] || cp -a "$target" "$BACKUP/$name.conf"
done
"$PY" - "$DATA_DIR/provisioning.db" "$BACKUP/provisioning.db" <<'PY'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as source, sqlite3.connect(sys.argv[2]) as target:
    source.backup(target)
PY
INSTALLED=1
for file in "${FILES[@]}"; do install -o root -g root -m 0644 "$TASK/$file" "$BASE/$file"; done
mkdir -p "$(dirname "$SERVICE_DROPIN")" "$(dirname "$TIMER_DROPIN")"
cat > "$SERVICE_DROPIN" <<EOF
[Service]
ExecStart=
ExecStart=$PY skip_analysis_worker.py --batch --max-jobs 4 --max-seconds 600
EOF
cat > "$TIMER_DROPIN" <<'EOF'
[Timer]
OnUnitInactiveSec=30s
EOF
chmod 0644 "$SERVICE_DROPIN" "$TIMER_DROPIN"

echo "Neue, additive Sitzungstabelle vorbereiten und Server prüfen …"
(cd "$BASE" && "$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
import os, re, shlex, sys
for line in Path(sys.argv[1]).read_text().splitlines():
    key, sep, text = line.partition('=')
    key = key.strip()
    if not sep or not re.fullmatch(r'[A-Z_][A-Z0-9_]*', key):
        continue
    parsed = shlex.split(text, comments=True)
    if len(parsed) == 1:
        os.environ[key] = parsed[0]
from app import db
from wsgi import app
with db() as con:
    assert con.execute("SELECT 1 FROM sqlite_master WHERE name='skip_presence_sessions'").fetchone()
print('Sitzungstabelle vorhanden; Marker und Tageslimit bleiben erhalten')
PY
)
systemctl daemon-reload
systemctl restart epimediahub-provisioning.service
curl -fsS --retry 5 --retry-delay 2 --retry-connrefused http://127.0.0.1:8787/health -o "$TASK/health.json"
"$PY" - "$TASK/health.json" <<'PY'
import json, sys
with open(sys.argv[1]) as source:
    assert json.load(source).get('status') == 'ok'
print('Server gesund')
PY
flock -u 9
exec 9>&-
systemctl start epimediahub-skip-analysis.timer
systemctl start --no-block epimediahub-skip-analysis.service
echo "Update installiert: bis zu vier aufeinanderfolgende Jobs, kürzere Timerpause, vollständige Audiofenster aus dem Cache."
echo "Die App 1.0.25 gibt das Providerkonto beim Verlassen des Players sofort frei."
echo "Deutsch und Italienisch behalten Vorrang; vorhandene CPU-/RAM-Limits bleiben wirksam."
echo "Backup: $BACKUP"
