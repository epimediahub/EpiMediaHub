"""Bounded chapter/audio analysis using private, administrator-enabled playlists.

The API accepts numeric catalogue IDs, never arbitrary URLs. The worker resolves
credentials from the existing customer configuration and keeps them off subprocess
arguments/logs. FFmpeg reads through a pinned-IP, redirect-aware, byte-limited proxy.
All results are pending proposals; no inferred boundary is published automatically.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import hashlib
import http.client
import ipaddress
import json
import os
import re
import secrets
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_PROVIDER_REDIRECTS = 3
CHAPTER_NAMES = {
    "intro": "intro", "opening": "intro", "opening credits": "intro", "title sequence": "intro", "vorspann": "intro", "titelsequenz": "intro",
    "recap": "recap", "previously on": "recap", "rückblick": "recap", "zusammenfassung": "recap",
    "outro": "outro", "credits": "outro", "end credits": "outro", "ending credits": "outro", "abspann": "outro",
}


def authorized_playlist(con, device, playlist_id):
    return con.execute("SELECT * FROM customer_playlists WHERE id=? AND customer_id=?", (playlist_id, device["customer_id"])).fetchone()


def configured_source(row):
    try:
        config = json.loads(row["config_json"])
        base = str(config.get("xtream_server", "")).rstrip("/")
        uri = urllib.parse.urlsplit(base)
        if config.get("playlist_type", "").upper() != "XTREAM" or uri.scheme not in ("http", "https") or not uri.hostname or uri.username or uri.password or uri.query or uri.fragment:
            raise ValueError("not_analyzable")
        if not config.get("xtream_username") or not config.get("xtream_password"):
            raise ValueError("credentials_missing")
        return config
    except (ValueError, TypeError, KeyError):
        raise ValueError("not_analyzable") from None


def source_account(row):
    cfg = configured_source(row)
    return hashlib.sha256((cfg["xtream_server"].rstrip("/") + "|" + cfg["xtream_username"]).encode()).hexdigest()


def source_url(playlist, asset):
    config = configured_source(playlist)
    folder = "series" if asset["media_type"] == "episode" else "movie"
    user = urllib.parse.quote(str(config["xtream_username"]), safe="")
    password = urllib.parse.quote(str(config["xtream_password"]), safe="")
    return f"{config['xtream_server'].rstrip('/')}/{folder}/{user}/{password}/{asset['stream_id']}.{asset['extension']}"


def provider_asset_key(url, media_type):
    uri = urllib.parse.urlsplit(url)
    name = uri.path.rsplit("/", 1)[-1]
    kind = "EPISODE" if media_type == "episode" else "MOVIE"
    origin = f"{uri.scheme.lower()}://{uri.hostname.lower()}:{uri.port if uri.port is not None else -1}"
    xtream = re.fullmatch(r"[0-9]+\.[a-zA-Z0-9]{1,8}", name) and uri.path.split("/")[1:2] in (["series"], ["movie"])
    value = f"{origin}|{kind}|{name}" if xtream else f"{kind}|{url}"
    return hashlib.sha256(value.encode()).hexdigest()


def register_asset(con, raw, data, device):
    from skip_markers import now
    playlist_id = raw.get("playlist_id")
    stream = raw.get("stream_id", "")
    extension = raw.get("extension", "")
    if type(playlist_id) is not int or not isinstance(stream, str) or not re.fullmatch(r"[0-9]{1,12}", stream) or extension not in ("mp4", "mkv", "m4v", "avi", "ts", "mpeg", "mpg"):
        return False
    playlist = authorized_playlist(con, device, playlist_id)
    if playlist is None:
        return False
    enabled = con.execute("SELECT enabled FROM skip_analysis_sources WHERE playlist_id=?", (playlist_id,)).fetchone()
    if not enabled or not enabled[0]:
        return False
    asset = dict(data, stream_id=stream, extension=extension)
    try:
        url = source_url(playlist, asset)
        if provider_asset_key(url, data["media_type"]) != data["asset_key"]:
            return False
    except ValueError:
        return False
    con.execute("""INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(asset_key) DO UPDATE SET
      playlist_id=excluded.playlist_id,source_key=excluded.source_key,duration_ms=excluded.duration_ms,updated_at=excluded.updated_at""",
      (data["asset_key"], data["source_key"], playlist_id, stream, extension, data["media_type"], data["duration_ms"], data["season"], data["episode"], data["title"], data["year"], now()))
    con.execute("INSERT OR IGNORE INTO skip_jobs(asset_key,status,created_at,updated_at) VALUES(?,'queued',?,?)", (data["asset_key"], now(), now()))
    con.execute("DELETE FROM skip_auto_assets WHERE asset_key=?", (data["asset_key"],))
    if data.get("imdb_id") or data.get("tmdb_id"):
        # Client metadata can seed a pending online suggestion; it cannot by
        # itself establish verified series identity for automatic publication.
        con.execute("INSERT OR IGNORE INTO skip_auto_identities VALUES(?,?,?,?,?)",
                    (data["source_key"], data.get("imdb_id", ""), data.get("tmdb_id", 0), "client_id_hint", now()))
    # A marker can be approved before audio analysis is enabled or its first
    # lookup succeeds. Registering that file later makes the existing reference
    # usable; wake waiting episodes without requiring another marker approval.
    reference = con.execute("""SELECT 1 FROM skip_records
      WHERE asset_key=? AND source_key=? AND season=? AND segment_type='intro'
      AND status='approved' AND disabled=0 AND end_ms-start_ms BETWEEN 19000 AND 300000
      AND ABS(duration_ms-?)<=2000 LIMIT 1""",
      (data["asset_key"], data["source_key"], data["season"], data["duration_ms"])).fetchone()
    if reference:
        con.execute("""UPDATE skip_jobs SET status='queued',attempts=0,detail='',updated_at=?
          WHERE status='no_reference' AND asset_key IN (
            SELECT a.asset_key FROM skip_assets a
            JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
            WHERE a.source_key=? AND a.season=?)""",
          (now(), data["source_key"], data["season"]))
    return True


def public_address(url, host):
    uri = urllib.parse.urlsplit(url)
    if (len(url) > 8192 or uri.scheme not in ("https", "http") or not uri.hostname
            or uri.hostname != host or uri.username or uri.password or uri.fragment):
        raise ValueError("unsafe_source")
    port = uri.port or (443 if uri.scheme == "https" else 80)
    addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.ip_address(address).is_global
                            or ipaddress.ip_address(address).is_multicast
                            for address in addresses):
        raise ValueError("unsafe_source")
    return uri, addresses[0]


class ProviderRedirect(urllib.request.HTTPRedirectHandler):
    """Follow only a bounded provider response chain, revalidating every hop."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target, _ = public_address(newurl, urllib.parse.urlsplit(newurl).hostname)
        if urllib.parse.urlsplit(req.full_url).scheme == "https" and target.scheme != "https":
            raise ValueError("redirect_downgrade")
        if req.get_method() not in ("GET", "HEAD"):
            raise ValueError("unsafe_source")
        # Never copy credentials, cookies, an old Host or Referer to another host.
        allowed = {"user-agent", "accept-encoding", "range"}
        forwarded = {key: value for key, value in req.header_items()
                     if key.lower() in allowed}
        return urllib.request.Request(newurl, headers=forwarded,
                                      method=req.get_method())

    def http_error_302(self, req, fp, code, msg, headers):
        location = headers.get("Location") or headers.get("URI")
        if not location:
            return None
        count = getattr(req, "_epimediahub_redirects", 0)
        if count >= MAX_PROVIDER_REDIRECTS:
            fp.close()
            raise ValueError("redirect_limit")
        if any(ord(character) < 32 for character in location):
            fp.close()
            raise ValueError("unsafe_source")
        try:
            newurl = urllib.parse.urljoin(req.full_url, location.strip().replace(" ", "%20"))
            redirected = self.redirect_request(req, fp, code, msg, headers, newurl)
        finally:
            # urllib's default drains the entire redirect body with fp.read().
            # Closing it keeps large/unbounded redirect bodies outside the decoder.
            fp.close()
        redirected._epimediahub_redirects = count + 1
        return self.parent.open(redirected, timeout=req.timeout)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def provider_failure(error):
    """Fixed, credential-free categories for failures hidden behind the proxy."""
    if isinstance(error, ValueError) and str(error) in (
            "unsafe_source", "redirect_limit", "redirect_downgrade"):
        return str(error)
    if isinstance(error, urllib.error.HTTPError) and 100 <= error.code <= 599:
        return "provider_http_" + str(error.code)
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "provider_timeout"
    if isinstance(reason, socket.gaierror):
        return "provider_dns"
    if isinstance(reason, ssl.SSLError):
        return "provider_tls"
    return "provider_connection"


