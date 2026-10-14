#!/usr/bin/env python3
"""Install only the EpiScene manual-submit authorization fix, with rollback.

Scope: /opt/epimediahub/provisioning/skip_markers.py and its WEB service.
Do NOT migrate the SQLite database or alter pre-existing pending manual marks.
Original PR #78: https://github.com/epimediahub/EpiMediaHub/pull/78
"""
from __future__ import annotations

import argparse
import ast
import fcntl
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time

DIRECTORY = Path('/opt/epimediahub/provisioning')
TARGET = DIRECTORY / 'skip_markers.py'
WEB = 'epimediahub-provisioning.service'
BACKUP_ROOT = Path('/var/lib/epimediahub/manual-release-backups')

ORIGINAL = '''            from skip_release import enabled as release_enabled
            asset = con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (data['asset_key'],)).fetchone() if registered else None
            if (asset and release_enabled(con, asset['playlist_id']) and saved['status'] == 'pending'
                    and all(asset[key] == data[key] for key in ('source_key','media_type','season','episode','duration_ms'))):
                record = con.execute('SELECT * FROM skip_records WHERE id=?', (saved['id'],)).fetchone()
                review_record(con, record, 'approve', start, end, off)
                saved = dict(id=saved['id'], status='approved')
'''

REPLACEMENT = '''            # An authenticated manual action is a direct human instruction.
            # Do not require the automatic-machine-release toggle or a second
            # dashboard confirmation. Unverifiable file identities stay pending.
            if (saved['status'] == 'pending'
                    and verified_manual_submission(con, raw, data, row)):
                record = con.execute('SELECT * FROM skip_records WHERE id=?', (saved['id'],)).fetchone()
                review_record(con, record, 'approve', start, end, off)
                saved = dict(id=saved['id'], status='approved')
'''

ANCHOR = 'def add_record(con, data, kind, start, end, disabled, device=None, source="device", confidence=1.0):'

HELPER = '''def verified_manual_submission(con, raw, data, device):
    """Check an authenticated device owns the exact media provider identity.

    Unlike machine detections, a deliberate manual mark must not depend on
    the playlist's automatic-release or analysis toggles. No registration or
    learning privileges are fabricated for unverified provider inputs.
    """
    from skip_analysis import authorized_playlist, provider_asset_key, source_url
    playlist_id = raw.get("playlist_id")
    stream = raw.get("stream_id")
    extension = raw.get("extension")
    if (type(playlist_id) is not int or not isinstance(stream, str)
            or not re.fullmatch(r"[0-9]{1,12}", stream)
            or extension not in ("mp4", "mkv", "m4v", "avi", "ts", "mpeg", "mpg")):
        return False
    playlist = authorized_playlist(con, device, playlist_id)
    if playlist is None:
        return False
    try:
        actual = provider_asset_key(
            source_url(playlist, dict(data, stream_id=stream, extension=extension)),
            data["media_type"])
    except (ValueError, TypeError, KeyError):
        return False
    if actual != data["asset_key"]:
        return False
    known = con.execute("SELECT * FROM skip_assets WHERE asset_key=?",
                        (data["asset_key"],)).fetchone()
    if known and (known["playlist_id"] != playlist_id
                  or any(known[k] != data[k] for k in
                         ("source_key", "media_type", "season", "episode"))
                  or abs(known["duration_ms"] - data["duration_ms"]) > 2000):
        return False
    return True


'''


def patch(source: str) -> tuple[str, bool]:
    """Reject unexpected sources; never stack multiple approvals/patches."""
    if source.count(REPLACEMENT) == 1 and source.count(HELPER) == 1 and ORIGINAL not in source:
        ast.parse(source)
        return source, False
    if source.count(ORIGINAL) != 1 or source.count(ANCHOR) != 1 or HELPER in source or REPLACEMENT in source:
        raise RuntimeError('Unexpected deployed skip_markers revision. No file changed.')
    result = source.replace(ANCHOR, HELPER + ANCHOR).replace(ORIGINAL, REPLACEMENT)
    if result.count(HELPER) != 1 or result.count(REPLACEMENT) != 1:
        raise RuntimeError('Patch internal consistency failure')
    ast.parse(result)
    return result, True


