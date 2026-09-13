#!/usr/bin/env python3
from pathlib import Path
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_v0914.py /path/to/plugin.py")

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit("%s: expected exactly one match, got %d" % (label, count))
    text = text.replace(old, new, 1)


def regex_once(pattern, replacement, label, flags=0):
    global text
    text2, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit("%s: expected exactly one match, got %d" % (label, count))
    text = text2


replace_once('PLUGIN_VERSION = "0.9.13"', 'PLUGIN_VERSION = "0.9.14"', "plugin version")

if "import socket\n" not in text:
    if "import shutil\n" in text:
        text = text.replace("import shutil\n", "import shutil\nimport socket\n", 1)
    else:
        raise SystemExit("socket import: anchor not found")

if "from concurrent.futures import ThreadPoolExecutor, as_completed" not in text:
    regex_once(
        r"from concurrent\.futures import ThreadPoolExecutor\b",
        "from concurrent.futures import ThreadPoolExecutor, as_completed",
        "concurrent futures import",
    )
    # Keep the fallback valid on receivers without concurrent.futures.
    regex_once(
        r"(except Exception:\n\s+ThreadPoolExecutor = None)(?!\n\s+as_completed = None)",
        r"\1\n    as_completed = None",
        "concurrent futures fallback",
    )

# Make the status dots clearly visible on a TV while keeping the stock MenuList.
replace_once(
    '(i, pos(82, 170 + (i * 48)), size(18, 18)) for i in range(8))',
    '(i, pos(80, 164 + (i * 48)), size(28, 28)) for i in range(8))',
    "status icon geometry",
)
replace_once(
    'rows.append("      %s%s   |   %s   |   %d %s   |   %s   |   %s" % (',
    'rows.append("        %s%s   |   %s   |   %d %s   |   %s   |   %s" % (',
    "playlist row indent",
)

# A playlist chooser only needs to know whether the server can be reached. The
# previous code could spend six seconds on player_api.php and then another six
# seconds on the M3U URL. A short TCP connection is enough for this UI status.
fast_probe = '''def probe_playlist_online(profile):
    """Fast server reachability check used by the playlist selector."""
    if not isinstance(profile, dict):
        return False, "Ungültige Playlist"

    managed = clean_text(profile.get("managed_file", ""))
    if managed:
        try:
            if os.path.isfile(managed) and os.path.getsize(managed) > 0:
                return True, ""
        except Exception:
            pass
        return False, "Lokale Playlist-Datei nicht erreichbar"

    url = clean_text(profile.get("m3u_url", ""))
    if not url:
        return False, "Keine Playlist-URL"

    try:
        parsed = urlparse(url)
        host = clean_text(parsed.hostname or "")
        if not host:
            return False, "Server nicht erreichbar"
        scheme = clean_text(parsed.scheme or "http").lower()
        try:
            port = int(parsed.port or (443 if scheme == "https" else 80))
        except Exception:
            port = 443 if scheme == "https" else 80
        connection = socket.create_connection((host, port), 1.35)
        try:
            return True, ""
        finally:
            try:
                connection.close()
            except Exception:
                pass
    except Exception as error:
        return False, clean_text(error) or "Server nicht erreichbar"
'''
regex_once(
    r"def probe_playlist_online\(profile\):\n.*?\n\ndef expiry_summary\(value\):",
    fast_probe + "\n\ndef expiry_summary(value):",
    "fast playlist probe",
    re.S,
)

# Prefer the lightweight status check before the separate expiry lookup.
replace_once(
    "        self.refreshList()\n        self._startExpiryJob()\n        self._startHealthJob()",
    "        self.refreshList()\n        self._startHealthJob()\n        self._startExpiryJob()",
    "health job order",
)

