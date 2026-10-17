#!/usr/bin/env python3
"""Atomically publish a CI-signed, SHA-256 pinned private Admin APK.

This script runs AS the non-root provisioning service owner. Release bundle
must come from the separate private GitHub Actions signing workflow; never
write to public web roots, GitHub release assets or the IPTV player updater.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

MAX_SIZE = 100 * 1024 * 1024
PACKAGE = "de.epimediahub.admin"
FILES = {"current.json", "current.apk"}


def verify_bundle(directory: Path):
    if directory.is_symlink() or not directory.is_dir():
        raise PermissionError("Invalid release staging directory")
    file = directory/"current.apk"
    manifest = directory/"current.json"
    for path in (file,manifest):
        if not path.is_file() or path.is_symlink():
            raise PermissionError("Bundle file missing or linked")
    if manifest.stat().st_size>4096:
        raise ValueError("Manifest too large")
    info=json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(info,dict) or set(info)!={
        "package","version_code","version_name","size_bytes","sha256"
    }:
        raise ValueError("Invalid manifest schema")
    if (info["package"]!=PACKAGE or type(info["version_code"]) is not int or
        info["version_code"]<=0 or type(info["size_bytes"]) is not int or
        not 1024<=info["size_bytes"]<=MAX_SIZE or
        not isinstance(info["version_name"],str) or
        not re.fullmatch(r"[A-Za-z0-9._-]{1,48}",info["version_name"]) or
        not isinstance(info["sha256"],str) or
        not re.fullmatch("[a-f0-9]{64}",info["sha256"]) or
        info["size_bytes"]!=file.stat().st_size):
        raise ValueError("Invalid manifest contents")
    digest=hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda:stream.read(512*1024),b""):
            digest.update(block)
    if digest.hexdigest()!=info["sha256"]:
        raise ValueError("Untrusted APK digest")
    return info


def publish(source:Path, admin_directory:Path):
    info=verify_bundle(source)
    if admin_directory.is_symlink() or not admin_directory.is_dir() or (
            admin_directory.stat().st_mode & 0o077) or (
            admin_directory.stat().st_uid != os.geteuid()):
        raise PermissionError("Private Admin data directory unsafe")
    target=admin_directory/"releases"
    target.mkdir(mode=0o700,exist_ok=True)
    if target.is_symlink() or target.stat().st_mode&0o077 or (
            target.stat().st_uid!=os.geteuid()):
        raise PermissionError("Release directory unsafe")
    current=target/"current.json"
    if current.exists():
        if current.is_symlink() or current.stat().st_mode & 0o077:
            raise PermissionError("Existing release manifest unsafe")
        old=json.loads(current.read_text(encoding="utf-8"))
        if type(old.get("version_code")) is not int or (
                info["version_code"]<=old["version_code"]):
            raise ValueError("Refusing downgrade or repeated release")
    for name in FILES:
        dest=target/name
        if dest.is_symlink():
            raise PermissionError("Existing update file symlink")
    apk_temp=target/(".admin-apk-"+str(os.getpid()))
    manifest_temp=target/(".admin-manifest-"+str(os.getpid()))
    try:
        with (source/"current.apk").open("rb") as src, apk_temp.open("xb") as dst:
            os.fchmod(dst.fileno(),0o600)
            shutil.copyfileobj(src,dst,512*1024)
            dst.flush();os.fsync(dst.fileno())
        # Verify the local copy as well as the original build artifact.
        if hashlib.sha256(apk_temp.read_bytes()).hexdigest()!=info["sha256"]:
            raise RuntimeError("Copied APK hash mismatch")
        with manifest_temp.open("x",encoding="utf-8") as dst:
            os.fchmod(dst.fileno(),0o600)
            json.dump(info,dst,separators=(",",":"),sort_keys=True)
            dst.flush();os.fsync(dst.fileno())
        os.replace(apk_temp,target/"current.apk")
        os.replace(manifest_temp,current)
    finally:
        apk_temp.unlink(missing_ok=True)
        manifest_temp.unlink(missing_ok=True)
    return {"mode":"PRIVATE_ADMIN_RELEASE_PUBLISHED",
            "version_code":info["version_code"],"version_name":info["version_name"],
            "apk_bytes":info["size_bytes"],"public_release":False}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--bundle",type=Path,required=True)
    parser.add_argument("--admin-dir",type=Path,
                        default=Path("/var/lib/epimediahub/admin-mobile"))
    args=parser.parse_args()
    print(json.dumps(publish(args.bundle,args.admin_dir),sort_keys=True))


if __name__=="__main__":
    main()