def pinned_connection(cls, host, ip, **kwargs):
    connection = cls(host, **kwargs)
    connection._create_connection = lambda address, timeout=None, source_address=None: socket.create_connection((ip, address[1]), timeout, source_address)
    return connection


@contextmanager
def provider_proxy(url, busy=lambda: False):
    host = urllib.parse.urlsplit(url).hostname
    public_address(url, host)
    budget = [MAX_INPUT_BYTES]
    failure = [None]
    lock = threading.Lock()
    token = "/" + secrets.token_urlsafe(24)

    class HTTP(urllib.request.HTTPHandler):
        def http_open(self, req):
            _, address = public_address(req.full_url, urllib.parse.urlsplit(req.full_url).hostname)
            return self.do_open(lambda original, **kw: pinned_connection(http.client.HTTPConnection, original, address, **kw), req)

    class HTTPS(urllib.request.HTTPSHandler):
        def https_open(self, req):
            _, address = public_address(req.full_url, urllib.parse.urlsplit(req.full_url).hostname)
            return self.do_open(lambda original, **kw: pinned_connection(http.client.HTTPSConnection, original, address, **kw), req, context=ssl.create_default_context())

    opener = urllib.request.build_opener(HTTP(), HTTPS(), ProviderRedirect(), urllib.request.ProxyHandler({}))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_HEAD(self):
            self.relay("HEAD")

        def do_GET(self):
            self.relay("GET")

        def relay(self, method):
            if self.path != token or busy():
                self.send_error(503)
                return
            headers = {"User-Agent": "EpiMediaHub/0.8.2 private analysis", "Accept-Encoding": "identity"}
            requested_range = self.headers.get("Range")
            if requested_range and not re.fullmatch(r"bytes=[0-9]+-[0-9]*", requested_range):
                self.send_error(400)
                return
            if requested_range:
                headers["Range"] = requested_range
            sent = False
            try:
                with opener.open(urllib.request.Request(url, headers=headers, method=method), timeout=5) as response:
                    self.send_response(response.status)
                    for key in ("Content-Length", "Content-Type", "Content-Range", "Accept-Ranges"):
                        if response.headers.get(key):
                            self.send_header(key, response.headers[key])
                    self.end_headers(); sent = True
                    if method == "HEAD":
                        return
                    while not busy():
                        with lock:
                            if budget[0] <= 0:
                                failure[0] = "analysis_input_limit"
                                break
                            amount = min(65_536, budget[0])
                            budget[0] -= amount
                        chunk = response.read(amount)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except Exception as error:
                # Client cancellation is not an upstream provider failure.
                if not isinstance(error, (BrokenPipeError, ConnectionResetError)):
                    failure[0] = provider_failure(error)
                if not sent:
                    self.send_error(502)
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        try:
            yield f"http://127.0.0.1:{server.server_port}{token}"
        except ValueError as error:
            if str(error) == "analysis_failed" and failure[0]:
                raise ValueError(failure[0]) from None
            raise
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def run(command, max_bytes=20_000_000, timeout=180, busy=lambda: False):
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.DEVNULL)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if busy() or time.monotonic() - started > timeout or os.fstat(output.fileno()).st_size > max_bytes:
                    raise ValueError("analysis_deferred" if busy() else "analysis_limit")
                time.sleep(.2)
            if process.returncode or os.fstat(output.fileno()).st_size > max_bytes:
                raise ValueError("analysis_failed")
            output.seek(0)
            return output.read(max_bytes + 1)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=2)


