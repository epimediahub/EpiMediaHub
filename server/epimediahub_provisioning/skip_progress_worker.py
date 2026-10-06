#!/usr/bin/env python3
"""Refresh a bounded progress snapshot without blocking dashboard requests."""
import os
from pathlib import Path
import sqlite3

from skip_database import connect
from skip_progress import refresh


def update(path, *, budget=.2, limit=64):
    try:
        with connect(path, timeout=.05) as con:
            return refresh(con, limit=limit, budget=budget)
    except sqlite3.OperationalError as error:
        if 'locked' not in str(error).lower() and 'busy' not in str(error).lower():
            raise
        return 0  # The next timer retries; never compete with a marker change.


if __name__ == '__main__':
    path = Path(os.environ.get('EPIMEDIAHUB_DATA_DIR', '/var/lib/epimediahub')) / 'provisioning.db'
    print('skip_progress_updated=' + str(update(path)), flush=True)
