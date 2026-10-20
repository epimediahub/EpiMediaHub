"""Private daily observations from explicitly permitted INSECURE HTTP Xtream requests.

Separate from the HTTPS-verified authoritative cache and automatic report/FCM
publisher. Per-account status is replaced atomically on every polling cycle.
HTTP dates are preliminary: they are never represented as authenticated data.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date,datetime,timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat

VALID_STATES=frozenset({
 "http_observed","provider_date_undated","provider_date_unavailable",
 "provider_http_4xx","provider_http_5xx","provider_http_other",
 "provider_http_error","provider_timeout","provider_connection_refused",
 "provider_connection_reset","provider_transport_error","provider_error",
 "invalid_endpoint","http_origin_required","non_public_provider_address",
 "provider_dns_unavailable","provider_response_too_large",
 "invalid_provider_json","missing_provider_account",
 "provider_account_mismatch","incomplete_credentials",
})
MAX_AGE_SECONDS=48*3600
CLOCK_SKEW_SECONDS=5*60
DDL="""CREATE TABLE IF NOT EXISTS insecure_http_expiry (
  playlist_id INTEGER PRIMARY KEY,
  expires_on TEXT,
  observed_epoch INTEGER NOT NULL,
  status TEXT NOT NULL,
  config_fingerprint TEXT NOT NULL,
  source TEXT NOT NULL CHECK(source='insecure_http')
)"""

class InsecureSnapshotUnavailable(RuntimeError):pass

@dataclass(frozen=True)
class Observation:
    playlist_id:int
    expires_on:date|None
    observed_at:datetime
    status:str
    config_fingerprint:str

def _owner_directory(directory):
    p=Path(directory)
    if p.is_symlink():raise InsecureSnapshotUnavailable("linked cache folder")
    p.mkdir(mode=0o700,parents=True,exist_ok=True)
    st=p.stat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.geteuid() or st.st_mode & 0o077:
        raise InsecureSnapshotUnavailable("unsafe cache folder")
    return p

def _private_file(file):
    file=Path(file)
    if file.is_symlink() or not file.is_file():
        raise InsecureSnapshotUnavailable("snapshot unavailable")
    st=file.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or st.st_mode & 0o077:
        raise InsecureSnapshotUnavailable("unsafe snapshot permissions")
    return file

def _key(path,create=False):
    p=Path(path)
    if create:_owner_directory(p.parent)
    if not p.exists() and create:
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
        if hasattr(os,"O_NOFOLLOW"):flags|=os.O_NOFOLLOW
        try:
            fd=os.open(p,flags,0o600)
            with os.fdopen(fd,"wb") as file:
                file.write(secrets.token_bytes(32))
        except FileExistsError:pass
    raw=_private_file(p).read_bytes()
    if len(raw)!=32:raise InsecureSnapshotUnavailable("invalid snapshot key")
    return raw

def fingerprint(config:object,key:bytes):
    """Bind a record to CURRENT Xtream origin and credentials without logging."""
    if not isinstance(config,dict) or len(key)!=32:
        raise InsecureSnapshotUnavailable("invalid fingerprint input")
    values=[config.get(k) for k in (
        "xtream_server","xtream_username","xtream_password")]
    if any(not isinstance(v,str) or not v or len(v)>1500 for v in values):
        raise InsecureSnapshotUnavailable("unavailable account identity")
    serialized=json.dumps(values,ensure_ascii=True,separators=(",",":")).encode()
    return hmac.new(key,serialized,hashlib.sha256).hexdigest()

def load_key_for_worker(cache:Path):
    return _key(Path(cache).with_name("expiry-http.key"),create=True)

def get_key_for_preview(cache:Path):
    return _key(Path(cache).with_name("expiry-http.key"),create=False)

def replace_snapshot(cache:Path,observations:list[Observation]):
    """Atomic FULL replacement, never leave yesterday's failed account as known."""
    p=Path(cache)
    _owner_directory(p.parent)
    if len(observations)>10000:raise InsecureSnapshotUnavailable("too many rows")
    seen=set()
    for row in observations:
        if (not isinstance(row,Observation) or type(row.playlist_id) is not int
            or not 0<row.playlist_id<2**63 or row.playlist_id in seen
            or row.status not in VALID_STATES
            or (row.status=="http_observed")!=(type(row.expires_on) is date)
            or row.observed_at.tzinfo is None or row.observed_at.utcoffset() is None
            or not isinstance(row.config_fingerprint,str)
            or len(row.config_fingerprint)!=64
            or any(c not in "0123456789abcdef" for c in row.config_fingerprint)):
            raise InsecureSnapshotUnavailable("bad snapshot observation")
        seen.add(row.playlist_id)
    if p.is_symlink():raise InsecureSnapshotUnavailable("linked snapshot")
    if not p.exists():
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
        if hasattr(os,"O_NOFOLLOW"):flags|=os.O_NOFOLLOW
        try:
            fd=os.open(p,flags,0o600)
            os.close(fd)
        except FileExistsError:pass
    _private_file(p)
    conn=sqlite3.connect(p,timeout=12)
    try:
        with conn:
            conn.execute(DDL)
            conn.execute("DELETE FROM insecure_http_expiry")
            conn.executemany("""INSERT INTO insecure_http_expiry
              (playlist_id,expires_on,observed_epoch,status,config_fingerprint,source)
              VALUES (?,?,?,?,?,'insecure_http')""",[
                (o.playlist_id,o.expires_on.isoformat() if o.expires_on else None,
                 int(o.observed_at.timestamp()),o.status,o.config_fingerprint)
                for o in observations
            ])
    finally:conn.close()
    return len(observations)

def read_snapshot(cache:Path,now:datetime):
    """Read valid recent rows only; invalid cache means no false safe dates."""
    p=Path(cache)
    if not p.exists() and not p.is_symlink():return {}
    _private_file(p)
    if now.tzinfo is None or now.utcoffset() is None:
        raise InsecureSnapshotUnavailable("invalid clock")
    conn=sqlite3.connect(p.resolve().as_uri()+"?mode=ro",uri=True,timeout=8)
    try:
        conn.execute("PRAGMA query_only=ON")
        records=conn.execute("""SELECT playlist_id,expires_on,observed_epoch,
                                 status,config_fingerprint,source
                                 FROM insecure_http_expiry LIMIT 10001""").fetchall()
    except sqlite3.Error:
        raise InsecureSnapshotUnavailable("invalid snapshot schema") from None
    finally:conn.close()
    if len(records)>10000:raise InsecureSnapshotUnavailable("too many records")
    output={}
    epoch=now.timestamp()
    for ident,day,observed,status,digest,source in records:
        if type(ident) is not int or ident<=0 or type(observed) is not int:
            raise InsecureSnapshotUnavailable("invalid stored record")
        if source!="insecure_http" or status not in VALID_STATES:
            raise InsecureSnapshotUnavailable("invalid source or state")
        if ident in output:raise InsecureSnapshotUnavailable("duplicate record")
        if not isinstance(digest,str) or len(digest)!=64:
            raise InsecureSnapshotUnavailable("invalid identity hash")
        # Date and status must agree even if the observation is stale.
        try:
            parsed=date.fromisoformat(day) if day is not None else None
        except (TypeError,ValueError):
            raise InsecureSnapshotUnavailable("invalid stored date") from None
        if (parsed is None)!=(status!="http_observed"):
            raise InsecureSnapshotUnavailable("date/status conflict")
        if -CLOCK_SKEW_SECONDS<=epoch-observed<=MAX_AGE_SECONDS:
            output[ident]=(parsed,status,digest)
    return output
