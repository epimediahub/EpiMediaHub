#!/usr/bin/env bash
set -euo pipefail

BASE="/opt/epimediahub/provisioning"
PY="$BASE/.venv/bin/python"
DETECTOR="$BASE/skip_detector_v3.py"
SOURCE_COMMIT="f9017ffaf7f84a58888895e4c975083e42464004"
RAW="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$SOURCE_COMMIT/server/epimediahub_provisioning"
DETECTOR_INSTALL_COMMIT="740b6d4886a4a2bf4e0ba554b55b24defafa8771"
STAMP="$(date +%Y%m%d-%H%M%S)"
TMP="$(mktemp -d /tmp/epimediahub-v3-worker.XXXXXX)"
BACKUP="$BASE/backups/skip-v3-$STAMP"
INSTALLED=0

cleanup() { rm -rf "$TMP"; }
rollback() {
  rc=$?
  if [ "$INSTALLED" = "1" ] && [ -d "$BACKUP" ]; then
    echo
    echo "FEHLER: Integration fehlgeschlagen – stelle Backup wieder her."
    for f in skip_automation.py skip_release.py skip_markers.py; do
      [ -f "$BACKUP/$f" ] && cp -a "$BACKUP/$f" "$BASE/$f"
    done
    systemctl restart epimediahub-provisioning.service 2>/dev/null || true
  fi
  cleanup
  exit "$rc"
}
trap rollback ERR
trap cleanup EXIT

if [ ! -x "$PY" ]; then
  echo "FEHLER: Python-Venv nicht gefunden: $PY" >&2
  exit 1
fi

echo "=== 1/7 V3.1 Detector prüfen ==="
if [ ! -f "$DETECTOR" ] || ! "$PY" "$DETECTOR" --selftest >/dev/null 2>&1; then
  echo "V3.1 fehlt oder Selbsttest fehlgeschlagen – installiere Detector automatisch."
  curl -fsSL "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$DETECTOR_INSTALL_COMMIT/server/epimediahub_provisioning/deploy/install_skip_detector_v3_1.sh"     -o "$TMP/install_detector.sh"
  bash "$TMP/install_detector.sh"
fi
"$PY" "$DETECTOR" --selftest

echo
echo "=== 2/7 Integrationsdateien laden ==="
for f in skip_automation.py skip_release.py skip_markers.py; do
  curl -fsSL "$RAW/$f" -o "$TMP/$f"
  echo "geladen: $f"
done

echo
echo "=== 3/7 Syntaxprüfung ==="
"$PY" -m py_compile "$DETECTOR" "$TMP/skip_automation.py" "$TMP/skip_release.py" "$TMP/skip_markers.py"

echo
echo "=== 4/7 Backup + Installation ==="
mkdir -p "$BACKUP"
for f in skip_automation.py skip_release.py skip_markers.py; do
  cp -a "$BASE/$f" "$BACKUP/$f"
  install -o root -g root -m 0644 "$TMP/$f" "$BASE/$f"
done
INSTALLED=1
echo "Backup: $BACKUP"

echo
echo "=== 5/7 Import-/Policy-Test ==="
cd "$BASE"
"$PY" - <<'PY'
import skip_detector_v3
import skip_automation
import skip_release
assert skip_automation.DETECTOR_POLICY == "chromaprint_fft_v3_1"
assert hasattr(skip_detector_v3, "detect")
print("IMPORT OK")
print("Detector-Policy:", skip_automation.DETECTOR_POLICY)
PY

echo
echo "=== 6/7 Dienste neu laden ==="
if systemctl is-active --quiet epimediahub-provisioning.service; then
  systemctl restart epimediahub-provisioning.service
fi
systemctl start epimediahub-skip-analysis.timer
# Ein sofortiger bounded Lauf; bei bereits laufendem Job ist das unkritisch.
systemctl start epimediahub-skip-analysis.service || true

echo
echo "=== 7/7 Status ==="
systemctl --no-pager --full status epimediahub-skip-analysis.timer | sed -n '1,12p' || true
echo
curl -fsS http://127.0.0.1:8787/health || true
echo
journalctl -u epimediahub-skip-analysis.service -n 12 --no-pager || true

echo
echo "V3.1 ist jetzt in den bestehenden EpiMediaHub-Worker integriert."
echo "Vorhandene manuelle Marker bleiben geschützt; AUTO_CONFIRMED benötigt reproduzierbare V3.1-Evidenz."
echo "Rollback-Backup: $BACKUP"
