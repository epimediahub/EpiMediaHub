#!/usr/bin/env bash
set -euo pipefail

BASE="/opt/epimediahub/provisioning"
PY="$BASE/.venv/bin/python"
TARGET="$BASE/skip_analysis_worker.py"
SOURCE_COMMIT="0cd6008184a0151eddd74e045699ff2a01d2b40a"
RAW="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$SOURCE_COMMIT/server/epimediahub_provisioning/skip_analysis_worker.py"
STAMP="$(date +%Y%m%d-%H%M%S)"
TMP="$(mktemp /tmp/skip_analysis_worker.XXXXXX.py)"
BACKUP="$TARGET.bak-language-$STAMP"
trap 'rm -f "$TMP"' EXIT

[ -x "$PY" ] || { echo "FEHLER: Python-Venv fehlt: $PY" >&2; exit 1; }
[ -f "$TARGET" ] || { echo "FEHLER: Worker fehlt: $TARGET" >&2; exit 1; }

echo "=== Worker laden ==="
curl -fsSL "$RAW" -o "$TMP"

echo "=== Syntax prüfen ==="
"$PY" -m py_compile "$TMP"

echo "=== Backup ==="
cp -a "$TARGET" "$BACKUP"
echo "$BACKUP"

echo "=== Installieren ==="
install -o root -g root -m 0644 "$TMP" "$TARGET"

echo "=== Analyse neu anstoßen ==="
systemctl start epimediahub-skip-analysis.timer
systemctl start epimediahub-skip-analysis.service || true

echo
echo "Sprachreihenfolge aktiv:"
echo "1) Deutsch + Italienisch vollständig"
echo "2) erst danach unbekannte/andere Sprachen"
echo
journalctl -u epimediahub-skip-analysis.service -n 8 --no-pager || true