def input_options(source):
    # Nested HLS/concat playlists must not escape the controlled provider proxy.
    protocols = "http,tcp" if source.startswith("http://127.0.0.1:") else "file"
    return ["-protocol_whitelist", protocols, "-format_whitelist", "mov,matroska,avi,mpegts,mpeg,mp3,wav"]


def probe(source, busy=lambda: False):
    raw = run(["ffprobe", "-v", "error", *input_options(source), "-show_entries", "format=duration:chapter=start_time,end_time:chapter_tags=title", "-of", "json", source], max_bytes=200_000, timeout=35, busy=busy)
    data = json.loads(raw)
    duration = round(float(data.get("format", {}).get("duration", 0)) * 1000)
    if not 5000 <= duration <= 86_400_000:
        raise ValueError("duration_unknown")
    return duration, data.get("chapters", [])[:500]


def chapter_candidates(chapters, duration):
    from skip_markers import valid_range
    result = []
    for chapter in chapters:
        title = str(chapter.get("tags", {}).get("title", "")).strip().lower()
        kind = CHAPTER_NAMES.get(title)
        try:
            start, end = round(float(chapter["start_time"]) * 1000), round(float(chapter["end_time"]) * 1000)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if valid_range(kind, start, end, duration):
            result.append((kind, start, end))
    return result


