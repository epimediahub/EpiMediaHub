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
            db.execute("""CREATE TABLE IF NOT EXISTS admin_mobile_outbox(
                installation_id TEXT NOT NULL,
                alert_key TEXT NOT NULL,
                generation_epoch INTEGER NOT NULL,
                kind TEXT NOT NULL,
                sent_epoch INTEGER,
                PRIMARY KEY(installation_id,alert_key,generation_epoch)
            )""")

    def begin_push_test(self, installation_id: str, now_epoch: int | None=None):
        """Throttle generic push test to once per two minutes per opted-in device."""
        try:
            normalized=str(uuid.UUID(installation_id))
        except (TypeError,ValueError,AttributeError):
            return "not_registered", None
        now=int(time.time()) if now_epoch is None else int(now_epoch)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS admin_mobile_push_tests(
                installation_id TEXT PRIMARY KEY,
                attempted_epoch INTEGER NOT NULL
            )""")
            row=db.execute("""SELECT fcm_token FROM admin_mobile_devices
                WHERE installation_id=? AND enabled=1""",(normalized,)).fetchone()
            if row is None:
                return "not_registered", None
            previous=db.execute("""SELECT attempted_epoch FROM admin_mobile_push_tests
                WHERE installation_id=?""",(normalized,)).fetchone()
            if previous and now-int(previous[0])<120:
                return "rate_limited", None
            db.execute("""INSERT INTO admin_mobile_push_tests(
                installation_id,attempted_epoch) VALUES(?,?)
                ON CONFLICT(installation_id)
                DO UPDATE SET attempted_epoch=excluded.attempted_epoch
            """,(normalized,now))
            return "ready", row["fcm_token"]

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
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("DELETE FROM admin_mobile_devices WHERE installation_id=?",
                           (normalized,))
            db.execute("DELETE FROM admin_mobile_outbox WHERE installation_id=?",
                       (normalized,))
            if db.execute("""SELECT 1 FROM sqlite_master WHERE
                  type='table' AND name='admin_mobile_push_tests'""").fetchone():
                db.execute("DELETE FROM admin_mobile_push_tests WHERE installation_id=?",
                           (normalized,))
            return row.rowcount==1

    def tokens(self):
        with self._connect() as db:
            return [row["fcm_token"] for row in db.execute(
                "SELECT fcm_token FROM admin_mobile_devices WHERE enabled=1 LIMIT ?",
                (MAX_INSTALLATIONS,))]

    def enqueue(self, events: list[tuple[str,str,int]], now_epoch: int):
        """Queue a new incident generation once for each opted-in installation."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Never retain undeliverable notifications indefinitely.
            db.execute("DELETE FROM admin_mobile_outbox WHERE generation_epoch<?",
                       (int(now_epoch)-30*86400,))
            installs=[row[0] for row in db.execute(
                "SELECT installation_id FROM admin_mobile_devices WHERE enabled=1")]
            for key,kind,generation in events:
                if not isinstance(key,str) or len(key)>200:
                    raise ValueError("Invalid incident key")
                if kind not in ("analysis_stalled","playlist_access","worker_preflight",
                                "service_down","build_failed","playback_errors","daily_report",
                                "expiry_monthly","expiry_weekly"):
                    raise ValueError("Invalid incident category")
                for install in installs:
                    db.execute("""INSERT OR IGNORE INTO admin_mobile_outbox(
                       installation_id,alert_key,generation_epoch,kind,sent_epoch)
                       VALUES(?,?,?,?,NULL)""",
                       (install,key,int(generation),kind))

    def pending(self, limit: int=40):
        with self._connect() as db:
            return [dict(row) for row in db.execute("""
                SELECT o.installation_id,o.alert_key,o.generation_epoch,
                       o.kind,d.fcm_token
                FROM admin_mobile_outbox o
                JOIN admin_mobile_devices d ON d.installation_id=o.installation_id
                WHERE o.sent_epoch IS NULL AND d.enabled=1
                ORDER BY o.generation_epoch LIMIT ?""",(min(int(limit),40),))]

    def sent(self, installation_id: str, key: str, generation: int, now_epoch: int):
        with self._connect() as db:
            db.execute("""UPDATE admin_mobile_outbox SET sent_epoch=?
               WHERE installation_id=? AND alert_key=? AND generation_epoch=?
                 AND sent_epoch IS NULL""",
                (int(now_epoch),installation_id,key,int(generation)))

    def active_count(self):
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM admin_mobile_devices WHERE enabled=1").fetchone()[0])
