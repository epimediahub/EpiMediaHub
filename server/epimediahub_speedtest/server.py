#!/usr/bin/env python3
"""EpiMediaHub private-bandwidth-test backend (Python stdlib only).

Run behind a dedicated HTTPS reverse proxy on 127.0.0.1:8792.
This service intentionally does NOT change any WireGuard routes or VPN services.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import socket
from threading import BoundedSemaphore, Lock
import time
from urllib.parse import parse_qs, urlsplit

HOST = "127.0.0.1"
PORT = 8792
ONE_MIB = 1024 * 1024
MAX_TRANSFER = 32 * ONE_MIB
MAX_UPLOAD = 16 * ONE_MIB
MAX_DOWN_PER_SESSION = 176 * ONE_MIB
MAX_UP_PER_SESSION = 64 * ONE_MIB
TEST_FILE = Path("/opt/epimediahub/speedtest/test-payload.bin")
SESSION_TTL = 300
MAX_LIVE_SESSIONS = 100
SESSIONS_PER_MINUTE = 6
MAX_ACTIVE_TRANSFERS = 12


class State:
    def __init__(self, payload: Path):
        self.payload = payload
        self.lock = Lock()
        self.sessions: dict[str, dict] = {}
        self.issued: dict[str, deque[float]] = defaultdict(deque)
        self.slots = BoundedSemaphore(MAX_ACTIVE_TRANSFERS)

    def create_session(self, ip: str) -> tuple[str | None, str]:
        now = time.monotonic()
        with self.lock:
            self.sessions = {
                token: data for token, data in self.sessions.items() if data["expires"] > now
            }
            timestamps = self.issued[ip]
            while timestamps and timestamps[0] < now - 60:
                timestamps.popleft()
            if len(timestamps) >= SESSIONS_PER_MINUTE:
                return None, "Session-Limit erreicht; bitte kurz warten"
            if len(self.sessions) >= MAX_LIVE_SESSIONS:
                return None, "Testserver ausgelastet"
            token = secrets.token_urlsafe(32)
            timestamps.append(now)
            self.sessions[token] = {
                "ip": ip, "expires": now + SESSION_TTL,
                "download": 0, "upload": 0
            }
            return token, ""

    def reserve(self, token: str, ip: str, direction: str, count: int) -> bool:
        now = time.monotonic()
        with self.lock:
            record = self.sessions.get(token)
            if not record or record["ip"] != ip or record["expires"] <= now:
                return False
            max_bytes = (MAX_DOWN_PER_SESSION if direction == "download"
                         else MAX_UP_PER_SESSION)
            if record[direction] + count > max_bytes:
                return False
            record[direction] += count
            return True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "EpiMediaHubSpeedtest"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, fmt, *args):
        # Never log Authorization values, tokens or query strings.
        safe = fmt.replace("%s", "{}")
        try:
            message = safe.format(*args)
        except Exception:
            message = "request"
        print(f"{self.log_date_time_string()} {self.client_address[0]} {message}",
              flush=True)

    def client_ip(self) -> str:
        # The only external entry is Caddy, which OVERWRITES X-Client-IP.
        # Direct network connections are impossible: server binds to loopback.
        if self.client_address[0] in ("127.0.0.1", "::1"):
            forwarded = self.headers.get("X-Client-IP", "")
            if forwarded and len(forwarded) < 64:
                return forwarded
        return self.client_address[0]

    def reply(self, status: int, obj: dict, *, retry_after: int = 0):
        content = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if retry_after:
            self.send_header("Retry-After", str(retry_after))
        self.end_headers()
        self.wfile.write(content)

    def authenticate(self, direction: str, count: int) -> bool:
        authorization = self.headers.get("Authorization", "")
        token = (authorization[len("Bearer "):]
                 if authorization.startswith("Bearer ") else "")
        if len(token) < 30 or not self.server.state.reserve(
            token, self.client_ip(), direction, count
        ):
            self.reply(403, {"error": "invalid_or_exhausted_speedtest_session"})
            return False
        return True

    def do_GET(self):
        path = urlsplit(self.path)
        if path.path == "/v1/health":
            self.reply(200, {"service": "epimediahub-speedtest", "status": "ok",
                             "version": "1.0"})
            return
        if path.path != "/v1/down":
            self.reply(404, {"error": "not_found"})
            return
        try:
            query = parse_qs(path.query, strict_parsing=True)
            bytes_requested = int(query["bytes"][0])
            stream = int(query.get("stream", ["0"])[0])
        except (ValueError, KeyError, IndexError):
            self.reply(400, {"error": "bad_parameters"})
            return
        if not (32 <= bytes_requested <= MAX_TRANSFER and 0 <= stream < 4):
            self.reply(400, {"error": "out_of_bounds"})
            return
        if not self.authenticate("download", bytes_requested):
            return
        if not self.server.state.slots.acquire(blocking=False):
            self.reply(503, {"error": "server_busy"}, retry_after=15)
            return
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(bytes_requested))
            self.send_header("Cache-Control", "no-store, no-transform")
            self.send_header("Content-Encoding", "identity")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.flush()
            # Kernel zero-copy: no large heap allocations, disk writes, or
            # Python data generation during the bandwidth test.
            with self.server.state.payload.open("rb", buffering=0) as data:
                self.connection.sendfile(
                    data, offset=stream * MAX_TRANSFER, count=bytes_requested)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass
        finally:
            self.server.state.slots.release()

    def do_POST(self):
        path = urlsplit(self.path)
        if path.path == "/v1/session":
            if self.headers.get("Content-Length", "") not in ("0", ""):
                self.reply(400, {"error": "body_not_allowed"})
                return
            token, reason = self.server.state.create_session(self.client_ip())
            if token is None:
                self.reply(429, {"error": reason}, retry_after=60)
                return
            self.reply(200, {
                "session": token, "ttlSeconds": SESSION_TTL,
                "maxStreams": 4, "maxDownloadBytes": MAX_TRANSFER,
                "maxUploadBytes": MAX_UPLOAD
            })
            return
        if path.path != "/v1/up":
            self.reply(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.reply(411, {"error": "content_length_required"})
            return
        if length < 256 * 1024 or length > MAX_UPLOAD:
            self.reply(413, {"error": "upload_size_out_of_bounds"})
            return
        if not self.authenticate("upload", length):
            return
        if not self.server.state.slots.acquire(blocking=False):
            self.reply(503, {"error": "server_busy"}, retry_after=15)
            return
        received = 0
        try:
            while received < length:
                chunk = self.rfile.read(min(65536, length - received))
                if not chunk:
                    return
                received += len(chunk)
            self.reply(200, {"received": received})
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass
        finally:
            self.server.state.slots.release()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, host: str, port: int, state: State):
        super().__init__((host, port), Handler)
        self.state = state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--payload", type=Path, default=TEST_FILE)
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "::1"):
        parser.error("For security, listen only on loopback behind HTTPS proxy")
    if not args.payload.is_file() or args.payload.stat().st_size < 128 * ONE_MIB:
        parser.error("128 MiB sparse payload file missing; run installer first")
    with Server(args.host, args.port, State(args.payload)) as server:
        print(f"EpiMediaHub Speedtest listening on {args.host}:{args.port}", flush=True)
        server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