def fingerprint(source, start_ms, length_ms, busy=lambda: False, *, require_complete=False, with_coverage=False):
    if not 15_000 <= length_ms <= 600_000 or start_ms < 0:
        raise ValueError("fingerprint_window")
    pcm = run(["ffmpeg", "-nostdin", "-v", "error", "-threads", "1", *input_options(source), "-ss", str(start_ms / 1000), "-i", source, "-t", str(length_ms / 1000), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "11025", "-f", "s16le", "pipe:1"], busy=busy)
    if require_complete and len(pcm) / (2 * 11025) * 1000 < length_ms - 250:
        raise ValueError("fingerprint_incomplete")
    library = ctypes.util.find_library("chromaprint")
    if not library:
        raise ValueError("chromaprint_unavailable")
    lib = ctypes.CDLL(library)
    lib.chromaprint_new.argtypes = [ctypes.c_int]; lib.chromaprint_new.restype = ctypes.c_void_p
    for name in ("chromaprint_free", "chromaprint_get_sample_rate", "chromaprint_get_item_duration", "chromaprint_finish"):
        getattr(lib, name).argtypes = [ctypes.c_void_p]
    lib.chromaprint_start.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.chromaprint_feed.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int16), ctypes.c_int]
    lib.chromaprint_get_raw_fingerprint.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_uint32)), ctypes.POINTER(ctypes.c_int)]
    lib.chromaprint_dealloc.argtypes = [ctypes.c_void_p]
    ctx = lib.chromaprint_new(1)
    if not ctx:
        raise ValueError("fingerprint_failed")
    pointer = ctypes.POINTER(ctypes.c_uint32)()
    try:
        if not lib.chromaprint_start(ctx, 11025, 1):
            raise ValueError("fingerprint_failed")
        for offset in range(0, len(pcm) - len(pcm) % 2, 131072):
            block = pcm[offset:offset + 131072]
            samples = (ctypes.c_int16 * (len(block) // 2)).from_buffer_copy(block)
            if not lib.chromaprint_feed(ctx, samples, len(samples)):
                raise ValueError("fingerprint_failed")
        if not lib.chromaprint_finish(ctx):
            raise ValueError("fingerprint_failed")
        count = ctypes.c_int()
        if not lib.chromaprint_get_raw_fingerprint(ctx, ctypes.byref(pointer), ctypes.byref(count)) or not 0 < count.value <= 10_000:
            raise ValueError("fingerprint_failed")
        step = lib.chromaprint_get_item_duration(ctx) * 1000.0 / lib.chromaprint_get_sample_rate(ctx)
        result = [pointer[i] for i in range(count.value)], step
        return (*result, len(pcm) / (2 * 11025) * 1000) if with_coverage else result
    finally:
        if pointer:
            lib.chromaprint_dealloc(pointer)
        lib.chromaprint_free(ctx)


def matching_offset(reference, target, step_ms):
    """Reject low information, weak matches and repeated/ambiguous occurrences."""
    if not 40 <= len(reference) <= len(target) <= 10_000 or len(set(reference)) < max(15, len(reference) // 5):
        return None
    candidates = []
    for offset in range(len(target) - len(reference) + 1):
        distance = sum((a ^ b).bit_count() for a, b in zip(reference, target[offset:offset + len(reference)])) / (32 * len(reference))
        if distance <= .10:
            candidates.append((distance, offset))
    if not candidates:
        return None
    score, best = min(candidates)
    if any(abs(offset - best) * step_ms > 2000 and distance <= score + .025 for distance, offset in candidates):
        return None
    # The fingerprint grid is about 124 ms wide. Refine an already accepted,
    # unique peak between its neighbours without changing the match threshold.
    fraction = 0.0
    if score > 0 and 0 < best < len(target) - len(reference):
        left, right = [sum((a ^ b).bit_count() for a, b in
                          zip(reference, target[offset:offset + len(reference)]))
                       / (32 * len(reference)) for offset in (best - 1, best + 1)]
        curvature = left - 2 * score + right
        if curvature > 0:
            fraction = max(-.5, min(.5, .5 * (left - right) / curvature))
    return round((best + fraction) * step_ms), 1.0 - score
