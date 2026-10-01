#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [ "$(id -u)" -ne 0 ]; then
  echo 'Bitte mit sudo bash fix_skip_analysis_boundaries.sh ausführen.' >&2
  exit 1
fi

app_dir=/opt/epimediahub/provisioning
python_bin="$app_dir/.venv/bin/python"
env_file=/etc/epimediahub/provisioning.env
source_ref=0efd95751c7da3364947f53e9efee0f09a55d98b
source_base="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$source_ref/server/epimediahub_provisioning"
task_dir="$(mktemp -d -p /var/tmp epimediahub-boundary-fix.XXXXXX)"
backup_dir="/var/backups/epimediahub/skip-boundaries-$(date +%Y%m%d-%H%M%S)"
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
    cp -a "$backup_dir/skip_markers.py" "$app_dir/skip_markers.py" || true
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
"$python_bin" - <<'PY'
from flask import Flask
import ctypes.util, shutil
if not ctypes.util.find_library("chromaprint") or not all(shutil.which(program) for program in ("ffmpeg", "ffprobe", "flock")):
    raise SystemExit("FFmpeg, FFprobe, Chromaprint und flock müssen vorhanden sein.")
PY
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

mkdir -p "$task_dir/tests" "$task_dir/deploy"
curl -fsSL --connect-timeout 10 --max-time 60 "$source_base/skip_analysis.py" -o "$task_dir/skip_analysis.py"
curl -fsSL --connect-timeout 10 --max-time 60 "$source_base/skip_analysis_worker.py" -o "$task_dir/skip_analysis_worker.py"
curl -fsSL --connect-timeout 10 --max-time 60 "$source_base/skip_markers.py" -o "$task_dir/skip_markers.py"
curl -fsSL --connect-timeout 10 --max-time 60 "$source_base/tests/test_skip_analysis_redirects.py" -o "$task_dir/tests/test_skip_analysis_redirects.py"
curl -fsSL --connect-timeout 10 --max-time 60 "$source_base/tests/test_skip_analysis_references.py" -o "$task_dir/tests/test_skip_analysis_references.py"
curl -fsSL --connect-timeout 10 --max-time 60 "$source_base/tests/test_skip_analysis_boundaries.py" -o "$task_dir/tests/test_skip_analysis_boundaries.py"
curl -fsSL --connect-timeout 10 --max-time 60 "$source_base/deploy/inspect_skip_references.py" -o "$task_dir/deploy/inspect_skip_references.py"
sha256sum -c <<EOF
30f554502c7e1b345adceb948febed549291e998d5a3d8f4219fcb178fbd9dc0  $task_dir/skip_analysis.py
a6ffb9c51d8d1120407441278e1dea1c145bbfe02da2f8fab2e6319690781a49  $task_dir/skip_analysis_worker.py
5aab2b85d3b37544e9ad33c161d26092f9d6f036fc47b66eeadfbe3844be9b3f  $task_dir/skip_markers.py
4b4c2faff24503cc3e37740ea232a3279480fe7957b432ed091d1a02a494cf51  $task_dir/tests/test_skip_analysis_redirects.py
9d0efdaaa5b8a45774bff956418212f1aaddeb30e83d2ae0dc9c1e3716a7497e  $task_dir/tests/test_skip_analysis_references.py
2a76f04522b10001e4ff5c0704c41ec596e09ebe47550f541d1a18062c7f52e3  $task_dir/tests/test_skip_analysis_boundaries.py
df57e84d73475ee3ae5dff1183e3d821655f8d805af67bd6fb34369c08cbc87d  $task_dir/deploy/inspect_skip_references.py
EOF
"$python_bin" -m py_compile "$task_dir/skip_analysis.py" "$task_dir/skip_analysis_worker.py" "$task_dir/skip_markers.py"
echo 'Genauere Zeitgrenzen, korrigierte Referenzen und Anbieterweiterleitungen prüfen ...'
PYTHONPATH="$task_dir:$app_dir" "$python_bin" -m unittest discover -s "$task_dir/tests" -p 'test_skip_analysis*.py' -q

# Acquire the same inode lock as the worker before stopping services.
# A currently running analysis completes normally; this installer can be rerun.
exec 9>>"$data_dir/skip-analysis.lock"
chown epimediahub:epimediahub "$data_dir/skip-analysis.lock"
if ! flock -n 9; then
  echo 'Der Analysedienst arbeitet gerade. Nach Abschluss erneut ausführen.' >&2
  exit 1
fi

mkdir -p "$backup_dir"
cp -a "$app_dir/skip_analysis.py" "$backup_dir/skip_analysis.py"
cp -a "$app_dir/skip_analysis_worker.py" "$backup_dir/skip_analysis_worker.py"
cp -a "$app_dir/skip_markers.py" "$backup_dir/skip_markers.py"
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
install -o epimediahub -g epimediahub -m 0644 "$task_dir/skip_markers.py" "$app_dir/skip_markers.py"
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
if data.get("api_version") != "0.8.2" or data.get("status") != "ok":
    raise SystemExit("Der aktualisierte Server meldet keinen gültigen Status.")
PY

if [ "$timer_was_active" -eq 1 ]; then
  systemctl start epimediahub-skip-analysis.timer
fi
services_stopped=0
code_changed=0
echo 'Raspberry 0.8.2: Genauere Intro-Zeitgrenzen installiert.'
echo "Backup: $backup_dir"
echo 'Vorhandene Zeitmarken und Freigaben bleiben erhalten.'
echo 'Für den Vergleich die nächste noch unmarkierte Folge öffnen und wieder beenden.'
echo 'Neue Vorschläge im Dashboard unter Zur Prüfung kontrollieren.'
