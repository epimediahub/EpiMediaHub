#!/usr/bin/env bash
# Verify the private worker before switching only heavy computations away from the Pi.
set -Eeuo pipefail
umask 0077
BASE="${EPIMEDIAHUB_APP_DIR:-/opt/epimediahub/provisioning}"
ENV_FILE="${EPIMEDIAHUB_ENV_FILE:-/etc/epimediahub/provisioning.env}"
UNIT_ROOT="${EPIMEDIAHUB_SYSTEMD_DIR:-/etc/systemd/system}"
STAGE="$BASE/remote-analysis-stage"
PY="$BASE/.venv/bin/python"
DROPIN="$UNIT_ROOT/epimediahub-skip-analysis.service.d/remote.conf"
TIMER_DROPIN="$UNIT_ROOT/epimediahub-skip-analysis.timer.d/remote.conf"
REMOTE_URL=http://10.87.26.1:8790
BACKUP="$BASE/backups/remote-analysis-$(date +%Y%m%d-%H%M%S)"
FILES=(skip_analysis.py skip_automation.py skip_analysis_worker.py skip_detector_v2.py skip_detector_v3.py skip_remote_client.py skip_remote_protocol.py skip_remote_verify.py skip_catalogue.py skip_schedule.py skip_app_capture.py skip_release.py skip_markers.py templates/skip_markers.html templates/skip_schedule.html)
TIMER_ACTIVE=0
TIMER_STOPPED=0
INSTALLED=0
systemctl is-active --quiet epimediahub-skip-analysis.timer && TIMER_ACTIVE=1 || true
rollback() {
  code=$?
  trap - ERR
  if [ "$INSTALLED" = 1 ]; then
    for file in "${FILES[@]}"; do
      if [ -f "$BACKUP/$file" ]; then cp -a "$BACKUP/$file" "$BASE/$file"; else rm -f "$BASE/$file"; fi
    done
    if [ -f "$BACKUP/remote.conf" ]; then cp -a "$BACKUP/remote.conf" "$DROPIN"; else rm -f "$DROPIN"; fi
    if [ -f "$BACKUP/timer.conf" ]; then cp -a "$BACKUP/timer.conf" "$TIMER_DROPIN"; else rm -f "$TIMER_DROPIN"; fi
    if [ -f "$BACKUP/skip_remote_role.json" ]; then cp -a "$BACKUP/skip_remote_role.json" "$BASE/skip_remote_role.json"; else rm -f "$BASE/skip_remote_role.json"; fi
    systemctl daemon-reload
    systemctl restart epimediahub-provisioning.service || true
  fi
  if [ "$TIMER_STOPPED" = 1 ] && [ "$TIMER_ACTIVE" = 1 ]; then systemctl start epimediahub-skip-analysis.timer || true; fi
  echo "Umstellung fehlgeschlagen; vorheriger Analysecode und Timer wiederhergestellt." >&2
  exit "$code"
}
trap rollback ERR
if [ "$(id -u)" != 0 ]; then echo "Bitte mit sudo ausführen." >&2; exit 1; fi
test -x "$PY"
test -f "$ENV_FILE"
if [ "$#" -gt 1 ]; then echo "Nur eine Anbieteroption angeben." >&2; exit 1; fi
case "${1:-}" in
  --provider-via-raspberry) PROVIDER_PATH=raspberry ;;
  --provider-direct) PROVIDER_PATH=direct ;;
  "") PROVIDER_PATH="$("$PY" - "$BASE/skip_remote_role.json" <<'PY'
from pathlib import Path
import json,sys
path=Path(sys.argv[1])
value=json.loads(path.read_text()).get('provider_path','direct') if path.exists() else 'direct'
if value not in ('direct','raspberry'): raise SystemExit('Ungültiger Anbieterpfad')
print(value)
PY
)" ;;
  *) echo "Unbekannte Anbieteroption." >&2; exit 1 ;;
esac
export SKIP_ANALYSIS_PROVIDER_PATH="$PROVIDER_PATH"
systemctl is-active --quiet wg-quick@wg-epi-analysis.service
echo "Private Verbindung, Codeversion und Audiovergleich auf Hetzner prüfen …"
SKIP_ANALYSIS_REMOTE_URL="$REMOTE_URL" PYTHONPATH="$STAGE:$BASE" "$PY" - <<'PY'
import random
from skip_remote_client import health,match
health()
rng=random.Random(20261004)
reference=[rng.getrandbits(32) for _ in range(80)]
target=[rng.getrandbits(32) for _ in range(20)]+reference+[rng.getrandbits(32) for _ in range(20)]
assert match(reference,target,125)==(2500,1.0)
print('Hetzner-Code und echter privater Berechnungsaufruf erfolgreich geprüft')
PY
if [ "$PROVIDER_PATH" = raspberry ] && command -v ufw >/dev/null; then
  ufw allow in on wg-epi-analysis from 10.87.26.1 to 10.87.26.2 port 8791 proto tcp
fi
DATA_DIR="$("$PY" - "$ENV_FILE" <<'PY'
from pathlib import Path
import shlex,sys
value='/var/lib/epimediahub'
for line in Path(sys.argv[1]).read_text().splitlines():
    key,sep,text=line.partition('=')
    if sep and key.strip()=='EPIMEDIAHUB_DATA_DIR':
        parts=shlex.split(text,comments=True)
        if len(parts)!=1 or not Path(parts[0]).is_absolute():
            raise SystemExit('Ungültiges Datenverzeichnis')
        value=parts[0]
