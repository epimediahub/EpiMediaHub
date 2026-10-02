#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [ "$(id -u)" -ne 0 ]; then
  echo 'Bitte mit sudo bash install_skip_catalogue.sh ausführen.' >&2
  exit 1
fi
start_catalogue=0
wait_worker=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --start-catalogue) start_catalogue=1 ;;
    --wait-worker) wait_worker=1 ;;
    *) echo 'Erlaubte Optionen: --start-catalogue, --wait-worker' >&2; exit 1 ;;
  esac
  shift
done

app_dir=/opt/epimediahub/provisioning
python_bin="$app_dir/.venv/bin/python"
env_file=/etc/epimediahub/provisioning.env
source_ref=eb2318c979b7403d1adf5b269cc00dc22a091101
source_base="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$source_ref/server/epimediahub_provisioning"
task_dir="$(mktemp -d -p /var/tmp epimediahub-skip-catalogue.XXXXXX)"
backup_dir="/var/backups/epimediahub/skip-catalogue-$(date +%Y%m%d-%H%M%S)"
services_stopped=0
code_changed=0
settings_changed=0
timer_was_active=0
if systemctl is-active --quiet epimediahub-skip-analysis.timer; then
  timer_was_active=1
fi
files=(skip_analysis.py skip_analysis_worker.py skip_markers.py skip_automation.py skip_catalogue.py templates/skip_markers.html)

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
    exists = lambda con, table: bool(con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone())
    previous = dict((r[0],r) for r in saved.execute('SELECT * FROM skip_catalogue_settings')) if exists(saved,'skip_catalogue_settings') else {}
    previous_runs = dict((r[0],r) for r in saved.execute('SELECT playlist_id,generation,next_due,retry_at FROM skip_catalogue_runs')) if exists(saved,'skip_catalogue_runs') else {}
    with live:
        changed = [r[0] for r in live.execute('SELECT playlist_id FROM skip_catalogue_settings WHERE updated_at=?',(stamp,))]
        for playlist in changed:
            live.execute('DELETE FROM skip_catalogue_settings WHERE playlist_id=? AND updated_at=?',(playlist,stamp))
            if playlist in previous:
                live.execute('INSERT OR IGNORE INTO skip_catalogue_settings VALUES(?,?,?)',previous[playlist])
            if playlist in previous_runs:
                old=previous_runs[playlist]
                live.execute('UPDATE skip_catalogue_runs SET next_due=?,retry_at=? WHERE playlist_id=? AND generation=?',(old[2],old[3],playlist,old[1]))
            else:
                live.execute('DELETE FROM skip_catalogue_runs WHERE playlist_id=? AND generation=0',(playlist,))
        before = saved.execute("SELECT name,value,updated_at FROM skip_catalogue_config WHERE name='daily_limit'").fetchone() if exists(saved,'skip_catalogue_config') else None
        if live.execute("SELECT 1 FROM skip_catalogue_config WHERE name='daily_limit' AND updated_at=?",(stamp,)).fetchone():
            live.execute("DELETE FROM skip_catalogue_config WHERE name='daily_limit' AND updated_at=?",(stamp,))
            if before:
                live.execute('INSERT OR IGNORE INTO skip_catalogue_config VALUES(?,?,?)',before)
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
from zoneinfo import ZoneInfo
ZoneInfo("Europe/Berlin")
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
downloads=("${files[@]}" tests/test_skip_analysis_redirects.py tests/test_skip_analysis_references.py tests/test_skip_analysis_boundaries.py tests/test_skip_analysis_automation.py tests/test_skip_analysis_catalogue.py tests/test_skip_analysis_dashboard.py tests/test_skip_analysis_dedup.py tests/test_skip_analysis_online_errors.py tests/test_skip_analysis_languages.py tests/test_skip_analysis_bulk_review.py deploy/inspect_skip_references.py)
for file in "${downloads[@]}"; do
  curl -fsSL --connect-timeout 10 --max-time 60 "$source_base/$file" -o "$task_dir/$file"
