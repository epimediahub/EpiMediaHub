#!/usr/bin/env bash
set -Eeuo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Bitte als root starten: sudo bash upgrade_to_v052.sh" >&2
  exit 1
fi

BRANCH="${EPIMEDIAHUB_UPGRADE_BRANCH:-raspberry-v0.5.2-dashboard}"
TARGET_VERSION="${EPIMEDIAHUB_TARGET_VERSION:-0.5.2}"
DASHBOARD_MODULE="${EPIMEDIAHUB_DASHBOARD_MODULE:-dashboard_v052.py}"
SMOKE_TEST="${EPIMEDIAHUB_SMOKE_TEST:-tests/smoke_v052.py}"
REPO="https://github.com/epimediahub/EpiMediaHub.git"
APP_DIR=/opt/epimediahub/provisioning
DATA_DIR=/var/lib/epimediahub
DB="$DATA_DIR/provisioning.db"
ENV_FILE=/etc/epimediahub/provisioning.env
SERVICE=epimediahub-provisioning.service
STAMP="$(date +%Y%m%d-%H%M%S)"
VERSION_SLUG="$(printf '%s' "$TARGET_VERSION" | tr -d '.')"
BACKUP_DIR="/var/backups/epimediahub/v${VERSION_SLUG}-$STAMP"
mkdir -p /var/tmp
TMP="$(mktemp -d -p /var/tmp epimediahub-upgrade.XXXXXX)"
ROLLBACK_ARMED=0

cleanup() { rm -rf "$TMP"; }
rollback() {
  rc=$?
  if [ "$ROLLBACK_ARMED" -eq 1 ]; then
    echo
    echo "Upgrade fehlgeschlagen - stelle vorherigen Stand wieder her ..." >&2
    systemctl stop "$SERVICE" 2>/dev/null || true
    if [ -d "$BACKUP_DIR/code" ]; then
      rsync -a --delete --exclude '.venv' "$BACKUP_DIR/code/" "$APP_DIR/" || true
    fi
    if [ -f "$BACKUP_DIR/provisioning.db" ]; then
      cp -f "$BACKUP_DIR/provisioning.db" "$DB" || true
      chown epimediahub:epimediahub "$DB" || true
      chmod 640 "$DB" || true
    fi
    systemctl start "$SERVICE" 2>/dev/null || true
    echo "Rollback abgeschlossen. Backup: $BACKUP_DIR" >&2
  fi
  cleanup
  exit "$rc"
}
trap rollback ERR
trap cleanup EXIT

apt-get update
apt-get install -y git rsync python3 python3-venv python3-pip curl ca-certificates

git clone --depth 1 --branch "$BRANCH" "$REPO" "$TMP/repo"
SRC="$TMP/repo/server/epimediahub_provisioning"
test -f "$SRC/app.py"
test -f "$SRC/wsgi.py"
test -f "$SRC/$DASHBOARD_MODULE"
test -f "$SRC/$SMOKE_TEST"

echo "Erstelle Sicherheitskopie in $BACKUP_DIR"
mkdir -p "$BACKUP_DIR/code"
rsync -a --exclude '.venv' "$APP_DIR/" "$BACKUP_DIR/code/"
[ -f "$ENV_FILE" ] && cp -a "$ENV_FILE" "$BACKUP_DIR/provisioning.env"

systemctl stop "$SERVICE"
ROLLBACK_ARMED=1

python3 - "$DB" "$BACKUP_DIR/provisioning.db" <<'PY'
import sqlite3, sys
src_path, dst_path = sys.argv[1:3]
src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
dst = sqlite3.connect(dst_path)
src.backup(dst)
check = dst.execute("PRAGMA integrity_check").fetchone()[0]
dst.close(); src.close()
if check != "ok":
    raise SystemExit("DB-Backup Integritaetspruefung fehlgeschlagen: " + str(check))
PY

# Nur Anwendungscode ersetzen. Datenbank, Secrets, Cloudflare und Tailscale bleiben unberuehrt.
rsync -a --delete --exclude 'deploy' --exclude '.venv' "$SRC/" "$APP_DIR/"

if [ ! -x "$APP_DIR/.venv/bin/pip" ]; then
  python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --upgrade pip >/dev/null
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" >/dev/null

chown -R epimediahub:epimediahub "$APP_DIR" "$DATA_DIR"
chmod 640 "$DB"

# Vor dem Neustart Syntax und den isolierten Dashboard-Smoke-Test pruefen.
"$APP_DIR/.venv/bin/python" -m py_compile \
  "$APP_DIR/app.py" \
  "$APP_DIR/wsgi.py" \
  "$APP_DIR/receiver_sync.py" \
  "$APP_DIR/$DASHBOARD_MODULE"

(
  cd "$APP_DIR"
  EPIMEDIAHUB_EXPECTED_API_VERSION="$TARGET_VERSION" "$APP_DIR/.venv/bin/python" "$SMOKE_TEST"
)

systemctl start "$SERVICE"

ok=0
for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8787/health >"$TMP/health.json" 2>/dev/null; then
    ok=1
    break
  fi
  sleep 1
done
[ "$ok" -eq 1 ]

grep -q "\"api_version\":\"$TARGET_VERSION\"" "$TMP/health.json" || grep -q "\"api_version\": \"$TARGET_VERSION\"" "$TMP/health.json"

python3 - "$DB" <<'PY'
import sqlite3, sys
p=sys.argv[1]
con=sqlite3.connect(f"file:{p}?mode=ro", uri=True)
required={"customers","devices","activations","customer_config_history","customer_playlists"}
tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
missing=required-tables
if missing:
    raise SystemExit("Fehlende Tabellen: "+", ".join(sorted(missing)))
cc={r[1] for r in con.execute("PRAGMA table_info(customers)")}
dc={r[1] for r in con.execute("PRAGMA table_info(devices)")}
for col in ("config_version",):
    if col not in cc:
        raise SystemExit("Fehlende customer-Spalte: "+col)
for col in ("display_name","last_seen_at","applied_config_version","last_sync_at","last_sync_status","last_sync_error","sync_bootstrap_hash"):
    if col not in dc:
        raise SystemExit("Fehlende device-Spalte: "+col)
for table in ("customers","devices","activations"):
    print(f"{table}: {con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]}")
con.close()
PY

systemctl is-active --quiet "$SERVICE"
ROLLBACK_ARMED=0

echo
echo "=== EpiMediaHub Raspberry Upgrade auf v$TARGET_VERSION erfolgreich ==="
cat "$TMP/health.json"
echo
echo "Backup: $BACKUP_DIR"
echo "Cloudflare, Tailscale, Secrets und bestehende Daten wurden nicht veraendert."
