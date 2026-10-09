#!/usr/bin/env python3
"""Root-only WireGuard reconciler. Manages only explicitly assigned peers.

Clearing AllowedIPs disables a peer's IP traffic without losing its preshared
key. Managed peers also start with no AllowedIPs in wg-quick's disk config, so
reboots cannot resurrect an expired grant. No private keys leave this server.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import ipaddress
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

MARKER = "# EpiMediaHub VPN managed: starts blocked until dashboard confirmation"


def atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle, temp = tempfile.mkstemp(prefix=".vpn-", dir=path.parent)
    try:
        with os.fdopen(handle, "w") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def peer_blocks(text):
    return re.split(r"(?im)(?=^\s*\[Peer\]\s*$)", text)


def block_key(block):
    found = re.search(r"(?im)^\s*PublicKey\s*=\s*([^\s#]+)", block)
    return found[1] if found else None


def seal_config(path, owned):
    """Preserve interface settings, PSKs and unrelated peers; block managed IPs on boot."""
    path = Path(path)
    original = path.read_text()
    blocks = peer_blocks(original)
    blocks[0] = re.sub(r"(?im)^\s*SaveConfig\s*=\s*true\s*(?:#.*)?$", "SaveConfig = false", blocks[0])
    found = set()
    for index, block in enumerate(blocks[1:], 1):
        key = block_key(block)
        if key not in owned:
            continue
        found.add(key)
        block = re.sub(r"(?im)^\s*AllowedIPs\s*=.*(?:\n|$)", "", block)
        if MARKER not in block:
            block = block.rstrip() + "\n" + MARKER + "\n\n"
        blocks[index] = block
    for key in sorted(set(owned) - found):
        blocks.append(f"\n[Peer]\nPublicKey = {key}\n{MARKER}\n")
    result = "".join(blocks)
    if result != original:
        backup = path.with_name(path.name + ".before-epimediahub-vpn")
        if not backup.exists():
            atomic(backup, original)
        atomic(path, result)


def parse_time(value):
    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Timezone required")
    return value


def validate(snapshot, subnet):
    if not isinstance(snapshot, dict) or snapshot.get("version") != 1 or snapshot.get("node") != "finland":
        raise ValueError("Invalid snapshot")
    lease = snapshot.get("lease_seconds")
    if type(lease) is not int or not 5 <= lease <= 60:
        raise ValueError("Invalid lease")
    server_time = parse_time(snapshot["server_time"])
    if abs((datetime.now(timezone.utc) - server_time).total_seconds()) > 120:
        raise ValueError("Server clock mismatch")
    peers = snapshot.get("peers")
    if not isinstance(peers, list) or len(peers) > 10000:
        raise ValueError("Invalid peers")
    ids, keys, addresses = set(), set(), set()
    network = ipaddress.ip_network(subnet)
    for peer in peers:
        if not isinstance(peer, dict) or type(peer.get("id")) is not int or peer["id"] < 1 or type(peer.get("enabled")) is not bool:
            raise ValueError("Invalid peer")
        key = peer["public_key"]
        decoded = base64.b64decode(key, validate=True)
        if len(decoded) != 32 or not any(decoded) or base64.b64encode(decoded).decode() != key:
            raise ValueError("Invalid key")
        address = ipaddress.ip_interface(peer["client_address"])
        if address.version != 4 or address.network.prefixlen != 32 or address.ip not in network or int(address.ip) <= int(network.network_address) + 1 or address.ip == network.broadcast_address:
            raise ValueError("Invalid address")
        if peer["id"] in ids or key in keys or (peer["enabled"] and str(address) in addresses):
            raise ValueError("Duplicate peer")
        if not re.fullmatch(r"[0-9a-f]{64}", peer.get("generation", "")):
            raise ValueError("Invalid generation")
        if peer["enabled"] and (not peer.get("expires_at") or parse_time(peer["expires_at"]) <= max(server_time, datetime.now(timezone.utc))):
            raise ValueError("Expired grant")
        ids.add(peer["id"]); keys.add(key)
        if peer["enabled"]:
            addresses.add(str(address))
    return server_time


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Agent redirects are not allowed")


class Agent:
    def __init__(self, config, runner=None):
        self.config = config
        self.interface = config.get("interface", "wg0")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,15}", self.interface):
            raise ValueError("Invalid interface")
        self.base = config["dashboard_url"].rstrip("/")
        url = urlsplit(self.base)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}:
            raise ValueError("HTTPS dashboard origin required")
        self.token = config["token"]
        if len(self.token) < 32:
            raise ValueError("Invalid token")
        self.path = Path(config.get("state_file", "/var/lib/epimediahub-vpn/agent-state.json"))
        self.wg_config = Path(config.get("wireguard_config", f"/etc/wireguard/{self.interface}.conf"))
        self.subnet = config.get("subnet", "10.92.0.0/24")
        self.runner = runner or subprocess.run
        self.owned = set()
        if self.path.exists():
            self.owned.update(json.loads(self.path.read_text())["owned"])
        for block in peer_blocks(self.wg_config.read_text())[1:]:
            if MARKER in block and block_key(block):
                self.owned.add(block_key(block))
        self.deadlines = {}
        self.lock = threading.RLock()
        self.stopping = threading.Event()
        self.opener = urllib.request.build_opener(NoRedirect())

    def wg(self, *args):
        return self.runner([shutil.which("wg") or "/usr/bin/wg", *args], check=True, capture_output=True, text=True, timeout=3).stdout

    def allowed(self):
        result = {}
        for line in self.wg("show", self.interface, "allowed-ips").splitlines():
            key, _, ips = line.partition("\t")
            result[key] = set(ips.replace(",", " ").split()) - {"(none)"}
        return result

    def close_all(self):
        with self.lock:
            existing = self.allowed()
            for key in sorted(self.owned):
                if existing.get(key):
                    self.wg("set", self.interface, "peer", key, "allowed-ips", "")
            self.deadlines.clear()

    def expire(self):
        with self.lock:
            for key, deadline in list(self.deadlines.items()):
                if time.monotonic() >= deadline:
                    self.wg("set", self.interface, "peer", key, "allowed-ips", "")
                    del self.deadlines[key]

    def watchdog(self):
        while not self.stopping.wait(.5):
            try:
                self.expire()
            except Exception:
                # systemd restarts us and ExecStopPost also clears owned peers.
                os._exit(1)

    def request(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        with self.opener.open(req, timeout=5) as response:
            payload = response.read(1024 * 1024 + 1)
            if len(payload) > 1024 * 1024:
                raise ValueError("Oversized response")
            return json.loads(payload)

    def apply(self, snapshot):
        server_time = validate(snapshot, self.subnet)
        peers = snapshot["peers"]
        received = time.monotonic()
        wanted = {p["public_key"]: p for p in peers}
        with self.lock:
            actual = self.allowed()
            # Never steal a VPN address from a peer outside this dashboard.
            for key, existing in actual.items():
                if key not in self.owned and key not in wanted:
                    for peer in peers:
                        if peer["enabled"] and any(ipaddress.ip_interface(peer["client_address"]).ip in ipaddress.ip_network(cidr) for cidr in existing):
                            raise ValueError("Address belongs to an unmanaged peer")
            self.owned.update(wanted)
            atomic(self.path, json.dumps({"owned": sorted(self.owned)}))
            seal_config(self.wg_config, self.owned)
            # Revoke old bindings BEFORE granting replacements.
            for key in sorted(self.owned):
                if key not in wanted or not wanted[key]["enabled"]:
                    if actual.get(key):
                        self.wg("set", self.interface, "peer", key, "allowed-ips", "")
                    self.deadlines.pop(key, None)
            for peer in peers:
                if not peer["enabled"]:
                    continue
                local_time = datetime.now(timezone.utc)
                elapsed = max(0, (local_time - server_time).total_seconds())
                remaining = (parse_time(peer["expires_at"]) - max(server_time, local_time)).total_seconds()
                deadline = received + min(snapshot["lease_seconds"] - elapsed, remaining)
                if time.monotonic() >= deadline:
                    raise ValueError("Grant expired during reconciliation")
                self.deadlines[peer["public_key"]] = deadline
                if actual.get(peer["public_key"]) != {peer["client_address"]}:
                    self.wg("set", self.interface, "peer", peer["public_key"], "allowed-ips", peer["client_address"])
            actual = self.allowed()
            handshakes = {}
            for line in self.wg("show", self.interface, "latest-handshakes").splitlines():
                key, _, epoch = line.partition("\t")
                handshakes[key] = int(epoch)
            report = []
            for peer in peers:
                expected = {peer["client_address"]} if peer["enabled"] else set()
                if actual.get(peer["public_key"], set()) != expected:
                    raise ValueError("WireGuard did not apply the requested rules")
                report.append({"id": peer["id"], "generation": peer["generation"], "enabled": peer["enabled"], "last_handshake": handshakes.get(peer["public_key"], 0)})
            # Public server key is safe to return via the authenticated agent
            # channel; clients no longer need a manually copied WireGuard key.
            server_key = self.wg("show", self.interface, "public-key").strip()
            return {"peers": report, "server_public_key": server_key}

    def run(self):
        # Never reuse an old grant after process restart.
        self.close_all()
        watchdog = threading.Thread(target=self.watchdog, daemon=True)
        watchdog.start()
        while not self.stopping.is_set():
            try:
                snapshot = self.request("/v1/vpn-agent/desired")
                report = self.apply(snapshot)
                self.request("/v1/vpn-agent/applied", report)
            except Exception as error:
                self.close_all()
                print(f"VPN-Abgleich fehlgeschlagen ({type(error).__name__}); verwaltete Zugänge gesperrt.", flush=True)
            self.stopping.wait(5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/etc/epimediahub-vpn-agent.json")
    parser.add_argument("--close", action="store_true")
    args = parser.parse_args()
    config_path = Path(args.config)
    if config_path.stat().st_mode & 0o077:
        raise SystemExit("Die Agent-Konfiguration muss Modus 0600 haben.")
    config = json.loads(config_path.read_text())
    agent = Agent(config)
    if args.close:
        agent.close_all()
        return
    lock_path = agent.path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            agent.run()
        finally:
            agent.stopping.set()
            agent.close_all()


if __name__ == "__main__":
    main()
