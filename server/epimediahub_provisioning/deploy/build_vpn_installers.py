#!/usr/bin/env python3
"""Build deterministic, self-contained installers; no moving-branch downloads."""
import base64
import gzip
import hashlib
import io
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]
COMMON="""#!/usr/bin/env bash
set -euo pipefail
umask 0077
if [ "$(id -u)" != 0 ]; then echo 'Bitte mit sudo ausführen.' >&2; exit 1; fi
TASK=$(mktemp -d /tmp/epi-vpn-install.XXXXXX)
trap 'rm -rf "$TASK"' EXIT
base64 --decode > "$TASK/payload.tar.gz" <<'EPIMEDIAHUB_PAYLOAD'
{payload}
EPIMEDIAHUB_PAYLOAD
echo '{digest}  '"$TASK/payload.tar.gz" | sha256sum --check --status
tar -xzf "$TASK/payload.tar.gz" -C "$TASK"
{run}
"""


def build(files,target,run):
    data=io.BytesIO()
    with tarfile.open(fileobj=data,mode="w") as archive:
        for name in sorted(files):
            body=(ROOT/name).read_bytes()
            info=tarfile.TarInfo(name);info.size=len(body);info.mode=0o644;info.mtime=0
            archive.addfile(info,io.BytesIO(body))
    raw=gzip.compress(data.getvalue(),mtime=0)
    text=COMMON.format(payload=base64.encodebytes(raw).decode().strip(),digest=hashlib.sha256(raw).hexdigest(),run=run)
    (ROOT/"deploy"/target).write_text(text)


def main():
    build(["vpn_dashboard.py","templates/vpn_dashboard.html","static/vpn-dashboard.css","static/vpn-dashboard.js","deploy/install_vpn_dashboard.py"],"install_vpn_dashboard.sh",'BASE="${EPIMEDIAHUB_APP_DIR:-/opt/epimediahub/provisioning}"\n"$BASE/.venv/bin/python" "$TASK/deploy/install_vpn_dashboard.py" --source "$TASK" --base "$BASE" --env "${EPIMEDIAHUB_ENV_FILE:-/etc/epimediahub/provisioning.env}"')
    build(["vpn_finland_agent.py","deploy/install_vpn_agent.py"],"install_vpn_finland_agent.sh",'python3 "$TASK/deploy/install_vpn_agent.py"')


if __name__=="__main__":main()
