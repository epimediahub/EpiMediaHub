#!/usr/bin/env python3
"""Safely install only the additive, fail-closed GalaBox HTTPS vault endpoint.

--check changes nothing. --apply preserves existing Fire TV WireGuard peers,
VPN and app licenses, dashboards and DB. Creates one persistent 0600 master
key if and only if no previous GalaBox vault was installed.
"""
import argparse
import json
import os
import pwd
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path("/opt/epimediahub/provisioning")
DATA_DEFAULT = Path("/var/lib/epimediahub")
SERVICE = "epimediahub-provisioning.service"
SOURCE = Path(__file__).resolve().parents[1] / "vpn_galabox_remote_vault.py"
DEST = BASE / "vpn_galabox_remote_vault.py"
WSGI = BASE / "wsgi.py"
MASTER = "galabox-vpn-vault-master.bin"
IMPORT_LINE = "import vpn_galabox_remote_vault  # Non-Amazon secure GalaBox VPN vault; Fire TV unchanged.\n"
BACKUP_ROOT = Path("/var/backups/epimediahub")


def require(ok, text):
    if not ok:
        raise RuntimeError(text)


def command(*args):
    return subprocess.check_output(args, text=True, timeout=25).strip()


def system():
    require(os.geteuid() == 0, "Please run as root.")
    require(WSGI.is_file() and (BASE / "vpn_auto_enroll.py").is_file() and
            (BASE / "vpn_dashboard.py").is_file() and SOURCE.is_file(),
            "Existing dashboard/VPN module or new source is missing.")
    require(command("systemctl", "is-active", SERVICE) == "active",
            "Provisioning service not active.")
    require(command("systemctl", "show", SERVICE, "-p", "WorkingDirectory", "--value") == str(BASE),
            "Unexpected production working directory.")
    username = command("systemctl", "show", SERVICE, "-p", "User", "--value")
    require(bool(username) and username != "root", "Dedicated service user required.")
    user = pwd.getpwnam(username)
    pid = int(command("systemctl", "show", SERVICE, "-p", "MainPID", "--value"))
    require(pid > 0, "Running service PID missing.")
    raw = Path("/proc").joinpath(str(pid), "environ").read_bytes().split(b"\0")
    env = dict(part.decode("utf-8", "surrogateescape").split("=", 1) for part in raw if b"=" in part)
    data = Path(env.get("EPIMEDIAHUB_DATA_DIR", DATA_DEFAULT))
    require(data.is_absolute() and data.is_dir() and (data/"provisioning.db").is_file(),
            "Production data directory or database missing.")
    if (data/MASTER).exists():
        master = data/MASTER
        meta = master.lstat()
        require(stat.S_ISREG(meta.st_mode) and meta.st_mode & 0o077 == 0
                and master.stat().st_size == 32, "Existing GalaBox master key invalid.")
    elif "import vpn_galabox_remote_vault" in WSGI.read_text():
        raise RuntimeError("Previously installed GalaBox vault master is missing; RESTORE BACKUP, never rotate.")
    text = WSGI.read_text()
    require("install_vpn_dashboard" in text and "import vpn_auto_enroll" in text,
            "Unexpected VPN bootstrap. Refusing to overwrite.")
    python = BASE / ".venv/bin/python"
    require(python.is_file(), "Existing Python venv missing.")
    subprocess.check_call([str(python), "-m", "py_compile", str(SOURCE)],
                          stdout=subprocess.DEVNULL, timeout=15)
    return user, data


def snapshot_database(db_path, destination):
    with sqlite3.connect("file:" + str(db_path) + "?mode=ro", uri=True, timeout=25) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
        require(dst.execute("PRAGMA quick_check").fetchone()[0] == "ok",
                "Database backup integrity check failed.")
    destination.chmod(0o600)


def health():
    opener = urllib.request.build_opener(_NoRedirect())
    for path in ("/health", "/v1/device/vpn/status", "/v1/device/vpn/galabox-vault-key"):
        try:
            with opener.open("http://127.0.0.1:8787" + path, timeout=5) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        require(status == (200 if path == "/health" else 401),
                "Unexpected service endpoint response: " + path + " => " + str(status))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def apply(user, data):
    BACKUP_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="galabox-vault-" + time.strftime("%Y%m%d-%H%M%S") + "-", dir=BACKUP_ROOT))
    backup.chmod(0o700)
    old_wsgi = WSGI.read_bytes()
    (backup/"wsgi.py").write_bytes(old_wsgi)
    (backup/"wsgi.py").chmod(0o600)
    had_module = DEST.is_file()
    if had_module:
        shutil.copy2(DEST, backup/"vpn_galabox_remote_vault.py")
        (backup/"vpn_galabox_remote_vault.py").chmod(0o600)
    snapshot_database(data/"provisioning.db", backup/"provisioning.db")

    master = data/MASTER
    if master.is_file():
        shutil.copy2(master, backup/MASTER)
        (backup/MASTER).chmod(0o600)
    else:
        # A new random 256-bit key; NEVER overwrite or rotate a preexisting one.
        fd = os.open(master, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            os.write(fd, os.urandom(32))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chown(master, user.pw_uid, user.pw_gid)
        master.chmod(0o600)
        shutil.copy2(master, backup/MASTER)
        (backup/MASTER).chmod(0o600)
    changed = False
    try:
        command("systemctl", "stop", SERVICE)
        staged = DEST.with_name(DEST.name + ".new")
        shutil.copyfile(SOURCE, staged)
        os.chown(staged, user.pw_uid, user.pw_gid)
        staged.chmod(0o644)
        os.replace(staged, DEST)
        text = old_wsgi.decode("utf-8")
        if IMPORT_LINE.strip() not in text:
            text = text.rstrip() + "\n\n" + IMPORT_LINE
        tmp = WSGI.with_name("wsgi.galabox-new.py")
        tmp.write_text(text, encoding="utf-8")
        os.chown(tmp, user.pw_uid, user.pw_gid)
        tmp.chmod(0o644)
        os.replace(tmp, WSGI)
        changed = True
        command("systemctl", "start", SERVICE)
        for i in range(25):
            try:
                health()
                break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError("Health checks did not pass after service restart.")
    except BaseException:
        command("systemctl", "stop", SERVICE)
        if changed:
            WSGI.write_bytes(old_wsgi)
            os.chown(WSGI, user.pw_uid, user.pw_gid)
            if had_module:
                shutil.copy2(backup/"vpn_galabox_remote_vault.py", DEST)
            else:
                DEST.unlink(missing_ok=True)
        command("systemctl", "start", SERVICE)
        raise RuntimeError("Installation rolled back, existing VPN and license DB unchanged. Backup: " + str(backup))

    print("INSTALL OK – GalaBox remote AES vault is available, Fire TV keys/licenses untouched.")
    print("Protected master file: " + str(master) + " (0600, do NOT delete)")
    print("Backup (contains sensitive master key, root-only): " + str(backup))


def main():
    ap = argparse.ArgumentParser()
    choices = ap.add_mutually_exclusive_group(required=True)
    choices.add_argument("--check", action="store_true")
    choices.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    user, data = system()
    print("CHECK OK – existing VPN backend, master-key lifecycle and source validated; no live changes.")
    if args.apply:
        apply(user, data)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ABBRUCH: " + str(exc), file=sys.stderr)
        sys.exit(1)
