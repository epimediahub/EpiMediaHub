#!/usr/bin/env python3
"""Rebuild the pinned, single-file credit installer from checked-in sources.

Run from the repository root. Deterministic zlib package; hash covers the entire
JSON payload. A CI check will fail if the embedded distribution is stale.
"""
from __future__ import annotations
import base64
import hashlib
import json
import re
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "server" / "epimediahub_provisioning"
INSTALLER = SOURCE / "deploy" / "install_credits_v120.py"
ASSETS = ("license_api.py", "templates/credits_v120.html", "templates/reseller_credits_v120.html")


def build():
    assets = {name: (SOURCE / name).read_text(encoding="utf-8") for name in ASSETS}
    plain = json.dumps(assets, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    encoded = base64.b64encode(zlib.compress(plain, level=9)).decode("ascii")
    digest = hashlib.sha256(plain).hexdigest()
    source = INSTALLER.read_text(encoding="utf-8")
    new, n1 = re.subn(r"(?m)^PAYLOAD_B64 = '[^']+'$", lambda _: "PAYLOAD_B64 = '" + encoded + "'", source)
    new, n2 = re.subn(r"(?m)^PAYLOAD_SHA256 = '[0-9a-f]{64}'$", "PAYLOAD_SHA256 = '" + digest + "'", new)
    if (n1, n2) != (1, 1):
        raise RuntimeError("Installer payload anchors no longer match")
    INSTALLER.write_text(new, encoding="utf-8")
    print("Bundled credit installer matches current license sources; digest:", digest)


if __name__ == "__main__":
    build()