done
sha256sum -c <<EOF
8ded57ab108a2ca06ad03ecabd09ee1435eb96ad7da2b3977657f5a8229241c1  $task_dir/skip_analysis.py
6c4ef57cec2a8b46a835da57f71e6241fecf4e5a3f2de210e2c852361d40f9e8  $task_dir/skip_analysis_worker.py
43a398b11c9bce7f1844ae55b524767251bb542d7a16675fc9e14277c823d6fe  $task_dir/skip_markers.py
6379c6f42c3eb52c13ee70dae4bb88476037ba2350bf964a2467317c2f87056f  $task_dir/skip_automation.py
eb3349381aa10894ffac50ba7af27ad27f112ca1800fabcf3776ffd9556b5a60  $task_dir/skip_catalogue.py
462e99ca72e5ed4af04542c42a858664321fbfe0ba7bba2c8ad8537915601b03  $task_dir/templates/skip_markers.html
c058c9f1b6702f99406ca15b2160f46ff1b80ec9235860445fe062f98b2ab788  $task_dir/tests/test_skip_analysis_redirects.py
9d0efdaaa5b8a45774bff956418212f1aaddeb30e83d2ae0dc9c1e3716a7497e  $task_dir/tests/test_skip_analysis_references.py
2a76f04522b10001e4ff5c0704c41ec596e09ebe47550f541d1a18062c7f52e3  $task_dir/tests/test_skip_analysis_boundaries.py
03a3211aac1c6fb753144c663e9793b76ace5944003bc65973981d58679383aa  $task_dir/tests/test_skip_analysis_automation.py
ea9187e05321cdae8a9df25a166f346f6325d4d52c0d339840e455f6475a2423  $task_dir/tests/test_skip_analysis_catalogue.py
07cd572fefdd61bebec2eda9209005917bfbc0c7117411b42f102e8b6ae110e0  $task_dir/tests/test_skip_analysis_dashboard.py
e65184b85ee5de3d58b0835e054973c6f1c8c496dc3ade7426fc570c748e7b08  $task_dir/tests/test_skip_analysis_dedup.py
66f94841a88568511c40a7a4a06b244f0ea8cc38d5b3f6de308e0d05a9e7a68b  $task_dir/tests/test_skip_analysis_online_errors.py
5d63c5afbb7194e715296bfdbe36e6872dca31b63c51a175942b183af5e2a4de  $task_dir/tests/test_skip_analysis_languages.py
615807c790aac9390b8eec8307687c96457cd3061763fe585797369efc869715  $task_dir/tests/test_skip_analysis_bulk_review.py
df57e84d73475ee3ae5dff1183e3d821655f8d805af67bd6fb34369c08cbc87d  $task_dir/deploy/inspect_skip_references.py
EOF
"$python_bin" -m compileall -q "$task_dir"
echo 'Sprachpriorität, Serien-/Staffelfreigaben, Online-Abfragen und Audioanalyse prüfen ...'
PYTHONPATH="$task_dir:$app_dir" "$python_bin" -m unittest discover -s "$task_dir/tests" -p 'test_skip_analysis*.py' -q

exec 9>>"$data_dir/skip-analysis.lock"
chown epimediahub:epimediahub "$data_dir/skip-analysis.lock"
lock_options=(-n)
if [ "$wait_worker" -eq 1 ]; then
  echo 'Auf den laufenden Analysedurchlauf warten (höchstens 15 Minuten) ...'
  lock_options=(-w 900)
fi
if ! flock "${lock_options[@]}" 9; then
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
if [ "$start_catalogue" -eq 1 ]; then
  settings_changed=1
  PYTHONPATH="$app_dir" "$python_bin" - "$data_dir/provisioning.db" "$task_dir/activation.txt" <<'PY'
from pathlib import Path
import sqlite3, sys
from skip_markers import migrate, now
from skip_catalogue import start, DEFAULT_DAILY_LIMIT
con = sqlite3.connect(sys.argv[1]); con.row_factory = sqlite3.Row
try:
    migrate(con)
    stamp = now()
    Path(sys.argv[2]).write_text(stamp)
    with con:
        rows = con.execute('SELECT playlist_id FROM skip_auto_settings WHERE enabled=1').fetchall()
        for row in rows:
            start(con,row['playlist_id'],stamp)
        con.execute("INSERT OR IGNORE INTO skip_catalogue_config VALUES('daily_limit',?,?)",(DEFAULT_DAILY_LIMIT,stamp))
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
if data.get('api_version') != '0.8.2' or data.get('status') != 'ok' or not all(data.get('features',{}).get(name) is True for name in ('skip_nightly_catalogue','skip_high_audio_approval','skip_proposal_dedup','skip_online_error_details','skip_language_priority','skip_bulk_review','skip_network_address_fallback')):
    raise SystemExit('Der aktualisierte Server meldet keinen gültigen Analyse-Status.')
PY
if [ "$timer_was_active" -eq 1 ] || [ "$start_catalogue" -eq 1 ]; then
  systemctl start epimediahub-skip-analysis.timer
fi
services_stopped=0
code_changed=0
settings_changed=0
echo 'Raspberry 0.8.2: Online-Abfragen unterscheiden fehlende Zeitmarken, Zugriffsfehler und Abfragelimits.'
echo 'Netzwerkzugriff versucht alternative öffentliche IPv4-/IPv6-Adressen bei Verbindungsausfällen.'
echo "Backup: $backup_dir"
if [ "$start_catalogue" -eq 1 ]; then
  echo 'Erster Katalogdurchlauf für bereits aktivierte Automatik-Playlists eingeplant.'
fi
echo 'Danach täglich ab 03:00 Uhr deutscher Zeit neue und geänderte Folgen prüfen.'
echo 'TMDB-Schlüssel und geprüfte Marker bleiben erhalten.'
echo 'Zeitmarken im Dashboard nach Serie, Staffel und Folge öffnen.'
echo 'Unter Zur Prüfung alle offenen Vorschläge einer Serie oder Staffel mit einem Button freigeben.'
echo 'Widersprüchliche Vorschläge bleiben zur Einzelprüfung offen.'
echo 'Bisherige unklare Online-Fehler werden im Leerlauf erneut geprüft, ohne erneute Audioanalyse.'
echo 'Deutsch und Italienisch werden gemeinsam bevorzugt, danach die übrigen Serien.'
echo 'Bestehende Warteschlangen erhalten einmalig eine neue Sprachzuordnung aus Anbieterkategorien.'
echo 'Fortschritt und Tageslimit im Dashboard unter Gesamtkatalog & Nachtprüfung prüfen.'
