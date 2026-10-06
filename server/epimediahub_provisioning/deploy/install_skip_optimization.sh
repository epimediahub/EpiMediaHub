#!/usr/bin/env bash
# Paired update: prepare on Pi, compute on Hetzner, control on Pi.
set -Eeuo pipefail
umask 0077
MODE="${1:-}"
SOURCE_REF="${2:-}"
[[ "$MODE" =~ ^(prepare|compute|control)$ && "$SOURCE_REF" =~ ^[a-f0-9]{40}$ ]] || { echo 'Aufruf: sudo bash install_skip_optimization.sh prepare|compute|control COMMIT'; exit 1; }
[[ "$(id -u)" == 0 ]] || { echo 'Bitte mit sudo ausführen.'; exit 1; }
if [[ "$MODE" == compute ]]; then
  BASE="${EPIMEDIAHUB_WORKER_DIR:-/opt/epimediahub/analysis}"
  FILES=(skip_analysis.py skip_automation.py skip_markers.py skip_detector_v2.py skip_detector_v3.py skip_remote_client.py skip_remote_protocol.py skip_remote_worker.py)
  test ! -f "$BASE/skip_remote_role.json"
else
  BASE="${EPIMEDIAHUB_APP_DIR:-/opt/epimediahub/provisioning}"
  FILES=(skip_analysis.py skip_automation.py skip_markers.py skip_detector_v2.py skip_detector_v3.py skip_remote_client.py skip_remote_protocol.py skip_database.py skip_progress.py skip_progress_worker.py skip_release.py templates/skip_markers.html templates/skip_progress.html static/skip_dashboard.js deploy/epimediahub-skip-progress.service deploy/epimediahub-skip-progress.timer deploy/check_skip_latency.py)
  test -f "$BASE/skip_remote_role.json"
fi
PY="$BASE/.venv/bin/python"
test -x "$PY"
ENV_FILE="${EPIMEDIAHUB_ENV_FILE:-/etc/epimediahub/provisioning.env}"
UNIT_ROOT="${EPIMEDIAHUB_SYSTEMD_DIR:-/etc/systemd/system}"
TIMING_DROPIN="$UNIT_ROOT/epimediahub-skip-analysis.service.d/optimization.conf"
RAW="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$SOURCE_REF/server/epimediahub_provisioning"
STAGE="$BASE/optimization-stage-$SOURCE_REF"
WORK="$(mktemp -d)"
BACKUP="$BASE/backups/optimization-$(date +%Y%m%d-%H%M%S)"
INSTALLED=0
STOPPED=0
TIMER_ACTIVE=0
PROGRESS_ACTIVE=0
cleanup() { rm -rf "$WORK"; }
restore_files() {
  for file in "${FILES[@]}"; do
    if [[ -f "$BACKUP/$file" ]]; then cp -a "$BACKUP/$file" "$BASE/$file"; else rm -f "$BASE/$file"; fi
  done
}
rollback() {
  code=$?
  trap - ERR
  if [[ "$INSTALLED" == 1 ]]; then
    restore_files
    if [[ "$MODE" == compute ]]; then
      systemctl restart epimediahub-analysis-worker.service || true
    else
      systemctl stop epimediahub-skip-progress.timer || true
      for name in epimediahub-skip-progress.service epimediahub-skip-progress.timer; do
        if [[ -f "$BACKUP/units/$name" ]]; then cp -a "$BACKUP/units/$name" "$UNIT_ROOT/$name"; else rm -f "$UNIT_ROOT/$name"; fi
      done
      if [[ -f "$BACKUP/units/analysis-timing.conf" ]]; then cp -a "$BACKUP/units/analysis-timing.conf" "$TIMING_DROPIN"; else rm -f "$TIMING_DROPIN"; fi
      systemctl daemon-reload
      systemctl restart epimediahub-provisioning.service || true
      [[ "$PROGRESS_ACTIVE" != 1 ]] || systemctl start epimediahub-skip-progress.timer || true
    fi
  fi
  if [[ "$MODE" == prepare && "$STOPPED" == 1 && "$TIMER_ACTIVE" == 1 ]]; then
    systemctl start epimediahub-skip-analysis.timer || true
  fi
  echo 'Update abgebrochen. Vorheriger Code wiederhergestellt; die aktive Kundendatenbank wird nicht überschrieben.' >&2
  if [[ "$MODE" == control ]]; then echo 'Die Audioanalyse bleibt bis zur passenden Version auf beiden Geräten pausiert. Die Vorbereitung bleibt erhalten.' >&2; fi
  exit "$code"
}
trap cleanup EXIT
trap rollback ERR

