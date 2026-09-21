#!/usr/bin/env bash
set -Eeuo pipefail

export EPIMEDIAHUB_UPGRADE_BRANCH="${EPIMEDIAHUB_UPGRADE_BRANCH:-raspberry-v0.7.0-customer-device-grid}"
export EPIMEDIAHUB_TARGET_VERSION="0.8.0"
export EPIMEDIAHUB_DASHBOARD_MODULE="dashboard_v080.py"
export EPIMEDIAHUB_SMOKE_TEST="tests/smoke_v080.py"

CORE_SCRIPT="$(mktemp)"
SYNC_SCRIPT="$(mktemp)"
trap 'rm -f "$CORE_SCRIPT" "$SYNC_SCRIPT"' EXIT
RAW="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/${EPIMEDIAHUB_UPGRADE_BRANCH}/server/epimediahub_provisioning/deploy"

curl -fsSL "$RAW/upgrade_to_v052.sh" -o "$CORE_SCRIPT"
bash "$CORE_SCRIPT"

curl -fsSL "$RAW/install_android_release_sync.sh" -o "$SYNC_SCRIPT"
bash "$SYNC_SCRIPT"

python3 - <<'PY'
import os
import sqlite3
from pathlib import Path
db = Path(os.environ.get("EPIMEDIAHUB_DATA_DIR", "/var/lib/epimediahub")) / "provisioning.db"
con = sqlite3.connect(db)
tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
for table in ("resellers", "audit_log"):
    if table not in tables:
        raise SystemExit("Fehlende Reseller-Tabelle: " + table)
cols = {r[1] for r in con.execute("PRAGMA table_info(customers)")}
if "reseller_id" not in cols:
    raise SystemExit("Fehlende customers.reseller_id Spalte")
con.close()
print("Reseller-Schema v0.8.0 validiert.")
PY

echo
echo "Dashboard v${EPIMEDIAHUB_TARGET_VERSION} mit Reseller-System und automatische Android-Release-Synchronisierung sind aktiv."
