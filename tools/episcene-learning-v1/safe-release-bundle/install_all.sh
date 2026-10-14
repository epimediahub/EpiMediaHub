#!/usr/bin/env bash
# EpiScene ONE STEP: guarded old-manual reconciliation + normal evidence release
# checks + bounded visual requeue + recurring feedback learning.
set -Eeuo pipefail
umask 077

[[ "$EUID" -eq 0 ]] || { echo "STOP: Root erforderlich";exit 2; }
REV=7d019c66041f92d3234ff7a4feb0cea2b7ffcf5e
BASE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$REV/tools/episcene-learning-v1/safe-release-bundle"
VENV=/opt/epimediahub/provisioning/.venv/bin/python
SRC=/var/lib/epimediahub/provisioning.db
LEARN=/var/lib/episcene-learning/reference-round-40
CODE=/opt/episcene-learning
UNIT=episcene-safe-release-learning
BACKUP=/var/lib/epimediahub/episcene-safe-release-backups
TMP="$(mktemp -d -t episcene-release-learning.XXXXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT

for program in curl sha256sum python3 install cmp systemctl stat;do
  command -v "$program" >/dev/null || { echo "STOP: fehlt $program";exit 2; }
done
[[ -d /run/systemd/system && -x "$VENV" && -f "$SRC" && ! -L "$SRC" &&
   -d "$CODE" && ! -L "$CODE" && -d "$LEARN" && ! -L "$LEARN" &&
   "$(stat -c '%u:%a' "$LEARN")" == "0:700" &&
   -f /opt/epimediahub/provisioning/skip_markers.py &&
   -f /opt/epimediahub/provisioning/skip_release.py ]] || {
   echo "STOP: Erwartete EpiScene-Installation fehlt oder Lernbereich ist nicht privat.";exit 2;
}
if ! grep -q 'verified_manual_submission(con, raw, data, row)' \
   /opt/epimediahub/provisioning/skip_markers.py;then
   echo "STOP: Sofort-Freigabe manueller Markierungen fehlt. Keine Aenderung.";exit 2
fi

fetch() {
  local filename="$1" digest="$2"
  curl -fsSL --retry 2 --max-time 45 "$BASE/$filename" -o "$TMP/$filename"
  printf '%s  %s\n' "$digest" "$TMP/$filename" | sha256sum --check
}
fetch safe_release_rollout.py 435a2e81fda3f430093e79118ad7f0df0ade359ea0cc48bb533f105f22dd07e7
fetch feedback_learning.py 20a58ca53d52efc8708f748afb1e94090673b1e6e17bd28a7457d4fe77c4bf85
fetch test_safe_release_rollout.py a16afa2547c80bcdde7c6fa5f77a9f85f5ec39e1158c3543f84599f5d0dfef21
fetch test_feedback_learning.py 50ca13be5ebec06a9cf1daba58c338adac80b05a4232d04acf8353a3a0c6c800

echo '=== Isolierte Tests (nur temporaere SQLite-Testdaten) ==='
(cd "$TMP" && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -q test_safe_release_rollout test_feedback_learning)
echo '=== Live-Vorschau (originale Produktionsdatenbank NUR LESEN) ==='
(cd "$TMP" && PYTHONDONTWRITEBYTECODE=1 "$VENV" safe_release_rollout.py --check)

# Fail closed if the current controller code already has unexpected scripts.
for filename in safe_release_rollout.py feedback_learning.py; do
  if [[ -L "$CODE/$filename" ]];then
    echo "STOP: Unerwarteter Symlink im Code-Verzeichnis.";exit 2
  fi
  if [[ -e "$CODE/$filename" ]] && ! cmp -s "$TMP/$filename" "$CODE/$filename";then
    echo "STOP: Bereits installierte unbekannte Version von $filename.";exit 2
  fi
done
if [[ -L "$BACKUP" ]];then
   echo 'STOP: Unerwarteter Backup-Symlink';exit 2