def run(*args: str, timeout=60) -> subprocess.CompletedProcess:
    return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          check=True, timeout=timeout)


def live_service() -> bool:
    proc = subprocess.run(['systemctl', 'is-active', '--quiet', WEB],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          check=False, timeout=10)
    return proc.returncode == 0


def restart_and_check():
    run('systemctl', 'restart', WEB, timeout=60)
    # Verify service remains active, rather than merely accepting the restart exit code.
    for _ in range(4):
        time.sleep(1)
        if not live_service():
            raise RuntimeError('Provisioning service stopped after restart')


def install(path: Path = TARGET, backup_root: Path = BACKUP_ROOT, *,
            check=False, require_service=True):
    if os.geteuid() != 0:
        raise RuntimeError('Root required')
    if path.is_symlink() or not path.is_file() or path.parent.is_symlink():
        raise RuntimeError('Unexpected target or symlink; no change')
    if require_service and not live_service():
        raise RuntimeError('Provisioning service not active; no change')
    st = path.stat()
    if not stat.S_ISREG(st.st_mode):
        raise RuntimeError('Target must be regular file')
    original = path.read_bytes()
    try:
        source = original.decode('utf-8')
    except UnicodeDecodeError:
        raise RuntimeError('Unexpected source encoding')
    desired, changed = patch(source)
    if not changed:
        print('ALREADY INSTALLED: manual device submissions use independent immediate approval.')
        return False
    if check:
        print('CHECK OK: precise manual submit patch matches live code; no changes made.')
        return True

    if backup_root.is_symlink():
        raise RuntimeError('Unexpected backup root symlink')
    backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if backup_root.stat().st_uid != 0:
        raise RuntimeError('Backup location not owned by root')
    os.chmod(backup_root, 0o700)
    fd, backup_name = tempfile.mkstemp(prefix='skip_markers-before-', suffix='.py',
                                        dir=backup_root)
    backup = Path(backup_name)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(original)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(backup, 0o600)

    fd, tempname = tempfile.mkstemp(prefix='.skip_markers-patch-', dir=path.parent)
    replaced = False
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(desired.encode('utf-8'))
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(tempname, st.st_uid, st.st_gid)
        os.chmod(tempname, stat.S_IMODE(st.st_mode))
        # Compile staged code first, without importing app modules or altering DB.
        ast.parse(Path(tempname).read_text(encoding='utf-8'))
        # No writes if a concurrent updater modified the original.
        if path.read_bytes() != original:
            raise RuntimeError('Live code changed after preflight')
        os.replace(tempname, path)
        replaced = True
        if require_service:
            restart_and_check()
        print('INSTALL OK: authenticated manual markers approved on submission.')
        print('Original code backup:', str(backup))
        print('Unmodified: machine approvals, original SQLite, previous pending markers.')
        return True
    except BaseException:
        if replaced:
            recover_fd, recover_name = tempfile.mkstemp(prefix='.skip_markers-rollback-',
                                                         dir=path.parent)
            try:
                with os.fdopen(recover_fd, 'wb') as handle:
                    handle.write(original)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chown(recover_name, st.st_uid, st.st_gid)
                os.chmod(recover_name, stat.S_IMODE(st.st_mode))
                os.replace(recover_name, path)
            finally:
                if os.path.exists(recover_name):
                    os.unlink(recover_name)
            if require_service:
                subprocess.run(['systemctl', 'restart', WEB],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=60, check=False)
            print('ROLLBACK: original code restored; service restart attempted.', file=sys.stderr)
        raise
    finally:
        if os.path.exists(tempname):
            os.unlink(tempname)


def main():
    args = argparse.ArgumentParser(description=__doc__)
    mode = args.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    a = args.parse_args()
    if not DIRECTORY.is_dir():
        raise RuntimeError('Expected provisioning deployment folder missing')
    # Serialize with earlier EpiScene code deployments where possible.
    lock = DIRECTORY / '.episcene-manual-approval-install.lock'
    if lock.is_symlink():
        raise RuntimeError('Unexpected lock symlink')
    with lock.open('a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        install(check=a.check)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.SubprocessError, SyntaxError,
            BlockingIOError) as e:
        # No source code, command args, credentials, or service journals printed.
        print('STOP:', str(e), file=sys.stderr)
        raise SystemExit(1)
