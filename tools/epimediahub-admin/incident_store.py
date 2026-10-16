"""Local incident ledger for EpiMediaHub Admin. No network, FCM or systemd.

Only sanitized monitor_rules.Alert values may be supplied. The caller must
explicitly resolve confirmed recoveries: missing measurements are not proof.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable

from monitor_rules import Alert

_SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_incidents (
    alert_key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    message TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('open', 'acknowledged', 'resolved')),
    first_seen_epoch INTEGER NOT NULL,
    last_seen_epoch INTEGER NOT NULL,
    occurrences INTEGER NOT NULL CHECK(occurrences > 0),
    acknowledged_epoch INTEGER,
    resolved_epoch INTEGER
);
CREATE INDEX IF NOT EXISTS admin_incidents_state_idx
    ON admin_incidents(state, last_seen_epoch);
"""


class IncidentStore:
    def __init__(self, path: str | Path):
        # The parent directory must also be restricted in deployment.
        p = Path(path)
        if p.is_symlink():
            raise PermissionError('Refusing symlink incident database')
        if p.exists():
            if p.stat().st_mode & 0o077:
                raise PermissionError('Incident database must not be group/world accessible')
        else:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, 'O_NOFOLLOW'):
                flags |= os.O_NOFOLLOW
            fd = os.open(p, flags, 0o600)
            os.close(fd)
        self.path = str(p)
        self._initialize()

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self):
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def observe(self, alerts: Iterable[Alert], now_epoch: int) -> list[str]:
        """Persist observations and return new/reopened keys for push.

        Repeat observations only update timestamps/counts; acknowledged alerts
        never create repeat pushes. Recovery must be verified explicitly.
        """
        to_notify = []
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            for alert in alerts:
                if not isinstance(alert, Alert):
                    raise TypeError('Only sanitized monitor_rules.Alert values are allowed')
                row = conn.execute('SELECT state FROM admin_incidents WHERE alert_key=?',
                                   (alert.key,)).fetchone()
                if row is None:
                    conn.execute('''INSERT INTO admin_incidents
                        (alert_key,kind,severity,entity_id,message,state,
                         first_seen_epoch,last_seen_epoch,occurrences)
                         VALUES (?,?,?,?,?,'open',?,?,1)''',
                        (alert.key,alert.kind,alert.severity,alert.entity_id,
                         alert.message,now_epoch,now_epoch))
                    to_notify.append(alert.key)
                elif row['state'] == 'resolved':
                    conn.execute('''UPDATE admin_incidents SET
                        kind=?,severity=?,entity_id=?,message=?,state='open',
                        first_seen_epoch=?,last_seen_epoch=?,occurrences=1,
                        acknowledged_epoch=NULL,resolved_epoch=NULL
                        WHERE alert_key=?''',
                        (alert.kind,alert.severity,alert.entity_id,
                         alert.message,now_epoch,now_epoch,alert.key))
                    to_notify.append(alert.key)
                else:
                    conn.execute('''UPDATE admin_incidents SET
                        severity=?,message=?,last_seen_epoch=?,occurrences=occurrences+1
                        WHERE alert_key=?''',
                        (alert.severity,alert.message,now_epoch,alert.key))
        return to_notify

    def acknowledge(self, alert_key: str, now_epoch: int) -> bool:
        with self._connect() as conn:
            row = conn.execute('''UPDATE admin_incidents SET state='acknowledged',
                   acknowledged_epoch=? WHERE alert_key=? AND state='open' ''',
                   (now_epoch,alert_key))
            return row.rowcount == 1

    def resolve(self, alert_key: str, now_epoch: int) -> bool:
        """Call only after verified recovery, or an explicit owner resolution."""
        with self._connect() as conn:
            row = conn.execute('''UPDATE admin_incidents SET state='resolved',
                   resolved_epoch=? WHERE alert_key=? AND state!='resolved' ''',
                   (now_epoch,alert_key))
            return row.rowcount == 1

    def get(self, alert_key: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute('SELECT * FROM admin_incidents WHERE alert_key=?',
                               (alert_key,)).fetchone()
            return dict(row) if row else None

    def open_incidents(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute('''SELECT * FROM admin_incidents
                    WHERE state IN ('open','acknowledged')
                    ORDER BY last_seen_epoch DESC''').fetchall()
            return [dict(x) for x in rows]
