#!/usr/bin/env bash
# EpiScene paired update: Pi prepare, Hetzner compute, Pi control.
set -Eeuo pipefail
umask 0077
MODE="${1:-}"
SOURCE_REF="${2:-}"
[[ "$MODE" =~ ^(prepare|compute|control)$ && "$SOURCE_REF" =~ ^[a-f0-9]{40}$ ]] || { echo 'Aufruf: sudo bash install_skip_scene.sh prepare|compute|control COMMIT'; exit 1; }
[[ "$(id -u)" == 0 ]] || { echo 'Bitte mit sudo ausführen.'; exit 1; }
if [[ "$MODE" == compute ]]; then
  BASE="${EPIMEDIAHUB_WORKER_DIR:-/opt/epimediahub/analysis}"
  FILES=(skip_analysis.py skip_automation.py skip_markers.py skip_detector_v2.py skip_detector_v3.py skip_remote_client.py skip_remote_protocol.py skip_remote_worker.py skip_visual.py skip_scene.py skip_release.py)
  test ! -f "$BASE/skip_remote_role.json"
else
  BASE="${EPIMEDIAHUB_APP_DIR:-/opt/epimediahub/provisioning}"
  FILES=(skip_analysis.py skip_automation.py skip_analysis_worker.py skip_markers.py skip_detector_v2.py skip_detector_v3.py skip_remote_client.py skip_remote_protocol.py skip_visual.py skip_scene.py skip_release.py templates/skip_markers.html)
  test -f "$BASE/skip_remote_role.json"
  test -f "$BASE/skip_dashboard_stats.py"
fi
PY="$BASE/.venv/bin/python"
test -x "$PY"
ENV_FILE="${EPIMEDIAHUB_ENV_FILE:-/etc/epimediahub/provisioning.env}"
RAW="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$SOURCE_REF/server/epimediahub_provisioning"
STAGE="$BASE/episcene-stage-$SOURCE_REF"
WORK="$(mktemp -d)"
BACKUP="$BASE/backups/episcene-$(date +%Y%m%d-%H%M%S)"
INSTALLED=0
STOPPED=0
TIMER_ACTIVE=0
PROGRESS_ACTIVE=0
DATA_DIR=''
cleanup() { rm -rf "$WORK"; }
rollback() {
  code=$?
  trap - ERR
  if [[ "$INSTALLED" == 1 ]]; then
    for file in "${FILES[@]}"; do
      if [[ -f "$BACKUP/$file" ]]; then cp -a "$BACKUP/$file" "$BASE/$file"; else rm -f "$BASE/$file"; fi
    done
    if [[ "$MODE" == compute ]]; then
      systemctl restart epimediahub-analysis-worker.service || true
    else
      # Restore only the feature switch, never overwrite the live database.
      if [[ -f "$BACKUP/episcene-setting.json" ]]; then
        "$PY" - "$DATA_DIR/provisioning.db" "$BACKUP/episcene-setting.json" "$BACKUP" <<'PY' || true
import json,sqlite3,sys
from pathlib import Path
value=json.load(open(sys.argv[2]))
with sqlite3.connect(sys.argv[1]) as con:
    if value is None: con.execute("DELETE FROM skip_auto_metadata_config WHERE name='episcene_enabled'")
    else: con.execute("INSERT OR REPLACE INTO skip_auto_metadata_config VALUES('episcene_enabled',?,?)",value)
    stamp=Path(sys.argv[3])/'activation-time.json'
    if stamp.exists():
        # Restore retries introduced by this installer, while retaining any
        # concurrent customer/reference change with a different timestamp.
        con.execute('ATTACH DATABASE ? AS previous',(str(Path(sys.argv[3])/'provisioning.db'),))
        con.execute('''UPDATE skip_jobs SET status=(SELECT status FROM previous.skip_jobs p WHERE p.id=skip_jobs.id),
          attempts=(SELECT attempts FROM previous.skip_jobs p WHERE p.id=skip_jobs.id),
          detail=(SELECT detail FROM previous.skip_jobs p WHERE p.id=skip_jobs.id),
          updated_at=(SELECT updated_at FROM previous.skip_jobs p WHERE p.id=skip_jobs.id)
          WHERE updated_at=? AND detail='EpiScene: Bildvergleich für bisher fehlende Intros'
          AND EXISTS(SELECT 1 FROM previous.skip_jobs p WHERE p.id=skip_jobs.id)''',
          (json.loads(stamp.read_text()),))
PY
      fi
      systemctl restart epimediahub-provisioning.service || true
      [[ "$PROGRESS_ACTIVE" != 1 ]] || systemctl start epimediahub-skip-progress.timer || true
    fi
  fi
  if [[ "$MODE" == prepare && "$STOPPED" == 1 && "$TIMER_ACTIVE" == 1 ]]; then
    systemctl start epimediahub-skip-analysis.timer || true
  fi
  echo 'EpiScene-Update abgebrochen; vorheriger Code wiederhergestellt. Kundendaten und Markierungen bleiben erhalten.' >&2
  if [[ "$MODE" == control ]]; then echo 'Die Analyse bleibt bis zu passenden Versionen auf beiden Geräten pausiert; Vorbereitung bleibt erhalten.' >&2; fi
  exit "$code"
}
trap cleanup EXIT
trap rollback ERR