fi
install -d -m 0700 -o root -g root "$BACKUP"
if [[ "$(stat -c %u "$BACKUP")" != "0" ]];then
   echo "STOP: Backup-Verzeichnis muss Root gehoeren.";exit 2
fi

echo '=== Sichere SQLite-Sicherung vor produktiven Entscheidungen ==='
BACKUP_FILE="$(mktemp "$BACKUP/provisioning-before-safe-release.XXXXXXXX.sqlite3")"
python3 - "$SRC" "$BACKUP_FILE" <<'PY_BACKUP'
import sqlite3,sys
src,dst=sys.argv[1:]
with sqlite3.connect('file:'+src+'?mode=ro',uri=True) as inp:
    with sqlite3.connect(dst) as out:
        inp.backup(out)
        if out.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise RuntimeError('Backup integrity failure')
print('BACKUP OK')
PY_BACKUP
chmod 0600 "$BACKUP_FILE"

echo '=== Zwei gepruefte Module installieren ==='
for filename in safe_release_rollout.py feedback_learning.py;do
  if [[ ! -e "$CODE/$filename" ]];then
    install -m 0644 -o root -g root "$TMP/$filename" "$CODE/$filename"
  fi
done

cat > "$TMP/$UNIT.service" <<'SERVICE_UNIT'
[Unit]
Description=EpiScene safe releases and authenticated continuous feedback learning
After=local-fs.target epimediahub-provisioning.service
Requires=epimediahub-provisioning.service

[Service]
Type=oneshot
User=root
Group=root
UMask=0077
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/epimediahub/provisioning/.venv/bin/python /opt/episcene-learning/safe_release_rollout.py --apply
NoNewPrivileges=true
PrivateTmp=true
PrivateNetwork=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ReadWritePaths=/var/lib/epimediahub /var/lib/episcene-learning/reference-round-40
TimeoutStartSec=240
SERVICE_UNIT

cat > "$TMP/$UNIT.timer" <<'TIMER_UNIT'
[Unit]
Description=Keep EpiScene learning from human corrections every hour
[Timer]
OnBootSec=15min
OnUnitInactiveSec=1h
Persistent=true
Unit=episcene-safe-release-learning.service
[Install]
WantedBy=timers.target
TIMER_UNIT

for ext in service timer;do
  dest="/etc/systemd/system/$UNIT.$ext"
  if [[ -L "$dest" ]];then echo "STOP: Unerwarteter Unit-Symlink";exit 2;fi
  if [[ -e "$dest" ]] && ! cmp -s "$dest" "$TMP/$UNIT.$ext";then
    echo "STOP: Service-Konfiguration unterscheidet sich. Keine Ueberschreibung.";exit 2
  fi
done
for ext in service timer;do
  dest="/etc/systemd/system/$UNIT.$ext"
  if [[ ! -e "$dest" ]];then
    install -m 0644 -o root -g root "$TMP/$UNIT.$ext" "$dest"
  fi
done

echo '=== Erste sichere Verarbeitung und Lernaktualisierung ==='
systemctl daemon-reload
systemctl start "$UNIT.service" || {
  systemctl status "$UNIT.service" --no-pager --full || true
  echo 'STOP: Rollout-Lauf fehlgeschlagen; keine weitere Automatik aktiviert.'
  exit 3
}
systemctl enable --now "$UNIT.timer" >/dev/null
echo '=== Laufstatus ==='
systemctl show "$UNIT.service" -p Result -p ExecMainStatus --no-pager
systemctl is-active "$UNIT.timer"
echo '=== Ergebnisse (ohne Kunden- oder Providerdaten) ==='
journalctl -u "$UNIT.service" -n 45 --no-pager -o cat || true
echo 'INSTALL OK: Eine Installation, bestehende Auto-Freigabepruefungen, stündliches Lernen.'
echo 'Vorherige manuelle Eintraege nur bei vollstaendig nachgewiesener Zuordnung bearbeitet.'
echo 'Original-Datenbank gesichert; Kunden-App und Player nicht geaendert.'