# Results are published to the selector as soon as EACH server replies. The old
# pool.map() waited for the slowest server before showing any result.
health_worker = '''    def _publishHealthResult(self, result, completed):
        if not result or self._health_stop:
            return
        profile_id, original_url, online, error = result
        completed.append(result)
        if not hasattr(self, "_health_live"):
            self._health_live = {}
        self._health_live[profile_id] = "online" if online else "offline"
        self._health_changed = True

    def _persistHealthResults(self, completed):
        if not completed or self._health_stop:
            return
        data = load_profiles()
        now = int(time.time())
        changed = False
        for result in completed:
            if not result:
                continue
            profile_id, original_url, online, error = result
            for profile in data.get("profiles", []):
                if profile.get("id") != profile_id:
                    continue
                if clean_text(profile.get("m3u_url", "")) != original_url:
                    break
                profile["online_status"] = "online" if online else "offline"
                profile["online_checked_at"] = now
                profile["online_error"] = "" if online else (error or "Server nicht erreichbar")
                changed = True
                break
        if changed:
            save_profiles(data)

    def _healthWorker(self, queue):
        def _check(profile):
            if self._health_stop:
                return None
            online, error = probe_playlist_online(profile)
            return (profile.get("id", ""), clean_text(profile.get("m3u_url", "")), online, clean_text(error))

        completed = []
        if ThreadPoolExecutor is not None and as_completed is not None and len(queue) > 1:
            try:
                workers = min(6, len(queue))
                pool = ThreadPoolExecutor(max_workers=workers)
                futures = [pool.submit(_check, profile) for profile in queue]
                for future in as_completed(futures):
                    if self._health_stop:
                        break
                    try:
                        result = future.result()
                    except Exception:
                        result = None
                    self._publishHealthResult(result, completed)
                pool.shutdown(wait=False)
                self._persistHealthResults(completed)
                return
            except Exception:
                pass

        for profile in queue:
            if self._health_stop:
                break
            self._publishHealthResult(_check(profile), completed)
        self._persistHealthResults(completed)
'''
regex_once(
    r"    def _healthWorker\(self, queue\):\n.*?\n    def _pollHealthJob\(self\):",
    health_worker + "\n    def _pollHealthJob(self):",
    "incremental health worker",
    re.S,
)

# Use fresh in-memory results immediately; persisted values remain the instant
# fallback when reopening the selector.
replace_once(
    '            online = clean_text(profile.get("online_status", ""))',
    '            online = clean_text(getattr(self, "_health_live", {}).get(profile.get("id", ""), profile.get("online_status", "")))',
    "live status row",
)
replace_once(
    '            status = clean_text(self.profiles[index].get("online_status", ""))',
    '            _profile = self.profiles[index]\n            status = clean_text(getattr(self, "_health_live", {}).get(_profile.get("id", ""), _profile.get("online_status", "")))',
    "live status icon",
)

# Ensure the live cache exists before the worker can publish into it.
replace_once(
    "        self._health_job = None\n        self._health_stop = False",
    "        self._health_job = None\n        self._health_live = {}\n        self._health_stop = False",
    "health live cache init",
)

release_notes = '''    "0.9.14": {
        "de": ["Playlist-Onlineprüfung deutlich beschleunigt: schneller Server-Check statt langem Xtream-/M3U-Doppeltest.", "Grüne und rote Statussymbole sind größer und deutlich sichtbar; jede Playlist aktualisiert ihren Status sofort, sobald das Ergebnis vorliegt."],
        "en": ["Playlist online checks are much faster using a lightweight server reachability test instead of a long Xtream/M3U double check.", "Green and red indicators are larger and clearer; each playlist updates as soon as its own result arrives."],
        "tr": ["Oynatma listesi çevrimiçi kontrolü uzun Xtream/M3U çift testi yerine hızlı sunucu erişim kontrolü kullanır.", "Yeşil ve kırmızı durum simgeleri daha büyük ve nettir; her liste sonucu gelir gelmez güncellenir."],
        "it": ["Il controllo online delle playlist è molto più rapido grazie a un test leggero di raggiungibilità del server.", "Gli indicatori verdi e rossi sono più grandi e chiari; ogni playlist si aggiorna appena arriva il proprio risultato."],
        "es": ["La comprobación online de las listas es mucho más rápida mediante una prueba ligera de conexión al servidor.", "Los indicadores verde y rojo son más grandes y claros; cada lista se actualiza en cuanto llega su resultado."]
    },
'''
replace_once(
    '_RELEASE_NOTES = {\n    "0.9.13": {',
    '_RELEASE_NOTES = {\n' + release_notes + '    "0.9.13": {',
    "release notes",
)

path.write_text(text, encoding="utf-8")
print("patched", path)
