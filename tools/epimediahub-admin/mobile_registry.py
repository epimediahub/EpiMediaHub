"""Private mobile push registry. No passwords or user identifiers stored.

This is an opt-in administrator *installation* registry, not a customer
device registry. Full tokens are necessary for FCM; this file must remain
private to the provisioning service owner, never served over HTTP.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import uuid

TOKEN = re.compile(r"^[A-Za-z0-9:_-]{80,4096}$")
MAX_INSTALLATIONS = 20

class AdminMobileRegistry:
    def __init__(self, path: Path):
        self.path=Path(path)
        parent=self.path.parent
        if parent.is_symlink():
            raise PermissionError("Push registry directory must not be a symlink")
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        mode=parent.stat().st_mode
        if mode & 0o077:
            raise PermissionError("Push registry directory must be private")
        if self.path.is_symlink():
            raise PermissionError("Push registry DB must not be a symlink")
        if self.path.exists():
            existing=self.path.stat()
            if existing.st_mode & 0o077 or existing.st_uid!=os.geteuid():
                raise PermissionError("Push registry file must be private to its owner")
        else:
            flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY
            if hasattr(os,"O_NOFOLLOW"):flags|=os.O_NOFOLLOW
            fd=os.open(self.path, flags, 0o600)
            os.close(fd)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS admin_mobile_devices(
                installation_id TEXT PRIMARY KEY,
                fcm_token TEXT NOT NULL UNIQUE,
                first_registered_epoch INTEGER NOT NULL,
                last_registered_epoch INTEGER NOT NULL,
                enabled INTEGER NOT NULL CHECK(enabled IN (0,1))
            )""")

    def _connect(self):
        db=sqlite3.connect(self.path, timeout=10)
        db.row_factory=sqlite3.Row
        return db

    def register(self, installation_id: str, fcm_token: str, now_epoch: int | None=None):
        try:
            normalized=str(uuid.UUID(installation_id))
        except (TypeError,ValueError,AttributeError):
            raise ValueError("Invalid installation identifier") from None
        if not isinstance(fcm_token,str) or not TOKEN.fullmatch(fcm_token):
            raise ValueError("Invalid FCM token")
        now=int(time.time()) if now_epoch is None else int(now_epoch)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count=db.execute("SELECT COUNT(*) FROM admin_mobile_devices WHERE enabled=1").fetchone()[0]
            known=db.execute("SELECT 1 FROM admin_mobile_devices WHERE installation_id=?",
                             (normalized,)).fetchone()
            if count>=MAX_INSTALLATIONS and not known:
                raise ValueError("Maximum number of administrator installations reached")
            # A rotated FCM token must never leave two records for the same device.
            db.execute("DELETE FROM admin_mobile_devices WHERE fcm_token=? AND installation_id<>?",
                       (fcm_token,normalized))
            db.execute("""INSERT INTO admin_mobile_devices
                       (installation_id,fcm_token,first_registered_epoch,last_registered_epoch,enabled)
                       VALUES(?,?,?,?,1)
                       ON CONFLICT(installation_id) DO UPDATE SET
                         fcm_token=excluded.fcm_token,
                         last_registered_epoch=excluded.last_registered_epoch,
                         enabled=1
                       """,(normalized,fcm_token,now,now))
        return True

    def unregister(self, installation_id: str):
        try: normalized=str(uuid.UUID(installation_id))
        except (TypeError,ValueError,AttributeError):return False
        with self._connect() as db:
            row=db.execute("DELETE FROM admin_mobile_devices WHERE installation_id=?",
                           (normalized,))
            return row.rowcount==1

    def tokens(self):
        with self._connect() as db:
            return [row["fcm_token"] for row in db.execute(
                "SELECT fcm_token FROM admin_mobile_devices WHERE enabled=1 LIMIT ?",
                (MAX_INSTALLATIONS,))]

    def active_count(self):
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM admin_mobile_devices WHERE enabled=1").fetchone()[0])
