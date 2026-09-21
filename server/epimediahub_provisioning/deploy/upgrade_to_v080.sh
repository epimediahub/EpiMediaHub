#!/usr/bin/env bash
set -Eeuo pipefail

export EPIMEDIAHUB_UPGRADE_BRANCH="${EPIMEDIAHUB_UPGRADE_BRANCH:-raspberry-v0.7.0-customer-device-grid}"
export EPIMEDIAHUB_TARGET_VERSION="0.8.0"
export EPIMEDIAHUB_DASHBOARD_MODULE="dashboard_v080.py"
export EPIMEDIAHUB_SMOKE_TEST="tests/smoke_v080.py"

mkdir -p /var/tmp
export TMPDIR=/var/tmp
CORE_SCRIPT="$(mktemp -p /var/tmp epimediahub-core.XXXXXX)"
SYNC_SCRIPT="$(mktemp -p /var/tmp epimediahub-sync.XXXXXX)"
trap 'rm -f "$CORE_SCRIPT" "$SYNC_SCRIPT"' EXIT

CORE_REF="${EPIMEDIAHUB_CORE_REF:-9f9b64da18d0b76e9c28ea39725e9d95ca4ddbeb}"
RAW_CORE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/${CORE_REF}/server/epimediahub_provisioning/deploy"
RAW_BRANCH="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/${EPIMEDIAHUB_UPGRADE_BRANCH}/server/epimediahub_provisioning/deploy"

curl -fsSL "$RAW_CORE/upgrade_to_v052.sh" -o "$CORE_SCRIPT"
bash "$CORE_SCRIPT"

curl -fsSL "$RAW_BRANCH/install_android_release_sync.sh?nocache=$(date +%s)" -o "$SYNC_SCRIPT"
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
