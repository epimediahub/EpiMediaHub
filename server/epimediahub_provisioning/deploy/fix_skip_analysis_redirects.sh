#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [ "$(id -u)" -ne 0 ]; then
  echo 'Bitte mit sudo bash fix_skip_analysis_redirects.sh ausführen.' >&2
  exit 1
fi

app_dir=/opt/epimediahub/provisioning
python_bin="$app_dir/.venv/bin/python"
env_file=/etc/epimediahub/provisioning.env
source_ref=9ccc8f7da3fa38457eb4b34bea8892e245025b2a
source_base="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$source_ref/server/epimediahub_provisioning"
task_dir="$(mktemp -d -p /var/tmp epimediahub-redirect-fix.XXXXXX)"
backup_dir="/var/backups/epimediahub/skip-redirect-$(date +%Y%m%d-%H%M%S)"
services_stopped=0
code_changed=0
timer_was_active=0
if systemctl is-active --quiet epimediahub-skip-analysis.timer; then
  timer_was_active=1
fi

cleanup() {
  rm -rf "$task_dir"
}

recover() {
  local rc=$?
  trap - ERR
  echo 'Korrektur fehlgeschlagen; vorherigen Anwendungscode wiederherstellen.' >&2
  if [ "$code_changed" -eq 1 ]; then
    cp -a "$backup_dir/skip_analysis.py" "$app_dir/skip_analysis.py" || true
    cp -a "$backup_dir/skip_analysis_worker.py" "$app_dir/skip_analysis_worker.py" || true
  fi
  if [ "$services_stopped" -eq 1 ]; then
    systemctl restart epimediahub-provisioning.service || true
    if [ "$timer_was_active" -eq 1 ]; then
      systemctl start epimediahub-skip-analysis.timer || true
    fi
  fi
  exit "$rc"
}

trap cleanup EXIT
trap recover ERR

test -x "$python_bin"
test -f "$app_dir/skip_analysis.py"
test -f "$app_dir/skip_analysis_worker.py"
curl -fsS --max-time 5 http://127.0.0.1:8787/health -o "$task_dir/health.json"
"$python_bin" - "$task_dir/health.json" <<'PY'
import json, sys
with open(sys.argv[1]) as source:
    data = json.load(source)
if data.get("api_version") != "0.8.2" or data.get("status") != "ok":
    raise SystemExit("Diese Korrektur benötigt einen laufenden Raspberry-Server 0.8.2.")
PY

# Read only the data directory; never execute the environment file or print secrets.
data_dir="$("$python_bin" - "$env_file" <<'PY'
from pathlib import Path
import shlex, sys
directory = "/var/lib/epimediahub"
env = Path(sys.argv[1])
if env.is_file():
    for line in env.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == "EPIMEDIAHUB_DATA_DIR":
            parts = shlex.split(value, comments=True)
            if len(parts) != 1 or not Path(parts[0]).is_absolute():
                raise SystemExit("Ungültige Konfiguration des Datenverzeichnisses.")
            directory = parts[0]
print(directory)
PY
)"
test -f "$data_dir/provisioning.db"

mkdir -p "$task_dir/tests"
curl -fsSL --connect-timeout 10 --max-time 60 "$source_base/skip_analysis.py" -o "$task_dir/skip_analysis.py"
curl -fsSL --connect-timeout 10 --max-time 60 "$source_base/skip_analysis_worker.py" -o "$task_dir/skip_analysis_worker.py"
curl -fsSL --connect-timeout 10 --max-time 60 "$source_base/tests/test_skip_analysis_redirects.py" -o "$task_dir/tests/test_skip_analysis_redirects.py"
sha256sum -c <<EOF
64a2c4841121005bc930d8b572a851c9a28ea98f995b9a76a039acd0b993686e  $task_dir/skip_analysis.py
6b351177523463b0df72db73d5e362cc76aa0ff948a79809a1ce48cd9ffd77a5  $task_dir/skip_analysis_worker.py
4b4c2faff24503cc3e37740ea232a3279480fe7957b432ed091d1a02a494cf51  $task_dir/tests/test_skip_analysis_redirects.py
EOF
"$python_bin" -m py_compile "$task_dir/skip_analysis.py" "$task_dir/skip_analysis_worker.py"
echo 'Weiterleitungen und Audioauswertung vor der Installation prüfen ...'
PYTHONPATH="$task_dir:$app_dir" "$python_bin" -m unittest discover -s "$task_dir/tests" -p test_skip_analysis_redirects.py -q

mkdir -p "$backup_dir"
cp -a "$app_dir/skip_analysis.py" "$backup_dir/skip_analysis.py"
cp -a "$app_dir/skip_analysis_worker.py" "$backup_dir/skip_analysis_worker.py"
services_stopped=1
systemctl stop epimediahub-skip-analysis.timer epimediahub-skip-analysis.service
systemctl stop epimediahub-provisioning.service
"$python_bin" - "$data_dir/provisioning.db" "$backup_dir/provisioning.db" <<'PY'
from pathlib import Path
import sqlite3, sys
source = sqlite3.connect(Path(sys.argv[1]).resolve().as_uri() + "?mode=ro", uri=True)
target = sqlite3.connect(sys.argv[2])
try:
    source.backup(target)
    if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise SystemExit("Die Datenbanksicherung ist nicht gültig.")
finally:
    target.close()
    source.close()
PY

code_changed=1
install -o epimediahub -g epimediahub -m 0644 "$task_dir/skip_analysis.py" "$app_dir/skip_analysis.py"
install -o epimediahub -g epimediahub -m 0644 "$task_dir/skip_analysis_worker.py" "$app_dir/skip_analysis_worker.py"
systemctl restart epimediahub-provisioning.service
healthy=0
for attempt in $(seq 1 20); do
  if curl -fsS --max-time 1 http://127.0.0.1:8787/health -o "$task_dir/health.json"; then
    healthy=1
    break
  fi
  sleep 1
done
test "$healthy" -eq 1
"$python_bin" - "$task_dir/health.json" <<'PY'
import json, sys
with open(sys.argv[1]) as source:
    data = json.load(source)
if data.get("api_version") != "0.8.2" or data.get("status") != "ok":
    raise SystemExit("Der aktualisierte Server meldet keinen gültigen Status.")
PY

retry_count="$("$python_bin" - "$data_dir/provisioning.db" <<'PY'
from datetime import datetime, timezone
import sqlite3, sys
with sqlite3.connect(sys.argv[1], timeout=10) as con:
    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    count = con.execute("""
      UPDATE skip_jobs SET status='queued',attempts=0,detail='',updated_at=?
      WHERE status='failed' AND asset_key IN (
        SELECT a.asset_key FROM skip_assets a
        JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id
        WHERE s.enabled=1)
    """, (stamp,)).rowcount
print(count)
PY
)"
if [ "$timer_was_active" -eq 1 ]; then
  systemctl start epimediahub-skip-analysis.timer
fi
services_stopped=0
code_changed=0
echo 'Raspberry 0.8.2: Korrektur für Anbieterweiterleitungen installiert.'
echo "Fehlgeschlagene Analyseaufträge erneut eingeplant: $retry_count"
echo "Backup: $backup_dir"
echo 'Ergebnis im Dashboard unter Audioanalyse pro Playlist / Letzte Analysen prüfen.'