if [[ "$MODE" != control ]]; then
  install -d -m 0700 "$WORK/templates"
  for file in "${FILES[@]}"; do curl -fsSL --connect-timeout 15 --max-time 60 "$RAW/$file" -o "$WORK/$file"; done
  "$PY" -m py_compile "$WORK"/*.py
  PYTHONPATH="$WORK:$BASE" "$PY" -P - "$WORK" <<'PY'
import hashlib,json,sys
from pathlib import Path
from skip_remote_protocol import versions
from skip_visual import VisualWindow,detect
root=Path(sys.argv[1])
manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*')
          if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.html')}
(root/'manifest.json').write_text(json.dumps(dict(files=manifest,versions=versions())))
PY
fi

if [[ "$MODE" == prepare ]]; then
  if [[ -f "$STAGE/state.json" ]]; then
    echo 'EpiScene bereits vorbereitet; gespeicherter Timerzustand bleibt erhalten.'
    exit 0
  fi
  systemctl is-active --quiet epimediahub-skip-analysis.timer && TIMER_ACTIVE=1 || true
  systemctl is-active --quiet epimediahub-skip-progress.timer && PROGRESS_ACTIVE=1 || true
  systemctl stop epimediahub-skip-analysis.timer
  STOPPED=1
  systemctl stop epimediahub-skip-analysis.service
  PYTHONPATH="$BASE" "$PY" -P - <<'PY'
import time
from skip_remote_client import configured,health
assert configured(), 'Bestehende Hetzner-Verbindung fehlt'
deadline=time.monotonic()+30
while health().get('active'):
    if time.monotonic()>=deadline: raise SystemExit('Hetzner-Auftrag gibt die Sperre nicht frei')
    time.sleep(1)
PY
  install -d -m 0700 "$STAGE/templates"
  for file in "${FILES[@]}"; do install -m 0644 "$WORK/$file" "$STAGE/$file"; done
  cp "$WORK/manifest.json" "$STAGE/manifest.json"
  cp "$BASE/skip_remote_role.json" "$STAGE/skip_remote_role.json"
  "$PY" - "$STAGE/state.json" "$SOURCE_REF" "$TIMER_ACTIVE" "$PROGRESS_ACTIVE" <<'PY'
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps(dict(commit=sys.argv[2],timer_active=int(sys.argv[3]),progress_active=int(sys.argv[4]))))
PY
  echo 'EpiScene vorbereitet. Dashboard läuft weiter; Analyse wartet auf das passende Hetzner-Update.'
  echo "Jetzt auf Hetzner: sudo bash /tmp/epimediahub-episcene.sh compute $SOURCE_REF"
  exit 0
fi

if [[ "$MODE" == control ]]; then
  test -f "$STAGE/state.json"
  "$PY" - "$STAGE" "$SOURCE_REF" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]);state=json.loads((root/'state.json').read_text())
assert state['commit']==sys.argv[2] and state['timer_active'] in (0,1) and state['progress_active'] in (0,1)
for name,digest in json.loads((root/'manifest.json').read_text())['files'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest, 'Vorbereitung wurde verändert'
PY
  read -r TIMER_ACTIVE PROGRESS_ACTIVE < <("$PY" - "$STAGE/state.json" <<'PY'
import json,sys
value=json.load(open(sys.argv[1]));print(value['timer_active'],value['progress_active'])
PY
)
  # Real WireGuard RPC and visual comparison before changing installed Pi files.
  PYTHONPATH="$STAGE:$BASE" "$PY" -P - <<'PY'
import copy,random
from skip_remote_client import health,visual_detect
from skip_visual import VisualWindow
health()
rng=random.Random(6102026)
def frames(n): return [[rng.getrandbits(63),rng.getrandbits(64),45,120] for _ in range(n)]
common=frames(48)
target=frames(120);target[20:68]=copy.deepcopy(common)
reference=frames(120);reference[30:78]=copy.deepcopy(common)
a=VisualWindow(target,0,500,60000,180000,'private-test-target',2)
b=VisualWindow(reference,0,500,60000,180000,'private-test-reference',1,[[15000,39000]])
value=visual_detect(a,[b],'intro')
assert value['status']=='AUTO_CONFIRMED' and value['start_ms']==10000 and value['end_ms']==33750
PY
  systemctl stop epimediahub-skip-analysis.timer
  systemctl stop epimediahub-skip-analysis.service
  systemctl stop epimediahub-skip-progress.timer || true
  systemctl stop epimediahub-skip-progress.service || true
  DATA_DIR="$("$PY" - "$ENV_FILE" <<'PY'
import os,shlex,sys
from pathlib import Path
value=os.environ.get('EPIMEDIAHUB_DATA_DIR','/var/lib/epimediahub')
for line in Path(sys.argv[1]).read_text().splitlines():
    key,sep,text=line.partition('=')
    if sep and key.strip()=='EPIMEDIAHUB_DATA_DIR':
        parts=shlex.split(text,comments=True);assert len(parts)==1;value=parts[0]
assert Path(value).is_absolute();print(value)
PY
)"
  exec 9>"$DATA_DIR/skip-analysis.lock"
  flock -w 30 9
  install -d -m 0700 "$BACKUP"
  "$PY" - "$DATA_DIR/provisioning.db" "$BACKUP/provisioning.db" "$BACKUP/episcene-setting.json" <<'PY'
import json,sqlite3,sys
from pathlib import Path
with sqlite3.connect(sys.argv[1]) as source,sqlite3.connect(sys.argv[2]) as target:
    source.backup(target)
    row=source.execute("SELECT value,updated_at FROM skip_auto_metadata_config WHERE name='episcene_enabled'").fetchone()
    Path(sys.argv[3]).write_text(json.dumps(row))
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
from skip_visual import POLICY
value=json.load(open(sys.argv[1]))
assert value.get('status')=='ok' and value.get('versions')==versions()
assert value.get('episcene',{}).get('policy')==POLICY
PY
  echo 'Hetzner bereit für EpiScene: Audio und begrenzte Bildvergleiche.'
  echo "Jetzt auf dem Raspberry: sudo bash /tmp/epimediahub-episcene.sh control $SOURCE_REF"
else
  PYTHONPATH="$BASE" "$PY" -P - "$DATA_DIR/provisioning.db" "$BACKUP/activation-time.json" <<'PY'
import json,sys
from pathlib import Path
from skip_database import connect
from skip_markers import migrate,now
from skip_scene import enabled
with connect(sys.argv[1]) as con:
    migrate(con)
    stamp=now();Path(sys.argv[2]).write_text(json.dumps(stamp))
    first=not enabled(con)
    con.execute("INSERT INTO skip_auto_metadata_config VALUES('episcene_enabled','1',?) ON CONFLICT(name) DO UPDATE SET value='1'",(now(),))
    con.execute("UPDATE skip_jobs SET status='queued',detail='EpiScene: unterbrochenen Auftrag fortsetzen',updated_at=? WHERE status='running'",(now(),))
    if first:
        con.execute('''UPDATE skip_jobs SET status='queued',attempts=0,detail='EpiScene: Bildvergleich für bisher fehlende Intros',updated_at=?
          WHERE status IN ('no_match','no_reference') AND EXISTS (
            SELECT 1 FROM skip_assets a JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
            JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
            JOIN customer_playlists p ON p.id=a.playlist_id JOIN customers c ON c.id=p.customer_id AND c.enabled=1
            WHERE a.asset_key=skip_jobs.asset_key AND a.media_type='episode' AND NOT EXISTS (
              SELECT 1 FROM skip_records r WHERE r.asset_key=a.asset_key AND r.segment_type='intro'
              AND ABS(r.duration_ms-a.duration_ms)<=2000 AND r.status IN ('approved','rejected'))
            AND NOT EXISTS(SELECT 1 FROM skip_auto_blocks b WHERE b.asset_key=a.asset_key AND b.kind='intro'
              AND ABS(b.duration_ms-a.duration_ms)<=2000))''',(stamp,))
PY
  systemctl restart epimediahub-provisioning.service
  curl -fsS --retry 5 --retry-delay 1 --retry-connrefused http://127.0.0.1:8787/health -o "$WORK/health.json"
  "$PY" - "$WORK/health.json" <<'PY'
import json,sys
value=json.load(open(sys.argv[1]))
assert value.get('status')=='ok' and all(value.get('features',{}).get(k) for k in ('skip_episcene','skip_dashboard_cached_statistics','skip_language_stages'))
PY
  PYTHONPATH="$BASE" "$PY" -P -c 'from skip_remote_client import health; health()'
  flock -u 9
  exec 9>&-
  if [[ "$PROGRESS_ACTIVE" == 1 ]]; then
    systemctl start epimediahub-skip-progress.timer
    systemctl start --no-block epimediahub-skip-progress.service
  fi
  if [[ "$TIMER_ACTIVE" == 1 ]]; then
    systemctl start epimediahub-skip-analysis.timer
    systemctl start --no-block epimediahub-skip-analysis.service
  fi
  echo 'EpiScene aktiv: neue Treffer werden durch Bildsequenzen geprüft. Rechenarbeit bleibt auf Hetzner.'
  echo 'Deutsch/Italienisch → Türkisch → übrige Sprachen, Tagesbudget und manuelle Marker bleiben erhalten.'
  rm -f "$STAGE/state.json"
fi
echo "Sicherung: $BACKUP"
