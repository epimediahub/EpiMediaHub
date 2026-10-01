#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [ "$(id -u)" -ne 0 ]; then
  echo 'Bitte mit sudo bash install_skip_automation.sh ausführen.' >&2
  exit 1
fi
enable_automatic=0
if [ "${1:-}" = '--enable-automatic' ]; then
  enable_automatic=1
  shift
fi
if [ "$#" -ne 0 ]; then
  echo 'Erlaubte Option: --enable-automatic' >&2
  exit 1
fi

app_dir=/opt/epimediahub/provisioning
python_bin="$app_dir/.venv/bin/python"
env_file=/etc/epimediahub/provisioning.env
source_ref=f205121b361e7b24144c17df5cc74e155a9a66e4
source_base="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$source_ref/server/epimediahub_provisioning"
task_dir="$(mktemp -d -p /var/tmp epimediahub-skip-automation.XXXXXX)"
backup_dir="/var/backups/epimediahub/skip-automation-$(date +%Y%m%d-%H%M%S)"
services_stopped=0
code_changed=0
settings_changed=0
timer_was_active=0
if systemctl is-active --quiet epimediahub-skip-analysis.timer; then
  timer_was_active=1
fi
files=(skip_analysis.py skip_analysis_worker.py skip_markers.py skip_automation.py templates/skip_markers.html)

cleanup() { rm -rf "$task_dir"; }
recover() {
  local rc=$?
  trap - ERR
  echo 'Update fehlgeschlagen; vorherigen Anwendungscode wiederherstellen.' >&2
  if [ "$services_stopped" -eq 1 ]; then
    systemctl stop epimediahub-provisioning.service || true
  fi
  if [ "$code_changed" -eq 1 ]; then
    for file in "${files[@]}"; do
      if [ -f "$backup_dir/$file" ]; then
        cp -a "$backup_dir/$file" "$app_dir/$file" || true
      else
        rm -f "$app_dir/$file"
      fi
    done
  fi
  if [ "$settings_changed" -eq 1 ]; then
    # Restore only this installer's settings; preserve all live marker/device data.
    "$python_bin" - "$data_dir/provisioning.db" "$backup_dir/provisioning.db" "$task_dir/activation.txt" <<'PY' || true
from pathlib import Path
import sqlite3, sys
live, saved = sqlite3.connect(sys.argv[1]), sqlite3.connect(Path(sys.argv[2]).resolve().as_uri() + '?mode=ro', uri=True)
try:
    stamp = Path(sys.argv[3]).read_text().strip()
    previous = dict((r[0],r) for r in saved.execute('SELECT * FROM skip_auto_settings')) if saved.execute("SELECT 1 FROM sqlite_master WHERE name='skip_auto_settings'").fetchone() else {}
    with live:
        changed = [r[0] for r in live.execute('SELECT playlist_id FROM skip_auto_settings WHERE updated_at=?',(stamp,))]
        for playlist in changed:
            live.execute('DELETE FROM skip_auto_settings WHERE playlist_id=? AND updated_at=?',(playlist,stamp))
            if playlist in previous:
                live.execute('INSERT OR IGNORE INTO skip_auto_settings VALUES(?,?,?,?)',previous[playlist])
        for job in saved.execute('SELECT id,status,attempts,detail,updated_at FROM skip_jobs'):
            live.execute('UPDATE skip_jobs SET status=?,attempts=?,detail=?,updated_at=? WHERE id=? AND updated_at=?',
                         (job[1],job[2],job[3],job[4],job[0],stamp))
finally:
    saved.close(); live.close()
PY
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
test -f "$app_dir/skip_markers.py"
test -f "$app_dir/templates/skip_markers.html"
"$python_bin" - <<'PY'
from flask import Flask
import ctypes.util, shutil
if not ctypes.util.find_library('chromaprint') or not all(shutil.which(p) for p in ('ffmpeg','ffprobe','flock')):
    raise SystemExit('FFmpeg, FFprobe, Chromaprint und flock müssen vorhanden sein.')
PY
curl -fsS --max-time 5 http://127.0.0.1:8787/health -o "$task_dir/health.json"
"$python_bin" - "$task_dir/health.json" <<'PY'
import json, sys
with open(sys.argv[1]) as source:
    data = json.load(source)
if data.get('api_version') != '0.8.2' or data.get('status') != 'ok':
    raise SystemExit('Dieses Update benötigt einen laufenden Raspberry-Server 0.8.2.')
PY
data_dir="$("$python_bin" - "$env_file" <<'PY'
from pathlib import Path
import shlex, sys
directory = '/var/lib/epimediahub'
env = Path(sys.argv[1])
if env.is_file():
    for line in env.read_text().splitlines():
        key, sep, value = line.partition('=')
        if sep and key.strip() == 'EPIMEDIAHUB_DATA_DIR':
            parts = shlex.split(value, comments=True)
            if len(parts) != 1 or not Path(parts[0]).is_absolute():
                raise SystemExit('Ungültige Konfiguration des Datenverzeichnisses.')
            directory = parts[0]
print(directory)
PY
)"
test -f "$data_dir/provisioning.db"

mkdir -p "$task_dir/tests" "$task_dir/deploy" "$task_dir/templates"
downloads=("${files[@]}" tests/test_skip_analysis_redirects.py tests/test_skip_analysis_references.py tests/test_skip_analysis_boundaries.py tests/test_skip_analysis_automation.py deploy/inspect_skip_references.py)
for file in "${downloads[@]}"; do
  curl -fsSL --connect-timeout 10 --max-time 60 "$source_base/$file" -o "$task_dir/$file"
