"""Private signed Android Admin updates served only to authenticated admins.

The update file and manifest are not public repo assets. This module never
writes them. A publisher must first verify a release-signed APK and atomically
place it in the protected admin-mobile releases directory.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat

MAX_APK_BYTES = 100 * 1024 * 1024
PACKAGE = "de.epimediahub.admin"
SHA = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^[A-Za-z0-9._-]{1,48}$")


@dataclass(frozen=True)
class Release:
    version_code: int
    version_name: str
    sha256: str
    size_bytes: int
    path: Path


def _private(path: Path, *, expect_dir: bool = False) -> bool:
    if path.is_symlink():
        return False
    try:
        st = path.stat()
    except FileNotFoundError:
        return False
    if st.st_mode & 0o077:
        return False
    if st.st_uid != os.geteuid():
        return False
    return stat.S_ISDIR(st.st_mode) if expect_dir else stat.S_ISREG(st.st_mode)


def read_release(data_directory: Path) -> Release | None:
    root = Path(data_directory)
    if root.is_symlink() or not root.is_dir():
        raise PermissionError("Unsafe admin data directory")
    private = root / "admin-mobile"
    release_dir = private / "releases"
    if not release_dir.exists():
        return None
    if not _private(private, expect_dir=True) or not _private(release_dir, expect_dir=True):
        raise PermissionError("Unsafe release directory")
    manifest = release_dir / "current.json"
    apk = release_dir / "current.apk"
    if not manifest.exists() or not apk.exists():
        return None
    if not _private(manifest) or not _private(apk):
        raise PermissionError("Unsafe update file")
    if manifest.stat().st_size > 4096:
        raise ValueError("Oversized update manifest")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or
        set(data) != {"package", "version_code", "version_name", "sha256", "size_bytes"} or
        data["package"] != PACKAGE or
        type(data["version_code"]) is not int or not 1 <= data["version_code"] < 2**31 or
        not isinstance(data["version_name"], str) or
        not VERSION.fullmatch(data["version_name"]) or
        not isinstance(data["sha256"], str) or
        not SHA.fullmatch(data["sha256"]) or
        type(data["size_bytes"]) is not int or
        not 1024 <= data["size_bytes"] <= MAX_APK_BYTES):
        raise ValueError("Invalid private update manifest")
    st = apk.stat()
    if st.st_size != data["size_bytes"]:
        raise ValueError("Update APK length mismatch")
    h = hashlib.sha256()
    with apk.open("rb") as binary:
        for chunk in iter(lambda: binary.read(256 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != data["sha256"]:
        raise ValueError("Update APK digest mismatch")
    return Release(data["version_code"], data["version_name"],
                   data["sha256"], data["size_bytes"], apk)
