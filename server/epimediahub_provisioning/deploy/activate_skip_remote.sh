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
REMOTE_URL=http://10.87.26.1:8790
BACKUP="$BASE/backups/remote-analysis-$(date +%Y%m%d-%H%M%S)"
FILES=(skip_analysis.py skip_automation.py skip_analysis_worker.py skip_detector_v2.py skip_detector_v3.py skip_remote_client.py skip_remote_protocol.py skip_remote_verify.py)
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
    if [ -f "$BACKUP/skip_remote_role.json" ]; then cp -a "$BACKUP/skip_remote_role.json" "$BASE/skip_remote_role.json"; else rm -f "$BASE/skip_remote_role.json"; fi
    systemctl daemon-reload
  fi
  if [ "$TIMER_STOPPED" = 1 ] && [ "$TIMER_ACTIVE" = 1 ]; then systemctl start epimediahub-skip-analysis.timer || true; fi
  echo "Umstellung fehlgeschlagen; vorheriger Analysecode und Timer wiederhergestellt." >&2
  exit "$code"
}
trap rollback ERR
if [ "$(id -u)" != 0 ]; then echo "Bitte mit sudo ausführen." >&2; exit 1; fi
test -x "$PY"
test -f "$ENV_FILE"
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
install -d -m 0700 "$BACKUP"
for file in "${FILES[@]}"; do [ ! -f "$BASE/$file" ] || cp -a "$BASE/$file" "$BACKUP/$file"; done
[ ! -f "$DROPIN" ] || cp -a "$DROPIN" "$BACKUP/remote.conf"
[ ! -f "$BASE/skip_remote_role.json" ] || cp -a "$BASE/skip_remote_role.json" "$BACKUP/skip_remote_role.json"
"$PY" - "$DATA_DIR/provisioning.db" "$BACKUP/provisioning.db" <<'PY'
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as source,sqlite3.connect(sys.argv[2]) as target:
    source.backup(target)
PY
INSTALLED=1
for file in "${FILES[@]}"; do install -o root -g root -m 0644 "$STAGE/$file" "$BASE/$file"; done
"$PY" - "$BASE/skip_remote_role.json" "$REMOTE_URL" <<'PY'
from pathlib import Path
import json,sys
path=Path(sys.argv[1])
path.write_text(json.dumps({'protocol':1,'url':sys.argv[2]})+'\n')
path.chmod(0o644)
PY
install -d -m 0755 "$(dirname "$DROPIN")"
cat > "$DROPIN" <<EOF
[Unit]
After=wg-quick@wg-epi-analysis.service
Wants=wg-quick@wg-epi-analysis.service
[Service]
Environment=SKIP_ANALYSIS_REMOTE_URL=$REMOTE_URL
EOF
chmod 0644 "$DROPIN"
systemctl daemon-reload
SKIP_ANALYSIS_REMOTE_URL="$REMOTE_URL" PYTHONPATH="$BASE" "$PY" -c 'from skip_remote_client import health; health()'
flock -u 9
exec 9>&-
systemctl start epimediahub-skip-analysis.timer
systemctl start --no-block epimediahub-skip-analysis.service
echo "Auslagerung aktiviert: Provider-Audio, Chromaprint und Fingerprint-Vergleiche laufen auf Hetzner."
echo "Der Raspberry behält nur Auftragssteuerung, Wiedergabe-Abstimmung und zentrale Zeitmarken."
echo "Deutsch/Italienisch, automatische Freigabekriterien und bestehendes Tagesbudget bleiben erhalten."
echo "Bei Verbindungsabbruch wird pausiert; es gibt keine zweite lokale Audioanalyse."
echo "Sicherung: $BACKUP"
