# -*- coding: utf-8 -*-
"""EpiMediaHub Enigma2 receiver configuration sync.

The client is deliberately independent from Tailscale. It talks only to the
configured EpiMediaHub provisioning URL and never changes network settings.
"""
from __future__ import print_function

import json
import os
import socket
import threading
import time
try:
    from urllib.request import Request, urlopen
except ImportError:
    from urllib2 import Request, urlopen

DATA_DIR = "/etc/enigma2/epimediahub"
SYNC_FILE = os.path.join(DATA_DIR, "receiver_sync.json")
SYNC_INTERVAL = 120
_STOP = threading.Event()
_THREAD = None


def _read(path, default=None):
    try:
        with open(path, "r") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else (default or {})
    except Exception:
        return default or {}


def _write(path, value):
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    tmp = path + ".tmp"
    with open(tmp, "w") as handle:
        json.dump(value, handle, separators=(",", ":"))
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except Exception:
            pass
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    os.rename(tmp, path)


def _request(server, path, token="", body=None, timeout=12):
    url = server.rstrip("/") + path
    headers = {"User-Agent": "EpiMediaHub-Enigma/0.9.42", "Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    response = urlopen(Request(url, data=data, headers=headers), timeout=timeout)
    try:
        raw = response.read()
    finally:
        try:
            response.close()
        except Exception:
            pass
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "ignore")
    value = json.loads(raw or "{}")
    if not isinstance(value, dict):
        raise Exception("Ungueltige Serverantwort")
    return value


def device_id():
    try:
        return socket.gethostname().strip() or "enigma2"
    except Exception:
        return "enigma2"


def configure(server, bootstrap_token):
    state = _read(SYNC_FILE, {})
    state.update({"server": server.rstrip("/"), "bootstrap_token": bootstrap_token.strip(), "device_id": device_id(), "enabled": True})
    _write(SYNC_FILE, state)
    return state


def _bootstrap(state):
    token = state.get("bootstrap_token", "")
    if not token:
        raise Exception("Kein Bootstrap-Schluessel eingerichtet")
    result = _request(state["server"], "/v1/device/bootstrap", body={"device_id": state.get("device_id") or device_id(), "bootstrap_token": token, "platform": "enigma2"})
    session_token = str(result.get("session_token", "")).strip()
    if not session_token:
        raise Exception("Server hat keinen Sitzungsschluessel geliefert")
    state["session_token"] = session_token
    state.pop("bootstrap_token", None)
    state["last_error"] = ""
    _write(SYNC_FILE, state)
    return state


def _report(state, version, status, error=""):
    try:
        _request(state["server"], "/v1/device/sync-result", state.get("session_token", ""), {"config_version": int(version), "status": status, "error": str(error)[:1000]})
    except Exception:
        pass


def _apply_playlist(plugin, playlist_url):
    url = str(playlist_url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise Exception("Playlist-Adresse ist ungueltig")
    data = plugin.load_profiles()
    profiles = data.get("profiles", [])
    managed = None
    for profile in profiles:
        if profile.get("managed_remote_sync"):
            managed = profile
            break
    if managed is None:
        managed = plugin.default_profile("EpiMediaHub Remote", url)
        managed["managed_remote_sync"] = True
        profiles.append(managed)
    old_url = str(managed.get("m3u_url", "") or "")
    if old_url == url:
        data["active_id"] = managed.get("id", "")
        plugin.save_profiles(data)
        return
    managed["m3u_url"] = url
    managed["source_mode"] = "m3u"
    managed["expiry"] = ""
    managed["expiry_checked_at"] = 0
    managed["epg_url_auto"] = ""
    managed["fast_api_error"] = ""
    managed["managed_remote_sync"] = True
    # Remove only caches for the remote-managed profile. Existing/manual
    # playlists remain untouched and therefore form a local safety fallback.
    try:
        plugin._clear_profile_source_cache(managed.get("id", ""))
    except Exception:
        pass
    data["profiles"] = profiles
    data["active_id"] = managed.get("id", "")
    plugin.save_profiles(data)


def sync_once(plugin):
    state = _read(SYNC_FILE, {})
    if not state.get("enabled") or not state.get("server"):
        return False
    try:
        if not state.get("session_token"):
            state = _bootstrap(state)
        result = _request(state["server"], "/v1/device/config", state.get("session_token", ""))
        version = int(result.get("config_version", 0) or 0)
        current = int(state.get("applied_config_version", 0) or 0)
        config = result.get("config", {}) if isinstance(result.get("config"), dict) else {}
        if version > current:
            _apply_playlist(plugin, config.get("playlist_url", ""))
            state["applied_config_version"] = version
            state["last_sync_at"] = int(time.time())
            state["last_error"] = ""
            _write(SYNC_FILE, state)
            _report(state, version, "ok")
            return True
        state["last_sync_at"] = int(time.time())
        state["last_error"] = ""
        _write(SYNC_FILE, state)
        return False
    except Exception as error:
        state["last_error"] = str(error)[:1000]
        state["last_sync_at"] = int(time.time())
        try:
            _write(SYNC_FILE, state)
        except Exception:
            pass
        version = state.get("applied_config_version", 0)
        if state.get("session_token"):
            _report(state, version, "error", error)
        return False


def start(plugin):
    global _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        return
    _STOP.clear()
    def worker():
        # Let Enigma2 and networking finish booting before the first request.
        _STOP.wait(12)
        while not _STOP.is_set():
            sync_once(plugin)
            _STOP.wait(SYNC_INTERVAL)
    _THREAD = threading.Thread(target=worker, name="EpiMediaHubConfigSync")
    _THREAD.daemon = True
    _THREAD.start()


def stop():
    _STOP.set()