print(value)
PY
)"
test -f "$DATA_DIR/provisioning.db"
echo "Laufenden Auftrag auslaufen lassen und Sicherung erstellen …"
systemctl stop epimediahub-skip-analysis.timer
TIMER_STOPPED=1
exec 9>"$DATA_DIR/skip-analysis.lock"
flock -w 900 9
systemctl stop epimediahub-skip-analysis.service || true
# Check the real provider after the old worker has finished, while playback
# heartbeats still protect the account. Failure resumes the original timer.
SKIP_ANALYSIS_REMOTE_URL="$REMOTE_URL" PYTHONPATH="$STAGE:$BASE" "$PY" "$STAGE/skip_remote_verify.py" "$DATA_DIR/provisioning.db"
install -d -m 0700 "$BACKUP" "$BACKUP/templates"
for file in "${FILES[@]}"; do [ ! -f "$BASE/$file" ] || cp -a "$BASE/$file" "$BACKUP/$file"; done
[ ! -f "$DROPIN" ] || cp -a "$DROPIN" "$BACKUP/remote.conf"
[ ! -f "$TIMER_DROPIN" ] || cp -a "$TIMER_DROPIN" "$BACKUP/timer.conf"
[ ! -f "$BASE/skip_remote_role.json" ] || cp -a "$BASE/skip_remote_role.json" "$BACKUP/skip_remote_role.json"
"$PY" - "$DATA_DIR/provisioning.db" "$BACKUP/provisioning.db" <<'PY'
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as source,sqlite3.connect(sys.argv[2]) as target:
    source.backup(target)
PY
INSTALLED=1
install -d -m 0755 "$BASE/templates"
for file in "${FILES[@]}"; do install -o root -g root -m 0644 "$STAGE/$file" "$BASE/$file"; done
"$PY" - "$BASE/skip_remote_role.json" "$REMOTE_URL" "$PROVIDER_PATH" <<'PY'
from pathlib import Path
import json,sys
path=Path(sys.argv[1])
path.write_text(json.dumps({'protocol':1,'url':sys.argv[2],'provider_path':sys.argv[3]})+'\n')
path.chmod(0o644)
PY
install -d -m 0755 "$(dirname "$DROPIN")" "$(dirname "$TIMER_DROPIN")"
cat > "$DROPIN" <<EOF
[Unit]
After=wg-quick@wg-epi-analysis.service
Wants=wg-quick@wg-epi-analysis.service
[Service]
ExecStart=
ExecStart=$PY skip_analysis_worker.py --batch --max-jobs 8 --max-seconds 600
Environment=SKIP_ANALYSIS_REMOTE_URL=$REMOTE_URL
Environment=SKIP_ANALYSIS_PROVIDER_PATH=$PROVIDER_PATH
EOF
chmod 0644 "$DROPIN"
cat > "$TIMER_DROPIN" <<'EOF'
[Timer]
OnUnitInactiveSec=
OnUnitInactiveSec=5s
RandomizedDelaySec=5s
AccuracySec=1s
EOF
chmod 0644 "$TIMER_DROPIN"
systemctl daemon-reload
SKIP_ANALYSIS_REMOTE_URL="$REMOTE_URL" PYTHONPATH="$BASE" "$PY" -c 'from skip_remote_client import health; health()'
systemctl restart epimediahub-provisioning.service
curl -fsS --retry 5 --retry-delay 2 --retry-connrefused http://127.0.0.1:8787/health -o "$STAGE/dashboard-health.json"
"$PY" - "$STAGE/dashboard-health.json" <<'PY'
import json,sys
with open(sys.argv[1]) as source:
    health=json.load(source)
assert health.get('status')=='ok' and all(health.get('features',{}).get(name) for name in ('skip_playlist_order','skip_fingerprint_capture'))
print('Dashboard gesund; Playlist-Reihenfolge und App-Fingerprints verfügbar')
PY
flock -u 9
exec 9>&-
systemctl start epimediahub-skip-analysis.timer
systemctl start --no-block epimediahub-skip-analysis.service
echo "Auslagerung aktiviert: Audiodekodierung, Chromaprint und Fingerprint-Vergleiche laufen auf Hetzner."
if [ "$PROVIDER_PATH" = raspberry ]; then
  echo "Anbieterabruf: komprimierte Mediendaten werden vom Raspberry privat zu Hetzner durchgereicht."
else
  echo "Anbieterabruf: Hetzner liest die Mediendaten direkt."
fi
echo "Der Raspberry steuert Aufträge, Wiedergabe-Abstimmung und zentrale Zeitmarken."
echo "Playlist-Reihenfolge im Dashboard anpassbar. Jede Serie wird nach Staffel und Folge abgearbeitet."
echo "Deutsch/Italienisch innerhalb der aktuellen Playlist, automatische Freigabekriterien und bestehendes Tagesbudget bleiben erhalten."
echo "Bis zu acht aufeinanderfolgende Aufträge; kurze Timerpause. Vorhandene Audiofenster werden weiterverwendet."
echo "Bei Verbindungsabbruch wird pausiert; es gibt keine zweite lokale Audioanalyse."
echo "Sicherung: $BACKUP"
