#!/usr/bin/env python3
"""Fail-closed Xtream subscription expiry probe / gated private-cache refresher.

Reads the EXISTING customer-playlist config on the dashboard host. The probe
sends no customer data to ChatGPT or GitHub, emits only aggregate counts, and
never writes to provisioning.db. Provider requests use only explicit HTTPS
Xtream servers, safe public DNS/IP endpoints, pinned connections and no
redirects. HTTP and private/internal destinations are never contacted.

--probe: provider GETs; no database/cache modifications.
--save-cache: additionally requires EPIMEDIAHUB_XTREAM_REFRESH_APPROVED=YES,
a successful confirmed date for EVERY active Xtream account, and existing
privacy-aware cache modules. Never enable in production without staging tests.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import ssl
import sys
from urllib.parse import urlsplit, urlencode

from expiry_provider_adapter import xtream_expiry

DATABASE=Path("/var/lib/epimediahub/provisioning.db")
CACHE=Path("/var/lib/epimediahub/admin-mobile/expiry-cache.sqlite3")
MAX_ACTIVE=10000
MAX_PAYLOAD=65536
HOSTNAME=re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]{0,250}$")
BASE_PATH=re.compile(r"^/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]*$")


class ProbeError(RuntimeError):
    """Only safe fixed error codes should be exposed in terminal output."""


def _type(config):
    if not isinstance(config,dict):
        raise ProbeError("invalid_playlist_config")
    present=[config[k] for k in ("playlist_type","type") if k in config]
    kinds=[x.strip().upper() for x in present if isinstance(x,str)]
    if (not present or len(kinds)!=len(present) or
        len(set(kinds))!=1 or kinds[0] not in {"XTREAM","M3U"}):
        raise ProbeError("invalid_playlist_type")
    return kinds[0]


def read_accounts(database=DATABASE):
    """No customer names/IDs or config values are emitted or logged."""
    database=Path(database)
    if database.is_symlink() or not database.is_file():
        raise ProbeError("database_unavailable")
    with sqlite3.connect(database.resolve().as_uri()+"?mode=ro",
                         uri=True,timeout=8) as db:
        db.execute("PRAGMA query_only=ON")
        records=db.execute("""
            SELECT p.id,p.config_json
            FROM customer_playlists p JOIN customers c
            ON c.id=p.customer_id
            WHERE p.enabled=1 AND c.enabled=1
            ORDER BY p.id LIMIT 10001
        """).fetchall()
    if len(records)>MAX_ACTIVE:
        raise ProbeError("account_limit_exceeded")
    accounts=[]
    for ident,raw in records:
        if (type(ident) is not int or ident<1 or
                not isinstance(raw,str) or len(raw)>131072):
            raise ProbeError("invalid_playlist_config")
        try:
            cfg=json.loads(raw)
        except (ValueError,TypeError):
            raise ProbeError("invalid_playlist_config") from None
        kind=_type(cfg)
        if kind=="M3U":
            continue
        values=tuple(cfg.get(key) for key in (
            "xtream_server","xtream_username","xtream_password"))
        if (any(not isinstance(x,str) or not x or len(x)>1500 for x in values)
                or any("\n" in x or "\r" in x for x in values)):
            accounts.append((ident,None))
        else:
            accounts.append((ident,values))
    if not accounts:
        raise ProbeError("no_xtream_accounts")
    return accounts


def parse_endpoint(server):
    """HTTPS only, no URL credentials/query/fragment; no arbitrary paths."""
    if not isinstance(server,str) or len(server)>1500 or server != server.strip():
        raise ProbeError("invalid_endpoint")
    try:
        uri=urlsplit(server)
        port=uri.port
        host=uri.hostname
    except ValueError:
        raise ProbeError("invalid_endpoint") from None
    if (uri.scheme!="https" or not host or not uri.netloc or
        uri.username is not None or uri.password is not None or
        uri.query or uri.fragment or (port is not None and port!=443) or
        (uri.path and not BASE_PATH.fullmatch(uri.path))):
        # HTTP credentials would traverse the network in plaintext.
        raise ProbeError("https_endpoint_required")
    if (not HOSTNAME.fullmatch(host) or host.endswith(".") or ".." in host):
        raise ProbeError("invalid_endpoint")
    base=uri.path.rstrip("/")
    return host,443,base


def resolve_public(host,port):
    """Validate ALL DNS answers, pin one for the actual socket connection."""
    try:
        addresses=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    except (socket.gaierror,OSError):
        raise ProbeError("provider_dns_unavailable") from None
    if not addresses:
        raise ProbeError("provider_dns_unavailable")
    selections=[]
    for family,_,_,_,address in addresses:
        if family not in (socket.AF_INET,socket.AF_INET6):
            raise ProbeError("unsupported_address")
        ip=address[0]
        try:
            if not ipaddress.ip_address(ip).is_global:
                raise ProbeError("non_public_provider_address")
        except ValueError:
            raise ProbeError("invalid_provider_address") from None
        selections.append((family,ip))
    return selections[0]



def _https_upgrade_host(origin):
    """Inspect just the configured hostname; never access the HTTP URL."""
    if (not isinstance(origin,str) or len(origin)>1500 or
            origin != origin.strip()):
        raise ProbeError("invalid_endpoint")
    try:
        url=urlsplit(origin)
        # Validate configured port syntax even though we probe only 443.
        configured_port=url.port
        host=url.hostname
    except ValueError:
        raise ProbeError("invalid_endpoint") from None
    if (url.scheme not in {"http","https"} or not url.netloc or
            not host or url.username is not None or url.password is not None
            or url.query or url.fragment
            or (url.path and not BASE_PATH.fullmatch(url.path))
            or not HOSTNAME.fullmatch(host)
            or host.endswith(".") or ".." in host
            or (configured_port is not None and configured_port<1)):
        raise ProbeError("invalid_endpoint")
    return host


def https_tls_handshake_only(origin):
    """Probe a verified TLS certificate on port 443, without any HTTP request.

    In particular: NEVER include Xtream usernames/passwords in this check.
    This cannot confirm that player_api.php is served on the HTTPS endpoint.
    """
    host=_https_upgrade_host(origin)
    family,address=resolve_public(host,443)
    sock=socket.socket(family,socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((address,443))
        with ssl.create_default_context().wrap_socket(
                sock,server_hostname=host) as channel:
            # A successful, verified handshake is enough; no HTTP is sent.
            channel.version()
        return True
    finally:
        sock.close()


def check_https_upgrade(database=DATABASE,handshake=https_tls_handshake_only):
    """Aggregate valid port-443 TLS capability without sending account secrets.

    All results (including failed origins) are cached per configured origin so
    multiple subscriber records never trigger repeated TLS handshakes.
    """
    accounts=read_accounts(database)
    counts=Counter()
    results={}
    for _,credentials in accounts:
        if credentials is None:
            counts["missing_configuration"]+=1
            continue
        origin=credentials[0]
        if origin not in results:
            try:
                results[origin]="https_tls_ready" if handshake(origin) else (
                    "https_tls_unavailable")
            except ProbeError as exc:
                code=str(exc)
                results[origin]="unsafe_or_invalid_origin" if code in {
                    "invalid_endpoint","non_public_provider_address",
                    "invalid_provider_address","unsupported_address"
                } else "https_tls_unavailable"
            except (OSError,ssl.SSLError,ValueError):
                results[origin]="https_tls_unavailable"
        counts[results[origin]]+=1
    return {
        "active_xtream_accounts":len(accounts),
        "accounts_with_valid_https_tls":counts["https_tls_ready"],
        "result_counts":dict(sorted(counts.items())),
        "distinct_origins_checked":len(results),
        "http_requests_sent":0,
        "provider_credentials_sent":False,
        "customer_data_written":False,
        "meaning":"TLS certificate check only; Xtream API not yet verified",
    }



def secure_fetch(endpoint,username,password):
    """No proxy, no redirect, pinned verified TLS, small JSON result."""
    host,port,base=parse_endpoint(endpoint)
    family,ip=resolve_public(host,port)
    query=urlencode({"username":username,"password":password})
    path=base+"/player_api.php?"+query
    conn=http.client.HTTPConnection(host,port,timeout=5)
    try:
        sock=socket.socket(family,socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            sock.connect((ip,port))
            conn.sock=ssl.create_default_context().wrap_socket(
                sock,server_hostname=host)
        except Exception:
            sock.close()
            raise
        conn.request("GET",path,headers={
            "Accept":"application/json",
            "Accept-Encoding":"identity",
            "Connection":"close",
            "User-Agent":"EpiMediaHub-Admin-Expiry/1.0",
        })
        reply=conn.getresponse()
        if reply.status!=200:
            raise ProbeError("provider_http_error")
        raw=reply.read(MAX_PAYLOAD+1)
        if len(raw)>MAX_PAYLOAD:
            raise ProbeError("provider_response_too_large")
        try:
            result=json.loads(raw)
        except (ValueError,UnicodeError):
            raise ProbeError("invalid_provider_json") from None
        if not isinstance(result,dict) or not isinstance(result.get("user_info"),dict):
            raise ProbeError("missing_provider_account")
        info=result["user_info"]
        # Xtream replies should identify the same account being queried.
        # A generic/shared response must never be applied to another playlist.
        if info.get("username") != username:
            raise ProbeError("provider_account_mismatch")
        return result
    finally:
        conn.close()


def probe(database=DATABASE,fetch=secure_fetch,now=None):
    """Injectable transport makes fixture testing fully offline."""
    accounts=read_accounts(database)
    counts=Counter()
    dates=[]
    for ident,credentials in accounts:
        if credentials is None:
            counts["incomplete_credentials"]+=1
            continue
        endpoint,username,password=credentials
        try:
            result=fetch(endpoint,username,password)
            expiry=xtream_expiry(result)
            if expiry.expires_on is None:
                counts["provider_date_unknown"]+=1
                continue
            dates.append((ident,expiry.expires_on,
                          now or datetime.now(timezone.utc)))
            counts["confirmed"]+=1
        except ProbeError as exc:
            # Fixed classification only, no exception traceback or URLs.
            counts[str(exc) if str(exc) in {
                "https_endpoint_required","invalid_endpoint",
                "non_public_provider_address","provider_dns_unavailable",
                "provider_http_error","provider_response_too_large",
                "invalid_provider_json","missing_provider_account",
                "provider_account_mismatch"} else "provider_error"]+=1
        except (OSError,ssl.SSLError,http.client.HTTPException,ValueError):
            counts["provider_error"]+=1
    return {
        "active_xtream_accounts":len(accounts),
        "confirmed":counts["confirmed"],
        "result_counts":dict(sorted(counts.items())),
        "all_confirmed":len(dates)==len(accounts),
    },dates


def main():
    parser=argparse.ArgumentParser(description="Privacy-preserving Xtream expiry check")
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--probe",action="store_true",help="Read-only; no cache writes")
    group.add_argument("--save-cache",action="store_true",
                       help="Requires explicit opt-in and full HTTPS verification")
    group.add_argument("--check-https",action="store_true",
                       help="TLS handshake only on port 443; no credentials or HTTP sent")
    options=parser.parse_args()
    if options.check_https:
        print("XTREAM_HTTPS_TLS_CHECK_COMPLETE; NO_PROVIDER_CREDENTIALS_SENT")
        print(json.dumps(check_https_upgrade(),sort_keys=True))
        return
    if options.save_cache and os.environ.get(
            "EPIMEDIAHUB_XTREAM_REFRESH_APPROVED")!="YES":
        raise ProbeError("write_not_authorized")
    result,dates=probe()
    if options.save_cache:
        if not result["all_confirmed"]:
            raise ProbeError("incomplete_verified_xtream_coverage")
        from expiry_report_rows import VerifiedPlaylistExpiry, require_complete_xtream_coverage
        from expiry_cache import save_verified
        observations=[VerifiedPlaylistExpiry(*row) for row in dates]
        require_complete_xtream_coverage(DATABASE,observations,
                                         datetime.now(timezone.utc))
        save_verified(CACHE,observations)
        print("PRIVATE_XTREAM_EXPIRY_CACHE_UPDATED")
    else:
        print("XTREAM_PROVIDER_PROBE_COMPLETE; NO_DATABASE_OR_CACHE_WRITES")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    try:
        main()
    except (ProbeError,sqlite3.Error,PermissionError,OSError):
        # No raw exception details: internal URLs, login and passwords stay private.
        print("XTREAM_PROVIDER_PROBE_UNAVAILABLE",file=sys.stderr)
        sys.exit(2)
