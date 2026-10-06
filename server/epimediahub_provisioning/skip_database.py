"""Short-lived SQLite connections shared by the web server and analysis worker."""
from __future__ import annotations

import sqlite3


class Connection(sqlite3.Connection):
    def __exit__(self, *exception):
        try:
            return super().__exit__(*exception)
        finally:
            # sqlite3's regular context manager only commits/rolls back. Close
            # cursors and their read snapshots as soon as the request finishes.
            self.close()


def connect(path, *, timeout=10.0):
    con = sqlite3.connect(path, timeout=timeout, factory=Connection)
    try:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        # Match the dashboard's Unicode search without materializing every row.
        con.create_function("epi_casefold", 1, lambda value: str(value or '').casefold(), deterministic=True)
        return con
    except BaseException:
        con.close()
        raise


def enable_wal(con):
    """Configure outside a transaction, before serving requests or running jobs."""
    if con.in_transaction:
        raise RuntimeError("WAL configuration requires an idle connection")
    if con.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() != "wal":
        raise RuntimeError("The provisioning database could not enable WAL")
