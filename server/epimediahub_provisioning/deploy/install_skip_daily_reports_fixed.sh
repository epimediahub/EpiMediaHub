#!/usr/bin/env bash
# EpiScene daily reports -- corrected launcher for the October 8, 2026 installer.
# Fixes the invalid systemd WorkingDirectory quoting in the original embedded installer.
# Uses the original pinned payload and its SHA-256 guard, retaining its backup/rollback logic.
set -euo pipefail
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Bitte als root bzw. mit sudo ausfuehren." >&2
  exit 1
fi

original="$(mktemp /tmp/episcene-reports-original.XXXXXXXX.sh)"
trap 'rm -f "$original"' EXIT
curl -fsSL --retry 3 \
  "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/93fb42aa0d882801cac5596c1252c88a6e8a1917/server/epimediahub_provisioning/deploy/install_skip_daily_reports.sh" \
  -o "$original"

python3 - "$original" <<'EPISCENE_INSTALL_FIX'
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zlib

script = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r'encoded="""([\s\S]*?)"""', script)
if not match:
    raise SystemExit("Originales Installationspaket fehlt; keine Aenderungen vorgenommen.")
packed = base64.b64decode(match.group(1), validate=False)
expected = "08bfccc3829d6455e4d2d054f5ed31f9e7f9908038342b55f9cedf6634f0d6c2"
if hashlib.sha256(packed).hexdigest() != expected:
    raise SystemExit("Pruefsumme stimmt nicht; keine Aenderungen vorgenommen.")

bundle = json.loads(zlib.decompress(packed))
old = "WorkingDirectory={q(base)}"
new = "WorkingDirectory={base}"
if bundle["installer"].count(old) != 1:
    raise SystemExit("Unerwarteter Installer-Aufbau; keine Aenderungen vorgenommen.")
bundle["installer"] = bundle["installer"].replace(old, new, 1)

print("EpiScene Tagesberichte: systemd-WorkingDirectory korrigiert.")
print("Der Original-Installer erstellt ein Backup und fuehrt bei Fehlern einen Rollback aus.", flush=True)
exec(compile(bundle["installer"], "episcene-installer-corrected", "exec"))
try:
    main(bundle["files"])
except Exception as error:
    if isinstance(error, subprocess.CalledProcessError):
        print("Pruefung fehlgeschlagen:", error.stderr[-2500:] if error.stderr else str(error))
    else:
        print("Installation abgebrochen:", str(error))
    raise SystemExit(1)
EPISCENE_INSTALL_FIX
