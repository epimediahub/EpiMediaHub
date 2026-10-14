#!/usr/bin/env bash
# EpiScene visual shadow pilot: one 40-second fingerprint window per run.
set -Eeuo pipefail
umask 077
[[ "$EUID" == 0 ]] || { echo "Nur auf der bestehenden Root-Konsole ausfuehren" >&2;exit 2; }
ROOT=/var/lib/episcene-learning/reference-round-40
BASE=/opt/epimediahub/provisioning
TARGET=/opt/episcene-learning/visual_shadow_capture.py
UNIT=episcene-visual-shadow-capture
REV=c91360fa10e8820f5b4dcca0978b42280b8ada8b
URL="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$REV/tools/episcene-learning-v1/active-shadow"
SCRIPT_SHA=1ffab13363a754175d8db0695c26671f57ce1471453826f1dd7e7d94bccb9973
TEST_SHA=d27f34301d517c0525cf3c5e8c55ff2734042fb77342b41e9f9d45508dc67669
TMP="$(mktemp -d -t episcene-shadow-visual.XXXXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
for tool in curl sha256sum install python3 systemctl cmp stat;do
  command -v "$tool" >/dev/null || { echo "Programm fehlt: $tool" >&2;exit 2; }
done
[[ -d /run/systemd/system && -d "$ROOT" && -f "$ROOT/shadow.sqlite3" &&
    -f "$ROOT/plan.json" && -f "$ROOT/baseline.json" &&
    -f /var/lib/epimediahub/provisioning.db &&
    ! -L "$ROOT" && ! -L "$TARGET" &&
    -f "$BASE/.venv/bin/python" &&
    -f "$BASE/skip_analysis.py" && -f "$BASE/skip_remote_client.py" &&
    -f "$BASE/skip_analysis_worker.py" && -f "$BASE/skip_scene_reliability.py" ]] || {
  echo "Produktiver EpiScene-Analyzer / Shadow-Basis fehlt. Kein Eingriff." >&2;exit 2;
}
[[ "$(stat -c '%u:%a' "$ROOT")" == "0:700" ]] || {
  echo "Nur der geschuetzte Root-Ordner ist erlaubt." >&2;exit 2;
}
for filename in visual_shadow_capture.py test_visual_shadow_capture.py;do
  curl -fsSL --retry 2 --max-time 45 "$URL/$filename" -o "$TMP/$filename"
done
echo "$SCRIPT_SHA  $TMP/visual_shadow_capture.py" | sha256sum -c -
echo "$TEST_SHA  $TMP/test_visual_shadow_capture.py" | sha256sum -c -
echo "=== Isolierte Tests: DB nur lesend, genau ein Bildfenster pro Durchlauf ==="
(cd "$TMP" && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -q test_visual_shadow_capture)
echo "=== Produktivdaten nur lesen: Quelle und bestehende Shadow-Kandidaten pruefen ==="
python3 - "$ROOT/shadow.sqlite3" <<'PREFLIGHT'
import sqlite3,sys
with sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True) as db:
    models=db.execute('SELECT COUNT(*) FROM shadow_outro_models WHERE series=? AND season=1 AND playlist_id=8 AND status=? AND publish_allowed=0',('mobland','shadow_only')).fetchone()[0]
    examples=db.execute('SELECT COUNT(*) FROM owner_attested_round40 WHERE title=? AND kind=? AND season=1 AND playlist_id=8',('mobland','outro')).fetchone()[0]
    proposals=db.execute('SELECT COUNT(*) FROM shadow_outro_candidates WHERE series=? AND status=?',('mobland','SHADOW_REVIEW_ONLY')).fetchone()[0]
if (models,examples,proposals)!=(1,5,4):
    raise SystemExit(f'ABBRUCH: Erwartet 1 Modell/5 Referenzen/4 Vorschlaege, vorhanden: {models}/{examples}/{proposals}')
print('PREFLIGHT OK: 1 Modell, 5 Referenzen, 4 Vorschlaege')
PREFLIGHT
echo "=== Installiere separaten Visual-Shadow-Dienst ==="
if [[ -e "$TARGET" ]];then
  cmp -s "$TARGET" "$TMP/visual_shadow_capture.py" || {
    echo "Andere Version bereits installiert, bitte nicht ueberschreiben." >&2;exit 2;
  }
else
  install -m 0644 -o root -g root "$TMP/visual_shadow_capture.py" "$TARGET"
fi
cat > "$TMP/$UNIT.service" <<'SERVICE'
[Unit]
Description=EpiScene bounded owner-reference visual fingerprint sampling (shadow only)
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
User=root
Group=root
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/epimediahub/provisioning/.venv/bin/python /opt/episcene-learning/visual_shadow_capture.py
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ReadWritePaths=/var/lib/episcene-learning/reference-round-40
TimeoutStartSec=240
SERVICE
cat > "$TMP/$UNIT.timer" <<'TIMER'
[Unit]
Description=Retry up to one 40-second EpiScene visual reference window every 20 minutes
[Timer]
OnBootSec=8min
OnUnitInactiveSec=20min
Unit=episcene-visual-shadow-capture.service
[Install]
WantedBy=timers.target
TIMER
for ext in service timer;do
  dest="/etc/systemd/system/$UNIT.$ext"
  if [[ -e "$dest" ]];then
    cmp -s "$dest" "$TMP/$UNIT.$ext" || {
      echo "Ein anderer Dienst mit gleichem Namen existiert. Kein Ueberschreiben." >&2;exit 2;
    }
  else
    install -m 0644 -o root -g root "$TMP/$UNIT.$ext" "$dest"
  fi
done
systemctl daemon-reload
systemctl enable --now "$UNIT.timer" >/dev/null
systemctl start --no-block "$UNIT.service"
echo "=== STATUS ==="
systemctl is-active "$UNIT.timer"
echo "INSTALL OK: Visual-Sampling gestartet; maximal ein 40s-Ausschnitt je Lauf."
echo "Keine Produktionsmarker/Freigaben veraendert."
echo "Aktuelle Ergebnisse spaeter mit: journalctl -u $UNIT.service -n 25 --no-pager"
