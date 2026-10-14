#!/usr/bin/env bash
# Targeted EpiScene provenance importer repair V2.
# Only the Learning Engine's bridge file changes; analyzer DB is never written.
set -Eeuo pipefail
umask 077
PIN=8d1f69f249fb94b89394f8f518f47abfc77d211b
SHA=daecfb4ffb698b0e4ae86b49f2fe0dcae1d01370fac200f77809d122d89cfe08
ROOT=/var/lib/episcene-learning
APP=/opt/episcene-learning
SERVICE=episcene-learning-provenance
TMP="$(mktemp -d -t episcene-import-repair.XXXXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
[[ $EUID -eq 0 ]] || { echo 'Bitte als root ausfuehren.' >&2; exit 2; }
for bin in curl sha256sum python3 install systemctl journalctl; do
  command -v "$bin" >/dev/null || { echo "Fehlendes Programm: $bin" >&2; exit 2; }
done
[[ -f "$ROOT/knowledge.sqlite3" && -f /var/lib/epimediahub/provisioning.db &&
   -f "$APP/approval_history_bridge.py" ]] || { echo 'Learning Engine / Quelldatenbank nicht gefunden' >&2; exit 2; }
curl -fsSL --retry 2 --max-time 45 \
  "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$PIN/tools/episcene-learning-v1/approval_history_bridge.py" \
  -o "$TMP/approval_history_bridge.py"
printf '%s  %s\n' "$SHA" "$TMP/approval_history_bridge.py" | sha256sum -c -
echo 'Pruefe Import mit Testdatenbank, inklusive Wiederholung und App-Fenstern ...'
python3 - "$TMP/approval_history_bridge.py" "$TMP" <<'PY_TEST'
import contextlib
import importlib.util
import io
import json
import pathlib
import sqlite3
import sys
src,folder=sys.argv[1:3]
compile(pathlib.Path(src).read_bytes(),src,'exec')
spec=importlib.util.spec_from_file_location('episcene_provenance_check',src)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
db=pathlib.Path(folder)/'fixture.sqlite3'
spool=pathlib.Path(folder)/'fixture.jsonl'
with sqlite3.connect(db):pass
marker=[123,'fixture-asset',8,'fixture-source','Testserie',1,1,'intro',
        2000,32000,'device','approved',0.96,'2026-10-14','2026-10-13']
app=['fixture-asset',8,2,'2026-10-14','2026-10-14']
spool.write_text(
    json.dumps({'type':'marker','row':marker})+'\n'+
    json.dumps({'type':'app_window','row':app})+'\n',encoding='utf-8')
with contextlib.redirect_stdout(io.StringIO()):
    mod.import_candidates(str(spool),str(db))
    mod.import_candidates(str(spool),str(db))
with sqlite3.connect(db) as conn:
    assert conn.execute('SELECT COUNT(*) FROM legacy_marker_snapshots').fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM legacy_app_window_observations').fetchone()[0]==1
    assert conn.execute('SELECT provenance FROM legacy_marker_snapshots').fetchone()[0]=='unverified_source_status'
print('Importtest OK: SQL, App-Fenster, Idempotenz, Herkunftskennzeichnung')
PY_TEST
# Back up only the separate Learning Engine DB using the SQLite online-backup API.
install -d -o episcene-learning -g episcene-learning -m 0700 "$ROOT/backups"
BACKUP="$ROOT/backups/knowledge-before-import-repair-v2.sqlite3"
if [[ ! -e "$BACKUP" ]]; then
    python3 - "$ROOT/knowledge.sqlite3" "$BACKUP" <<'PY_BACKUP'
import sqlite3,sys,pwd,os
a,b=sys.argv[1:3]
with sqlite3.connect(a) as source, sqlite3.connect(b) as destination:
    source.backup(destination)
owner=pwd.getpwnam('episcene-learning')
os.chown(b,owner.pw_uid,owner.pw_gid)
os.chmod(b,0o600)
print('Learning-DB-Sicherheitskopie erstellt')
PY_BACKUP
fi
install -o root -g root -m 0644 "$TMP/approval_history_bridge.py" "$APP/approval_history_bridge.py"
echo 'Starte beide Dienste ...'
if ! systemctl start "$SERVICE.service"; then
  echo 'EXPORT FEHLER'
  journalctl -u "$SERVICE.service" -n 30 --no-pager -o cat || true
  exit 3
fi
if ! systemctl start "$SERVICE-import.service"; then
  echo 'IMPORT FEHLER - Details:'
  journalctl -u "$SERVICE-import.service" -n 40 --no-pager -o cat || true
  exit 4
fi
systemctl enable --now "$SERVICE.timer" >/dev/null
echo '=== IMPORT ERGEBNIS ==='
journalctl -u "$SERVICE-import.service" -n 12 --no-pager -o cat || true
echo '=== TIMER ==='
systemctl is-enabled "$SERVICE.timer"
echo 'ERFOLG: Lernkandidaten in Schattenmodus. Keine automatische Kundenfreigabe.'
