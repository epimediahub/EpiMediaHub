#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY = os.environ.get("EPIMEDIAHUB_RELEASE_REPO", "epimediahub/EpiMediaHub")
DOWNLOAD_DIR = Path(os.environ.get("EPIMEDIAHUB_DOWNLOAD_DIR", "/srv/epimediahub-downloads/android"))
STATUS_PATH = Path(os.environ.get("EPIMEDIAHUB_SYNC_STATUS", str(DOWNLOAD_DIR / "sync-status.json")))
RELEASES_API = os.environ.get(
    "EPIMEDIAHUB_RELEASES_API",
    f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=20",
)
USER_AGENT = "EpiMediaHub-Pi-Release-Sync/1.0"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def request_bytes(url: str, timeout: int = 90) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json, application/json;q=0.9, */*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def write_atomic(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_status(**values) -> None:
    payload = {
        "service": "epimediahub-android-release-sync",
        "checkedAt": utc_iso(),
        **values,
    }
    write_atomic(STATUS_PATH, (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode())


def find_release() -> tuple[dict, dict]:
    releases = json.loads(request_bytes(RELEASES_API))
    if not isinstance(releases, list):
        raise RuntimeError("GitHub release API returned no release list")

    for release in releases:
        assets = release.get("assets") or []
        by_name = {str(asset.get("name") or ""): asset for asset in assets}
        manifest_asset = by_name.get("android-latest.json") or by_name.get("latest.json")
        if manifest_asset and manifest_asset.get("browser_download_url"):
            return release, manifest_asset
    raise RuntimeError("No GitHub release with android-latest.json was found")


def safe_asset_name(url: str) -> str:
    name = Path(urllib.parse.urlparse(url).path).name
    if not name or name in {".", ".."} or not name.lower().endswith(".apk"):
        raise RuntimeError(f"Invalid APK asset name: {name!r}")
    return name


def download_verified(url: str, destination: Path, expected_sha: str, expected_size: int | None) -> bool:
    expected_sha = expected_sha.lower().strip()
    if destination.exists():
        size_ok = expected_size is None or destination.stat().st_size == expected_size
        if size_ok and sha256_file(destination) == expected_sha:
            return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".part", dir=str(destination.parent))
    tmp = Path(tmp_name)
    try:
        digest = hashlib.sha256()
        total = 0
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"})
        with urllib.request.urlopen(req, timeout=180) as response, os.fdopen(fd, "wb") as handle:
            fd = -1
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                digest.update(chunk)
                total += len(chunk)
            handle.flush()
            os.fsync(handle.fileno())

        if expected_size is not None and total != expected_size:
            raise RuntimeError(
                f"Size mismatch for {destination.name}: expected {expected_size}, received {total}"
            )
        actual_sha = digest.hexdigest()
        if actual_sha != expected_sha:
            raise RuntimeError(
                f"SHA-256 mismatch for {destination.name}: expected {expected_sha}, received {actual_sha}"
            )

        os.chmod(tmp, 0o644)
        os.replace(tmp, destination)
        return True
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    previous_version = None
    local_manifest = DOWNLOAD_DIR / "latest.json"
    try:
        if local_manifest.exists():
            previous_version = json.loads(local_manifest.read_text(encoding="utf-8")).get("version")
    except Exception:
        previous_version = None

    try:
        release, manifest_asset = find_release()
        manifest_raw = request_bytes(str(manifest_asset["browser_download_url"]))
        manifest = json.loads(manifest_raw)
        version = str(manifest.get("version") or "").strip()
        version_code = int(manifest.get("versionCode") or 0)
        apks = manifest.get("apks")
        if not version or version_code <= 0 or not isinstance(apks, dict) or "universal" not in apks:
            raise RuntimeError("Android release manifest is incomplete")

        release_assets = {
            str(asset.get("name") or ""): asset
            for asset in (release.get("assets") or [])
            if asset.get("browser_download_url")
        }

        synced_files = []
        changed_files = []
        universal_path = None
        for abi, entry in apks.items():
            if not isinstance(entry, dict):
                continue
            source_url = str(entry.get("url") or "")
            expected_sha = str(entry.get("sha256") or "").lower().strip()
            expected_size_raw = entry.get("size")
            expected_size = int(expected_size_raw) if expected_size_raw not in (None, "") else None
            if len(expected_sha) != 64:
                raise RuntimeError(f"Missing/invalid SHA-256 for {abi}")

            filename = safe_asset_name(source_url)
            asset = release_assets.get(filename)
            if not asset:
                raise RuntimeError(f"Release asset is missing: {filename}")

            destination = DOWNLOAD_DIR / filename
            changed = download_verified(
                str(asset["browser_download_url"]),
                destination,
                expected_sha,
                expected_size,
            )
            synced_files.append(filename)
            if changed:
                changed_files.append(filename)
            if abi == "universal":
                universal_path = destination

        if universal_path and universal_path.exists():
            legacy_alias = DOWNLOAD_DIR / "EpiMediaHub_Android_v0.7.0-test.apk"
            if not legacy_alias.exists() or sha256_file(legacy_alias) != sha256_file(universal_path):
                tmp_alias = DOWNLOAD_DIR / f".{legacy_alias.name}.new"
                shutil.copyfile(universal_path, tmp_alias)
                os.chmod(tmp_alias, 0o644)
                os.replace(tmp_alias, legacy_alias)
                changed_files.append(legacy_alias.name)

        normalized_manifest = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
        write_atomic(DOWNLOAD_DIR / "android-latest.json", normalized_manifest)
        write_atomic(DOWNLOAD_DIR / "latest.json", normalized_manifest)

        write_status(
            state="synced",
            version=version,
            versionCode=version_code,
            previousVersion=previous_version,
            releaseTag=release.get("tag_name"),
            releaseName=release.get("name"),
            syncedAt=utc_iso(),
            changed=bool(changed_files),
            changedFiles=changed_files,
            files=synced_files,
        )
        print(
            f"EpiMediaHub Android sync OK: v{version} (code {version_code}); "
            f"{len(changed_files)} file(s) changed"
        )
        return 0
    except Exception as exc:
        write_status(
            state="error",
            previousVersion=previous_version,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
