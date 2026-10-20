"""Private verified expiry observation store.

Only trusted backend/provider workers may write through save_verified().
No HTTP ingestion route exists, so client IDs cannot spoof subscription expiry.
Stores ONLY playlist primary ID, provider-verified DATE and UTC observation time.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import os
from pathlib import Path
import sqlite3
import stat

from expiry_report_rows import VerifiedPlaylistExpiry

DDL="""CREATE TABLE IF NOT EXISTS verified_xtream_expiry (
    playlist_id INTEGER PRIMARY KEY,
    expires_on TEXT NOT NULL,
    observed_epoch INTEGER NOT NULL,
    source TEXT NOT NULL CHECK(source='xtream_user_info')
)"""

class Unavailable(RuntimeError):
    pass


def _private(path: Path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise Unavailable("verified provider cache not installed")
    meta=path.stat()
    if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid()
            or meta.st_mode & 0o077):
        raise Unavailable("private provider cache required")
    root=path.parent
    root_meta=root.stat()
    if root.is_symlink() or not stat.S_ISDIR(root_meta.st_mode) or (
        root_meta.st_uid != os.geteuid() or root_meta.st_mode & 0o077
    ):
        raise Unavailable("private cache directory required")
    return path


def read_verified(path: Path) -> list[VerifiedPlaylistExpiry]:
    """Read-only. Do not return names, credentials or remote API payloads."""
    source=_private(path)
    db=sqlite3.connect(source.resolve().as_uri()+"?mode=ro",uri=True,timeout=5)
    try:
        db.execute("PRAGMA query_only=ON")
        found={row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "verified_xtream_expiry" not in found:
            raise Unavailable("provider expiry schema missing")
        rows=db.execute("""SELECT playlist_id,expires_on,observed_epoch
                           FROM verified_xtream_expiry LIMIT 10001""").fetchall()
        if len(rows)>10000:
            raise Unavailable("too many account expiry records")
        result=[]
        for ident,day,observed in rows:
            if (type(ident) is not int or ident<1 or type(day) is not str
                    or type(observed) is not int):
                raise Unavailable("invalid provider cache record")
            try:
                parsed=date.fromisoformat(day)
                if parsed.isoformat()!=day:
                    raise ValueError()
                time=datetime.fromtimestamp(observed,timezone.utc)
            except (ValueError,OverflowError,OSError):
                raise Unavailable("invalid provider expiry metadata") from None
            result.append(VerifiedPlaylistExpiry(ident,parsed,time))
        return result
    finally:
        db.close()


def save_verified(path: Path, rows: list[VerifiedPlaylistExpiry]) -> int:
    """Trusted backend-only write. Never call with unverified account values.

    Opaque playlist IDs originate from authenticated provider refresh mapping.
    Files are 0600 and parent directory 0700; no caller-supplied strings.
    """
    path=Path(path)
    parent=path.parent
    if parent.is_symlink():
        raise Unavailable("linked provider cache directory")
    parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    meta=parent.stat()
    if meta.st_uid!=os.geteuid() or meta.st_mode & 0o077:
        raise Unavailable("unsafe provider cache directory")
    if path.is_symlink():
        raise Unavailable("linked provider cache")
    if path.exists():
        _private(path)
    if len(rows)>10000:
        raise ValueError("too many observations")
    unique={}
    for row in rows:
        if not isinstance(row,VerifiedPlaylistExpiry):
            raise ValueError("not a verified observation")
        if (type(row.playlist_id) is not int or not 0<row.playlist_id<2**63
                or type(row.expires_on) is not date
                or row.observed_at.tzinfo is None):
            raise ValueError("invalid observation")
        if row.playlist_id in unique:
            raise ValueError("duplicate provider account")
        unique[row.playlist_id]=row
    # Create a private file before sqlite opens it.
    if not path.exists():
        flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY
        if hasattr(os,"O_NOFOLLOW"):flags|=os.O_NOFOLLOW
        try:
            fd=os.open(path,flags,0o600)
            os.close(fd)
        except FileExistsError:
            _private(path)
    db=sqlite3.connect(path,timeout=10)
    try:
        with db:
            db.execute(DDL)
            for row in unique.values():
                db.execute("""INSERT INTO verified_xtream_expiry
                    (playlist_id,expires_on,observed_epoch,source)
                    VALUES (?,?,?,'xtream_user_info')
                    ON CONFLICT(playlist_id) DO UPDATE SET
                       expires_on=excluded.expires_on,
                       observed_epoch=excluded.observed_epoch,
                       source=excluded.source
                    WHERE excluded.observed_epoch > verified_xtream_expiry.observed_epoch
                """,(row.playlist_id,row.expires_on.isoformat(),
                     int(row.observed_at.timestamp())))
        return len(unique)
    finally:
        db.close()
