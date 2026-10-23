"""EpiScene scoped media registration contract (not a live migration).

Safe sidecar design: one provider asset key may be seen on many playlists and
may represent different cuts. Bind metadata per authenticated playlist, with
write-once conflict protection. Never mutates the legacy skip_assets table.

This module has NO installer, background task, network/provider access or
automatic approval. Integrate only after reviewing exact deployed API code
and completing an end-to-end rollback/cut-matching test.
"""
from __future__ import annotations
from dataclasses import dataclass
import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS episcene_scoped_assets (
  playlist_id INTEGER NOT NULL,
  asset_key TEXT NOT NULL,
  owner_customer_id INTEGER NOT NULL,
  source_key TEXT NOT NULL,
  media_type TEXT NOT NULL,
  season INTEGER NOT NULL,
  episode INTEGER NOT NULL,
  duration_ms INTEGER NOT NULL,
  stream_id TEXT NOT NULL,
  extension TEXT NOT NULL,
  PRIMARY KEY (playlist_id,asset_key)
);
CREATE INDEX IF NOT EXISTS episcene_scoped_asset_episode
ON episcene_scoped_assets(source_key,season,episode);
"""


class Conflict(ValueError):
    pass


@dataclass(frozen=True)
class Asset:
    playlist_id: int
    asset_key: str
    source_key: str
    media_type: str
    season: int
    episode: int
    duration_ms: int
    stream_id: str
    extension: str


def _validated_asset(a: Asset):
    if (type(a.playlist_id) is not int or a.playlist_id < 1 or
        not isinstance(a.asset_key, str) or not 1 <= len(a.asset_key) <= 240 or
        not isinstance(a.source_key,str) or not 1 <= len(a.source_key) <= 240 or
        a.media_type != "episode" or
        type(a.season) is not int or not 0 <= a.season <= 100 or
        type(a.episode) is not int or not 1 <= a.episode <= 10000 or
        type(a.duration_ms) is not int or not 30000 <= a.duration_ms <= 86400000 or
        not isinstance(a.stream_id,str) or not a.stream_id.isascii() or
        not a.stream_id.isdecimal() or not 1 <= len(a.stream_id) <= 12 or
        a.extension not in {"mp4","mkv","m4v","avi","ts","mpeg","mpg"}):
        raise Conflict("UNTRUSTED_MEDIA_METADATA")


def _authenticated_owner(con:sqlite3.Connection, device_id:int, playlist_id:int):
    if type(device_id) is not int or device_id < 1:
        raise Conflict("UNTRUSTED_DEVICE_ID")
    row=con.execute("""
        SELECT d.customer_id
        FROM devices d JOIN customers c
             ON c.id=d.customer_id AND c.enabled=1
        JOIN customer_playlists p
             ON p.customer_id=d.customer_id AND p.id=?
        WHERE d.id=? AND d.enabled=1
    """,(playlist_id,device_id)).fetchone()
    if row is None:
        raise Conflict("NOT_AUTHORIZED_FOR_PLAYLIST")
    return int(row[0])


def schema(con:sqlite3.Connection):
    # Intended only for explicit, reviewed migrations, never imported on live.
    con.executescript(DDL)


def register_authenticated(con:sqlite3.Connection, device_id:int, media:Asset):
    """Caller must also authenticate request & rederive asset_key from stream URL.

    Device/playlist ownership is enforced here independently. The caller must
    validate asset_key == provider_asset_key(actual authorized source_url)
    BEFORE this function. A declared key alone is not verification.
    """
    _validated_asset(media)
    owner=_authenticated_owner(con,device_id,media.playlist_id)
    values=(media.playlist_id,media.asset_key,owner,media.source_key,
            media.media_type,media.season,media.episode,media.duration_ms,
            media.stream_id,media.extension)
    columns=("playlist_id","asset_key","owner_customer_id","source_key",
             "media_type","season","episode","duration_ms","stream_id","extension")
    existing=con.execute("""
        SELECT playlist_id,asset_key,owner_customer_id,source_key,media_type,
               season,episode,duration_ms,stream_id,extension
        FROM episcene_scoped_assets
        WHERE playlist_id=? AND asset_key=?
    """,(media.playlist_id,media.asset_key)).fetchone()
    if existing is not None:
        if tuple(existing) != values:
            raise Conflict("SCOPED_MEDIA_IDENTITY_CONFLICT")
        return "already_registered"
    # INSERT only; never replace an existing cross-customer or different-cut key.
    con.execute("""
        INSERT INTO episcene_scoped_assets
            (playlist_id,asset_key,owner_customer_id,source_key,media_type,
             season,episode,duration_ms,stream_id,extension)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """,values)
    return "registered"


def lookup_owned(con:sqlite3.Connection, device_id:int, playlist_id:int,
                 asset_key:str):
    owner=_authenticated_owner(con,device_id,playlist_id)
    row=con.execute("""
        SELECT source_key,media_type,season,episode,duration_ms,
               stream_id,extension
        FROM episcene_scoped_assets
        WHERE playlist_id=? AND asset_key=? AND owner_customer_id=?
    """,(playlist_id,asset_key,owner)).fetchone()
    return dict(zip(("source_key","media_type","season","episode","duration_ms",
                     "stream_id","extension"),row)) if row else None
