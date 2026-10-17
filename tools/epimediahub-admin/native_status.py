"""Sanitized read-only admin status of independent EpiScene analysis lanes.

Only dedicated sources 8/10 are queried. No IPTV streams, customers,
credentials, titles or device information is fetched or returned.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time

LANES={8:"4K ANALYSE",10:"THE BEST"}
GOOD={"done","review","partial","no_match","no_reference"}
REQUIRED={
 "skip_analysis_sources":{"playlist_id","enabled"},
 "skip_analysis_playlists":{"id","archived"},
 "skip_assets":{"asset_key","playlist_id"},
 "skip_jobs":{"asset_key","status","updated_at"},
}

def _epoch(iso):
    if not isinstance(iso,str):return None
    try:
        value=datetime.fromisoformat(iso.replace("Z","+00:00"))
        if value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
        return int(value.timestamp())
    except ValueError:return None

def summarize(con,now=None):
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    now=int(time.time()) if now is None else int(now)
    con.execute("BEGIN")
    for name,fields in REQUIRED.items():
        columns={r["name"] for r in con.execute("PRAGMA table_info("+name+")")}
        if not fields<=columns:
            raise RuntimeError("EPISCENE_SCHEMA_UNAVAILABLE")
    states=con.execute("""
      SELECT p.id,p.archived,s.enabled FROM skip_analysis_playlists p
      LEFT JOIN skip_analysis_sources s ON s.playlist_id=p.id
      WHERE p.id IN (8,10) ORDER BY p.id""").fetchall()
    if {r["id"] for r in states}!=set(LANES):
        raise RuntimeError("DEDICATED_SOURCES_UNAVAILABLE")
    records={}
    for row in states:
        records[row["id"]]={
          "id":row["id"],"label":LANES[row["id"]],
          "enabled":bool(row["enabled"]==1 and row["archived"]==0),
          "queued":0,"running":0,"completed":0,"failed":0,
          "last_completion_epoch":None}
    grouped=con.execute("""
      SELECT a.playlist_id pid,j.status state,COUNT(*) total,
        MAX(CASE WHEN j.status IN
          ('done','review','partial','no_match','no_reference')
          THEN j.updated_at ELSE NULL END) latest
      FROM skip_jobs j INNER JOIN skip_assets a
      ON j.asset_key=a.asset_key
      WHERE a.playlist_id IN (8,10)
      GROUP BY a.playlist_id,j.status""").fetchall()
    for row in grouped:
        entry=records[row["pid"]]
        state=row["state"]
        if state=="queued":entry["queued"]+=row["total"]
        elif state in ("running","processing","in_progress"):
            entry["running"]+=row["total"]
        elif state in GOOD:entry["completed"]+=row["total"]
        elif state=="failed":entry["failed"]+=row["total"]
        latest=_epoch(row["latest"])
        if latest is not None and latest<=now+300:
            prev=entry["last_completion_epoch"]
            if prev is None or latest>prev:entry["last_completion_epoch"]=latest
    return {"sampled_at_epoch":now,"lanes":[records[pid] for pid in sorted(LANES)],
            "scope":"independent_analysis_sources_only"}

def read_status(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("ANALYSIS_DATABASE_MISSING")
    con=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=5)
    try:return summarize(con)
    finally:con.close()
