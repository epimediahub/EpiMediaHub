#!/usr/bin/env bash
# EpiScene owner-reference shadow engine. Does not edit original analyzer data.
set -Eeuo pipefail
umask 077
[[ $EUID == 0 ]] || { echo "Bitte als root ausfuehren." >&2; exit 2; }
REV=c9695e6deeb9f816c55d1e1843342ffb11c2b5c6
BASE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$REV/tools/episcene-learning-v1/active-shadow"
CODE_SHA=03164cd675c53c6149edbe501c11253ae655ab12ff0d1676dafb631e7a92c180
TEST_SHA=3fd0d4e86e4509b202e728e70eae95d9c2e5d88c1b8bea87bcfc4bbe934fc32e
ROOT=/var/lib/episcene-learning/reference-round-40
SOURCE=/var/lib/epimediahub/provisioning.db
TARGET=/opt/episcene-learning/reference_engine.py
SERVICE=episcene-owner-learning-shadow
TMP="$(mktemp -d -t episcene-reference-install.XXXXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
for tool in curl sha256sum python3 install systemctl stat; do
    command -v "$tool" >/dev/null || { echo "Fehlendes Programm: $tool" >&2; exit 2; }
done
[[ -d /run/systemd/system && -f "$SOURCE" && ! -L "$SOURCE" &&
    -f "$ROOT/plan.json" && -f "$ROOT/baseline.json" &&
    -f /var/lib/episcene-learning/knowledge.sqlite3 &&
    -d /opt/episcene-learning && ! -L "$ROOT" &&
    ! -L /opt/episcene-learning ]] || {
    echo "Bestehende EpiScene Installation oder Baseline fehlt; keine Aenderung." >&2
    exit 2
}
[[ "$(stat -c %u "$ROOT")" == 0 && "$(stat -c %a "$ROOT")" == 700 &&
   "$(stat -c %u /opt/episcene-learning)" == 0 &&
   ! -L "$ROOT/plan.json" && ! -L "$ROOT/baseline.json" &&
   ! -L "$ROOT/shadow.sqlite3" && ! -L "$TARGET" ]] || {
    echo "Referenzordner muss root gehoeren; kein root-Schreibzugriff in Nutzerordner." >&2
    exit 2
}
for name in reference_engine.py test_reference_engine.py; do
    curl --fail --silent --show-error --location --retry 2 --max-time 45 \
       "$BASE/$name" -o "$TMP/$name"
done
printf '%s  %s\n' "$CODE_SHA" "$TMP/reference_engine.py" | sha256sum --check
printf '%s  %s\n' "$TEST_SHA" "$TMP/test_reference_engine.py" | sha256sum --check
echo "=== Tests gegen separate SQLite-Testdatenbank ==="
(cd "$TMP" && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -q test_reference_engine)
echo "=== Live-Referenzlauf VOR Installation (Originaldatenbank nur lesen) ==="
python3 "$TMP/reference_engine.py" --dest "$TMP/check.sqlite3"
python3 - "$TMP/check.sqlite3" <<'PY_PREFLIGHT'
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
    count=db.execute('SELECT COUNT(*) FROM owner_attested_round40').fetchone()[0]
    verified=db.execute('SELECT COUNT(*) FROM owner_attested_round40 WHERE verified_backend<>0').fetchone()[0]
    published=db.execute('SELECT COUNT(*) FROM shadow_outro_models WHERE publish_allowed<>0').fetchone()[0]
if count < 60 or verified or published:
    raise SystemExit(f'PREFLIGHT STOP: {count} owner-attested rows; verified={verified}; released={published}. No installation.')
print(f'PREFLIGHT OK: {count} user-attested references, zero forged verification, zero publishing')
PY_PREFLIGHT
echo "=== Installation ==="
if [[ -e "$TARGET" || -L "$TARGET" ]]; then
    cmp -s "$TARGET" "$TMP/reference_engine.py" || {
        echo "Ein anderes Referenzmodul existiert schon. Kein Ueberschreiben." >&2; exit 2;
    }
else
    install -m 0644 -o root -g root "$TMP/reference_engine.py" "$TARGET"
fi
cat > "$TMP/$SERVICE.service" <<'SERVICE_UNIT'
[Unit]
Description=EpiScene owner-attested references and shadow-only credits proposals
After=local-fs.target
[Service]
Type=oneshot
User=root
Group=root
UMask=0077
ExecStart=/usr/bin/python3 /opt/episcene-learning/reference_engine.py
NoNewPrivileges=true
PrivateNetwork=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ReadWritePaths=/var/lib/episcene-learning/reference-round-40
TimeoutStartSec=120
SERVICE_UNIT
cat > "$TMP/$SERVICE.timer" <<'TIMER_UNIT'
[Unit]
Description=Hourly owner-attested EpiScene reference learning (shadow only)
[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Persistent=true
Unit=episcene-owner-learning-shadow.service
[Install]
WantedBy=timers.target
TIMER_UNIT
for ext in service timer; do
    unit="/etc/systemd/system/$SERVICE.$ext"
    if [[ -e "$unit" ]]; then
        cmp -s "$unit" "$TMP/$SERVICE.$ext" || {
            echo "Systemd Unit hat sich geaendert: $unit; keine Ueberschreibung." >&2;exit 2;
        }
    else
        install -m 0644 -o root -g root "$TMP/$SERVICE.$ext" "$unit"
    fi
done
systemctl daemon-reload
systemctl start "$SERVICE.service" || {
    systemctl status "$SERVICE.service" --no-pager --full || true
    exit 3
}
systemctl enable --now "$SERVICE.timer" >/dev/null
echo "=== SERVICE ==="
systemctl is-active "$SERVICE.timer"
echo "=== ECHTE SERVERERGEBNISSE (geschuetzte Schatten-Datenbank) ==="
python3 - <<'PY_STATUS'
import sqlite3
path='/var/lib/episcene-learning/reference-round-40/shadow.sqlite3'
with sqlite3.connect('file:'+path+'?mode=ro',uri=True) as db:
    for table in ('owner_attested_round40','shadow_outro_models','shadow_outro_candidates'):
        print(table,db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0])
    print('verified_backend',db.execute('SELECT SUM(verified_backend) FROM owner_attested_round40').fetchone()[0])
    for row in db.execute('SELECT series,season,playlist_id,shift_ms,reference_episodes,leave_one_out_mae_ms FROM shadow_outro_models ORDER BY series'):
        print('MODEL',row)
print('INSTALL OK: Stundenweises Lernen und Abspann-Kandidaten NUR in Schatten-Datenbank; keine Kundenfreigaben.')
PY_STATUS