if [[ "$MODE" != control ]]; then
  install -d -m 0700 "$WORK/templates" "$WORK/static" "$WORK/deploy"
  for file in "${FILES[@]}"; do curl -fsSL --connect-timeout 15 --max-time 60 "$RAW/$file" -o "$WORK/$file"; done
  "$PY" -m py_compile "$WORK"/*.py
  [[ ! -f "$WORK/deploy/check_skip_latency.py" ]] || "$PY" -m py_compile "$WORK/deploy/check_skip_latency.py"
  "$PY" "$WORK/skip_detector_v3.py" --selftest > "$WORK/selftest.log"
  PYTHONPATH="$WORK:$BASE" "$PY" -P - "$WORK" <<'PY'
import hashlib,json,sys
from pathlib import Path
from skip_remote_protocol import versions
root=Path(sys.argv[1])
manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*')
          if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.html','.js','.service','.timer')}
(root/'manifest.json').write_text(json.dumps(dict(files=manifest,versions=versions())))
PY
fi

if [[ "$MODE" == prepare ]]; then
  if [[ -f "$STAGE/state.json" ]]; then
    echo 'Diese Version ist bereits vorbereitet; gespeicherter Timerzustand bleibt erhalten.'
    exit 0
  fi
  systemctl is-active --quiet epimediahub-skip-analysis.timer && TIMER_ACTIVE=1 || true
  systemctl is-active --quiet epimediahub-skip-progress.timer && PROGRESS_ACTIVE=1 || true
  systemctl stop epimediahub-skip-analysis.timer
  STOPPED=1
  systemctl stop epimediahub-skip-analysis.service
  # Old operations lose their renewed lease after the Pi client stops.
  PYTHONPATH="$BASE" "$PY" -P - <<'PY'
import time
from skip_remote_client import configured,health
assert configured(), 'Bestehende Hetzner-Verbindung fehlt'
deadline=time.monotonic()+30
while health().get('active'):
    if time.monotonic()>=deadline: raise SystemExit('Remote-Auftrag gibt die Sperre nicht frei')
    time.sleep(1)
PY
  install -d -m 0700 "$STAGE/templates" "$STAGE/static" "$STAGE/deploy"
  for file in "${FILES[@]}"; do install -m 0644 "$WORK/$file" "$STAGE/$file"; done
  cp "$WORK/manifest.json" "$STAGE/manifest.json"
  cp "$BASE/skip_remote_role.json" "$STAGE/skip_remote_role.json"
  "$PY" - "$STAGE/state.json" "$SOURCE_REF" "$TIMER_ACTIVE" "$PROGRESS_ACTIVE" <<'PY'
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps(dict(commit=sys.argv[2],timer_active=int(sys.argv[3]),progress_active=int(sys.argv[4]))))
PY
  echo 'Raspberry vorbereitet; Webdashboard läuft weiter. Analyse ist für das passende Hetzner-Update pausiert.'
  echo "Jetzt auf Hetzner: sudo bash /tmp/epimediahub-optimization.sh compute $SOURCE_REF"
  exit 0
fi

if [[ "$MODE" == control ]]; then
  test -f "$STAGE/state.json"
  "$PY" - "$STAGE" "$SOURCE_REF" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1])
assert json.loads((root/'state.json').read_text())['commit']==sys.argv[2]
for name,digest in json.loads((root/'manifest.json').read_text())['files'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest, 'Vorbereitete Datei verändert'
PY
  read -r TIMER_ACTIVE PROGRESS_ACTIVE < <("$PY" - "$STAGE/state.json" <<'PY'
import json,sys
value=json.load(open(sys.argv[1]))
assert value['timer_active'] in (0,1) and value['progress_active'] in (0,1)
print(value['timer_active'],value['progress_active'])
PY
)
  # Verify the real peer and math before changing any installed Pi module.
  PYTHONPATH="$STAGE:$BASE" "$PY" -P - <<'PY'
import random
from skip_remote_client import health,match
health()
rng=random.Random(1062026)
reference=[rng.getrandbits(32) for _ in range(80)]
assert match(reference,[rng.getrandbits(32) for _ in range(20)]+reference+[rng.getrandbits(32) for _ in range(20)],125)==(2500,1.0)
PY
  systemctl stop epimediahub-skip-analysis.timer
  systemctl stop epimediahub-skip-analysis.service
  DATA_DIR="$("$PY" - "$ENV_FILE" <<'PY'
import os,shlex,sys
from pathlib import Path
value=os.environ.get('EPIMEDIAHUB_DATA_DIR','/var/lib/epimediahub')
for line in Path(sys.argv[1]).read_text().splitlines():
    key,sep,text=line.partition('=')
    if sep and key.strip()=='EPIMEDIAHUB_DATA_DIR':
        parts=shlex.split(text,comments=True)
        assert len(parts)==1
        value=parts[0]
assert Path(value).is_absolute()
print(value)
PY
)"
  exec 9>"$DATA_DIR/skip-analysis.lock"
  flock -w 30 9
  systemctl stop epimediahub-skip-progress.timer || true
  systemctl stop epimediahub-skip-progress.service || true
  install -d -m 0700 "$BACKUP/units"
  for name in epimediahub-skip-progress.service epimediahub-skip-progress.timer; do
    [[ ! -f "$UNIT_ROOT/$name" ]] || cp -a "$UNIT_ROOT/$name" "$BACKUP/units/$name"
  done
  [[ ! -f "$TIMING_DROPIN" ]] || cp -a "$TIMING_DROPIN" "$BACKUP/units/analysis-timing.conf"
  "$PY" - "$DATA_DIR/provisioning.db" "$BACKUP/provisioning.db" <<'PY'
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as source,sqlite3.connect(sys.argv[2]) as target: source.backup(target)
PY
  WORK_SOURCE="$STAGE"
else
  WORK_SOURCE="$WORK"
  install -d -m 0700 "$BACKUP"
fi

for file in "${FILES[@]}"; do
  install -d -m 0700 "$BACKUP/$(dirname "$file")"
  [[ ! -f "$BASE/$file" ]] || cp -a "$BASE/$file" "$BACKUP/$file"
done
if [[ "$MODE" == compute ]]; then systemctl stop epimediahub-analysis-worker.service; fi
INSTALLED=1
for file in "${FILES[@]}"; do
  install -d -m 0755 "$BASE/$(dirname "$file")"
  install -o root -g root -m 0644 "$WORK_SOURCE/$file" "$BASE/$file"
done

if [[ "$MODE" == compute ]]; then
  systemctl restart epimediahub-analysis-worker.service
  curl -fsS --retry 5 --retry-delay 1 --retry-connrefused http://10.87.26.1:8790/health -o "$WORK/health.json"
  PYTHONPATH="$BASE" "$PY" -P - "$WORK/health.json" <<'PY'
import json,sys
from skip_remote_protocol import versions
value=json.load(open(sys.argv[1]))
assert value.get('status')=='ok' and value.get('versions')==versions()
assert isinstance(value.get('detection_cache'),dict)
PY
  echo 'Hetzner aktualisiert: exakter schneller Vergleich, begrenzter Vergleichscache und präzisere Freigaben.'
  echo "Jetzt auf dem Raspberry: sudo bash /tmp/epimediahub-optimization.sh control $SOURCE_REF"
else
  PYTHONPATH="$BASE" "$PY" -P - "$DATA_DIR/provisioning.db" <<'PY'
import sys
from skip_database import connect
from skip_markers import migrate,now
from skip_progress import refresh
with connect(sys.argv[1]) as con:
    migrate(con)
    con.execute("UPDATE skip_jobs SET status='queued',detail='Nach Optimierung fortsetzen',updated_at=? WHERE status='running'",(now(),))
with connect(sys.argv[1]) as con: refresh(con,limit=128,budget=1)
PY
  "$PY" - "$BASE" "$ENV_FILE" "$UNIT_ROOT" <<'PY'
import sys
from pathlib import Path
base,env,units=map(Path,sys.argv[1:])
for name in ('epimediahub-skip-progress.service','epimediahub-skip-progress.timer'):
    text=(base/'deploy'/name).read_text().replace('/opt/epimediahub/provisioning',str(base)).replace('/etc/epimediahub/provisioning.env',str(env))
    (units/name).write_text(text)
    (units/name).chmod(0o644)
PY
  install -d -m 0755 "$(dirname "$TIMING_DROPIN")"
  printf '[Service]\nEnvironment=SKIP_ANALYSIS_TIMING=1\n' > "$TIMING_DROPIN"
  chmod 0644 "$TIMING_DROPIN"
  systemctl daemon-reload
  systemctl restart epimediahub-provisioning.service
  curl -fsS --retry 5 --retry-delay 1 --retry-connrefused http://127.0.0.1:8787/health -o "$WORK/health.json"
  "$PY" - "$WORK/health.json" <<'PY'
import json,sys
value=json.load(open(sys.argv[1]))
assert value.get('status')=='ok' and all(value.get('features',{}).get(k) for k in ('skip_dashboard_async','skip_progress_readonly','skip_detection_precision','skip_language_stages'))
PY
  PYTHONPATH="$BASE" "$PY" -P -c 'from skip_remote_client import health; health()'
  "$PY" "$BASE/deploy/check_skip_latency.py" "$DATA_DIR/provisioning.db"
  systemctl enable --now epimediahub-skip-progress.timer
  systemctl start --no-block epimediahub-skip-progress.service
  flock -u 9
  exec 9>&-
  if [[ "$TIMER_ACTIVE" == 1 ]]; then
    systemctl start epimediahub-skip-analysis.timer
    systemctl start --no-block epimediahub-skip-analysis.service
  fi
  echo 'Dashboard und Analyse optimiert. Deutsch/Italienisch → Türkisch → übrige Sprachen bleibt aktiv.'
  rm -f "$STAGE/state.json"
fi
echo "Sicherung: $BACKUP"