done
sha256sum -c <<EOF
52d225550fc86c2f2a6a907c9ad0a6223d855a3df5196b63c3f77dbba618d80b  $task_dir/skip_analysis.py
41c8a91b3d1655d8cc9ce21fb55f1237fb8058509efebd6bf229c78e8e47ee87  $task_dir/skip_analysis_worker.py
0d3df744887e0049373d849251004d8bd36f52baf27c96adc531d07c2cdc471e  $task_dir/skip_markers.py
d691b60ef366b0354f27025241fb0c9664047b69188e56eac8d7522c51c1e32e  $task_dir/skip_automation.py
84c8b8a8b4db7fa4f5acc344b6ea2a08a7ed6c50f1f24593a9348542ae46f2bd  $task_dir/templates/skip_markers.html
4b4c2faff24503cc3e37740ea232a3279480fe7957b432ed091d1a02a494cf51  $task_dir/tests/test_skip_analysis_redirects.py
9d0efdaaa5b8a45774bff956418212f1aaddeb30e83d2ae0dc9c1e3716a7497e  $task_dir/tests/test_skip_analysis_references.py
2a76f04522b10001e4ff5c0704c41ec596e09ebe47550f541d1a18062c7f52e3  $task_dir/tests/test_skip_analysis_boundaries.py
12bd27da28132bf014e71a0165da0d415c9532042062b9e93a4999b4d5db94eb  $task_dir/tests/test_skip_analysis_automation.py
df57e84d73475ee3ae5dff1183e3d821655f8d805af67bd6fb34369c08cbc87d  $task_dir/deploy/inspect_skip_references.py
EOF
"$python_bin" -m compileall -q "$task_dir"
echo 'Serienzuordnung, Online-Daten, Freigabekriterien und echte Audiospuren prüfen ...'
PYTHONPATH="$task_dir:$app_dir" "$python_bin" -m unittest discover -s "$task_dir/tests" -p 'test_skip_analysis*.py' -q

exec 9>>"$data_dir/skip-analysis.lock"
chown epimediahub:epimediahub "$data_dir/skip-analysis.lock"
if ! flock -n 9; then
  echo 'Der Analysedienst arbeitet gerade. Nach Abschluss erneut ausführen.' >&2
  exit 1
fi
mkdir -p "$backup_dir/templates"
for file in "${files[@]}"; do
  if [ -f "$app_dir/$file" ]; then
    cp -a "$app_dir/$file" "$backup_dir/$file"
  fi
done
services_stopped=1
systemctl stop epimediahub-skip-analysis.timer epimediahub-skip-analysis.service
systemctl stop epimediahub-provisioning.service
"$python_bin" - "$data_dir/provisioning.db" "$backup_dir/provisioning.db" <<'PY'
from pathlib import Path
import sqlite3, sys
source = sqlite3.connect(Path(sys.argv[1]).resolve().as_uri() + '?mode=ro', uri=True)
target = sqlite3.connect(sys.argv[2])
try:
    source.backup(target)
    if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise SystemExit('Die Datenbanksicherung ist nicht gültig.')
finally:
    target.close(); source.close()
PY
code_changed=1
for file in "${files[@]}"; do
  install -o epimediahub -g epimediahub -m 0644 "$task_dir/$file" "$app_dir/$file"
done
if [ "$enable_automatic" -eq 1 ]; then
  settings_changed=1
  PYTHONPATH="$app_dir" "$python_bin" - "$data_dir/provisioning.db" "$task_dir/activation.txt" <<'PY'
from pathlib import Path
import sqlite3, sys
from skip_markers import migrate, now
from skip_analysis import configured_source
con = sqlite3.connect(sys.argv[1]); con.row_factory = sqlite3.Row
try:
    migrate(con)
    stamp = now()
    Path(sys.argv[2]).write_text(stamp)
    with con:
        rows = con.execute('SELECT p.* FROM customer_playlists p JOIN skip_analysis_sources s ON s.playlist_id=p.id AND s.enabled=1 JOIN customers c ON c.id=p.customer_id AND c.enabled=1').fetchall()
        for row in rows:
            try:
                configured_source(row)
            except ValueError:
                continue
            con.execute('INSERT OR REPLACE INTO skip_auto_settings VALUES(?,1,1,?)',(row['id'],stamp))
            con.execute("UPDATE skip_jobs SET status='queued',attempts=0,updated_at=? WHERE asset_key IN (SELECT asset_key FROM skip_assets WHERE playlist_id=?) AND status IN ('disabled','failed','unmatched','no_match','no_reference','review','done')",(stamp,row['id']))
finally:
    con.close()
PY
fi
systemctl restart epimediahub-provisioning.service
healthy=0
for attempt in $(seq 1 20); do
  if curl -fsS --max-time 1 http://127.0.0.1:8787/health -o "$task_dir/health.json" 2>/dev/null; then
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
if data.get('api_version') != '0.8.2' or data.get('status') != 'ok' or data.get('features',{}).get('skip_season_automation') is not True:
    raise SystemExit('Der aktualisierte Server meldet keinen gültigen Automatik-Status.')
PY
if [ "$timer_was_active" -eq 1 ] || [ "$enable_automatic" -eq 1 ]; then
  systemctl start epimediahub-skip-analysis.timer
fi
services_stopped=0
code_changed=0
settings_changed=0
echo 'Raspberry 0.8.2: Staffelautomatik und Online-Zeitvorschläge installiert.'
echo "Backup: $backup_dir"
if [ "$enable_automatic" -eq 1 ]; then
  echo 'Automatik und Online-Abfragen für bereits aktivierte Audio-Playlists eingeschaltet.'
fi
echo 'Geprüfte Marker bleiben erhalten. Weitere Folgen werden im Leerlauf eingeplant.'
echo 'Im Dashboard: Seriennamenssuche mit TMDB-Schlüssel einrichten oder bekannte Serienkennung zuordnen.'
