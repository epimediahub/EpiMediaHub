#!/usr/bin/env python3
"""Opt-in installer for the VPN safety policy into a reconstructed v1.0.33 source.

Does not enable VPN, change player code, change Gradle, or publish an APK.
"""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"]).resolve(strict=True)
here = Path(__file__).resolve().parent
build = root / "app/build.gradle.kts"
if not build.is_file() or 'versionName = "1.0.33"' not in build.read_text():
    raise SystemExit("Refusing: expected Android 1.0.33 source")
pairs = [
    (here / "V134VpnRoutingPolicy.kt",
     root / "app/src/main/java/de/epimediahub/app/vpn/V134VpnRoutingPolicy.kt"),
    (here / "V134VpnRoutingPolicyTest.kt",
     root / "app/src/test/java/de/epimediahub/app/vpn/V134VpnRoutingPolicyTest.kt"),
]
# Preflight everything before writing.
for src, dst in pairs:
    data = src.read_bytes()
    if dst.exists() and dst.read_bytes() != data:
        raise SystemExit(f"Refusing to overwrite modified VPN file: {dst}")
for src, dst in pairs:
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
print("VPN safety policy copied into Android source; VPN remains disabled")
