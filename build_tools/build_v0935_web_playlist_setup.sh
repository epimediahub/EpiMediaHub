#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.34.ipk"
T=/tmp/epimedia0935
P="$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub/plugin.py"

rm -rf "$T"
mkdir -p "$T/ar" "$T/data" "$T/control" "$T/pkg"
cd "$T/ar"
ar x "$B"
tar -xzf data.tar.gz -C ../data
tar -xzf control.tar.gz -C ../control
cp debian-binary ../pkg/debian-binary
rm -rf "$T/data/etc/enigma2/EpiMediaHub" "$T/data/etc/enigma2/epimediahub"

export P
python3 - <<'PY'
import os
from pathlib import Path
p=Path(os.environ['P'])
t=p.read_text(encoding='utf-8')
if 'PLUGIN_VERSION = "0.9.34"' not in t:
    raise SystemExit('Expected v0.9.34 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.34"','PLUGIN_VERSION = "0.9.35"',1)

# Python stdlib HTTP server; no external web/cloud dependency.
import_anchor='''except ImportError:\n    from urllib2 import urlopen, Request\n    from urlparse import urlparse, parse_qs\n    from urllib import urlencode, quote, unquote\n'''
if import_anchor not in t:
    raise SystemExit('urllib import anchor missing')
http_import='''\ntry:\n    from http.server import BaseHTTPRequestHandler, HTTPServer\nexcept ImportError:\n    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer\n'''
t=t.replace(import_anchor,import_anchor+http_import,1)

profile_anchor='class EpiProfileSelect(Screen):\n'
if profile_anchor not in t:
    raise SystemExit('EpiProfileSelect anchor missing')

web_code=r'''WEB_PLAYLIST_SETUP_SKIN = build_fullscreen_skin(
    "EpiWebPlaylistSetup",
    overlay_pixmap(SETTINGS_GLASS_OVERLAY) +
    logo_widget(w=300, h=100) +
    label_widget("title", 380, 28, 845, 48, 29, "right") +
    label_widget("subtitle", 380, 78, 845, 30, 17, "right", fg="#9EADBF") +
    label_widget("url", 100, 180, 1080, 58, 25, "center", "center", "#101722", "#FFFFFF") +
    label_widget("pin", 390, 270, 500, 78, 40, "center", "center", "#141B27", "#FFFFFF") +
    label_widget("status", 100, 385, 1080, 120, 20, "center", "center", "#0D121B", "#E7EEF7") +
    label_widget("info", 100, 530, 1080, 55, 17, "center", "center", None, "#9EADBF") +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)


def _playlist_web_local_ip():
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        value = clean_text(sock.getsockname()[0])
        if value and not value.startswith("127."):
            return value
    except Exception:
        pass
    finally:
        try:
            if sock is not None:
                sock.close()
        except Exception:
            pass
    try:
        value = clean_text(socket.gethostbyname(socket.gethostname()))
        if value and not value.startswith("127."):
            return value
    except Exception:
        pass
    return "127.0.0.1"


def _playlist_web_valid_http_url(value):
    value = clean_text(value)
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return clean_text(parsed.scheme).lower() in ("http", "https") and bool(clean_text(parsed.netloc))


def _playlist_web_xtream_url(server, username, password):
    server = clean_text(server).rstrip("/")
    username = clean_text(username)
    password = clean_text(password)
    if not _playlist_web_valid_http_url(server):
        raise ValueError("Server muss mit http:// oder https:// beginnen.")
    if not username or not password:
        raise ValueError("Benutzername und Passwort fehlen.")
    parsed = urlparse(server)
    path = clean_text(parsed.path or "").rstrip("/")
    if path.lower().endswith("/get.php"):
        server = server[:-(len("/get.php"))]
    query = urlencode({"username": username, "password": password, "type": "m3u_plus", "output": "ts"})
    return server.rstrip("/") + "/get.php?" + query


def _playlist_web_page(message="", ok=False):
    banner = ""
    if message:
        cls = "ok" if ok else "err"
        banner = '<div class="%s">%s</div>' % (cls, message)
    return '''<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Epi MediaHub Web-Setup</title>
<style>
body{font-family:Arial,sans-serif;background:#0b111a;color:#eef4fb;margin:0;padding:24px} .card{max-width:720px;margin:auto;background:#131d2a;border-radius:18px;padding:26px;box-shadow:0 10px 35px #0008} h1{margin-top:0} label{display:block;margin-top:16px;color:#b9c7d8} input,select{box-sizing:border-box;width:100%%;padding:13px;margin-top:6px;border:1px solid #30435a;border-radius:9px;background:#0d1520;color:#fff;font-size:16px} button{margin-top:22px;width:100%%;padding:15px;border:0;border-radius:10px;background:#267a42;color:white;font-size:18px;font-weight:bold}.hint{color:#94a9bf;font-size:14px;line-height:1.45}.ok,.err{padding:12px;border-radius:9px;margin:10px 0}.ok{background:#173e26}.err{background:#4b2027}.section{margin-top:18px;padding-top:4px}.hidden{display:none}</style>
<script>function modeChanged(){var m=document.getElementById('mode').value;document.getElementById('m3u').className=m==='m3u'?'section':'section hidden';document.getElementById('xtream').className=m==='xtream'?'section':'section hidden';}</script>
</head><body><div class="card"><h1>Epi MediaHub</h1><p>Playlist bequem am Handy oder Computer einrichten.</p>''' + banner + '''
<form method="post" action="/save" autocomplete="off">
<label>Setup-PIN vom Fernseher<input name="pin" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required></label>
<label>Name der Playlist<input name="name" value="Playlist" maxlength="80" required></label>
<label>Art<select name="mode" id="mode" onchange="modeChanged()"><option value="m3u">M3U / M3U-Plus URL</option><option value="xtream">Xtream Zugangsdaten</option></select></label>
<div id="m3u" class="section"><label>M3U-URL<input name="m3u_url" placeholder="http://server/.../get.php?..." inputmode="url"></label></div>
<div id="xtream" class="section hidden"><label>Xtream Server<input name="server" placeholder="http://server:port" inputmode="url"></label><label>Benutzername<input name="username" autocomplete="username"></label><label>Passwort<input name="password" type="password" autocomplete="current-password"></label></div>
<button type="submit">An Receiver senden</button></form>
<p class="hint">Die Einrichtung läuft nur lokal über deinen Receiver. Der Setup-Code ist zeitlich begrenzt. Zugangsdaten werden nicht an EpiMediaHub oder einen Cloud-Dienst übertragen.</p>
</div><script>modeChanged()</script></body></html>'''


class _EpiPlaylistWebHandler(BaseHTTPRequestHandler):
    server_version = "EpiMediaHubSetup/1.0"

    def log_message(self, fmt, *args):
        return

    def _send_html(self, code, page):
        try:
            raw = page.encode("utf-8")
        except Exception:
            raw = page
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except Exception:
            pass

    def do_GET(self):
        path = clean_text(self.path).split("?", 1)[0]
        if path not in ("/", "/index.html"):
            self._send_html(404, _playlist_web_page("Seite nicht gefunden."))
            return
        if time.time() > float(getattr(self.server, "epi_expires", 0) or 0):
            self._send_html(410, _playlist_web_page("Der Setup-Code ist abgelaufen. Am Fernseher BLAU für einen neuen Code drücken."))
            return
        self._send_html(200, _playlist_web_page())

    def do_POST(self):
        path = clean_text(self.path).split("?", 1)[0]
        if path != "/save":
            self._send_html(404, _playlist_web_page("Seite nicht gefunden."))
            return
        if time.time() > float(getattr(self.server, "epi_expires", 0) or 0):
            self._send_html(410, _playlist_web_page("Der Setup-Code ist abgelaufen."))
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except Exception:
            length = 0
        if length <= 0 or length > 32768:
            self._send_html(413, _playlist_web_page("Ungültige Anfrage."))
            return
        try:
            body = self.rfile.read(length)
            if not isinstance(body, str):
                body = body.decode("utf-8", "replace")
            form = parse_qs(body, keep_blank_values=True)
            first = lambda key: clean_text((form.get(key) or [""])[0])
            if first("pin") != clean_text(getattr(self.server, "epi_pin", "")):
                self._send_html(403, _playlist_web_page("Setup-PIN ist falsch."))
                return
            name = first("name")[:80] or "Playlist"
            mode = first("mode").lower()
            if mode == "xtream":
                url = _playlist_web_xtream_url(first("server"), first("username"), first("password"))
            else:
                url = first("m3u_url")
                if not _playlist_web_valid_http_url(url):
                    raise ValueError("M3U-URL muss mit http:// oder https:// beginnen.")
            lock = getattr(self.server, "epi_lock", None)
            if lock is not None:
                lock.acquire()
            try:
                if getattr(self.server, "epi_pending", None) is not None:
                    self._send_html(409, _playlist_web_page("Der Receiver verarbeitet bereits eine Playlist."))
                    return
                self.server.epi_pending = {"name": name, "url": url, "mode": mode}
            finally:
                if lock is not None:
                    lock.release()
            self._send_html(200, _playlist_web_page("Daten wurden an den Receiver gesendet. Bitte jetzt auf den Fernseher schauen.", True))
        except Exception as error:
            self._send_html(400, _playlist_web_page(clean_text(error) or "Eingaben konnten nicht übernommen werden."))


class _EpiPlaylistWebServer(HTTPServer):
    allow_reuse_address = True


def _playlist_web_serve(server, stop_event):
    try:
        server.timeout = 0.35
        while not stop_event.is_set():
            server.handle_request()
    except Exception:
        pass
    try:
        server.server_close()
    except Exception:
        pass


class EpiWebPlaylistSetup(Screen):
    skin = WEB_PLAYLIST_SETUP_SKIN

    def __init__(self, session):
        Screen.__init__(self, session)
        self["logo"] = Pixmap()
        self["title"] = Label("PLAYLIST WEB-SETUP")
        self["subtitle"] = Label("Einrichtung über Handy oder Computer im selben Netzwerk")
        self["url"] = Label("Webserver wird gestartet ...")
        self["pin"] = Label("------")
        self["status"] = Label("Öffne die angezeigte Adresse im Browser und gib dort den PIN ein.")
        self["info"] = Label("Keine Cloud · keine Anmeldung · Setup-Code 15 Minuten gültig")
        self["red"] = Label("ROT  Zurück")
        self["green"] = Label("GRÜN  Fertig")
        self["yellow"] = Label("")
        self["blue"] = Label("BLAU  Neuer Code")
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "cancel": self.closeSetup, "red": self.closeSetup,
            "green": self.finishSetup, "ok": self.finishSetup,
            "blue": self.restartServer
        }, -10)
        self._server = None
        self._server_thread = None
        self._server_stop = None
        self._saved_profile_id = ""
        self._download_job = None
        self._download_result = None
        self._poll_timer = eTimer()
        connect_timer(self._poll_timer, self._pollServer)
        try:
            self.onLayoutFinish.append(self.restartServer)
            self.onClose.append(self._stopServer)
        except Exception:
            pass

    def _stopServer(self):
        server = self._server
        stop = self._server_stop
        self._server = None
        self._server_stop = None
        if stop is not None:
            try: stop.set()
            except Exception: pass
        try:self._poll_timer.stop()
        except Exception:pass
        if server is not None:
            try:
                # handle_request has a short timeout; no blocking shutdown on GUI thread.
                pass
            except Exception:
                pass

    def restartServer(self):
        self._stopServer()
        pin = "%06d" % ((uuid.uuid4().int % 900000) + 100000)
        expires = time.time() + 15 * 60
        server = None
        port = None
        for candidate in range(8765, 8771):
            try:
                server = _EpiPlaylistWebServer(("0.0.0.0", candidate), _EpiPlaylistWebHandler)
                port = candidate
                break
            except Exception:
                server = None
        if server is None:
            self["url"].setText("Webserver konnte nicht gestartet werden")
            self["pin"].setText("------")
            self["status"].setText("Die Ports 8765-8770 sind belegt. BLAU drücken, um es erneut zu versuchen.")
            return
        server.epi_pin = pin
        server.epi_expires = expires
        server.epi_pending = None
        server.epi_lock = threading.Lock()
        stop = threading.Event()
        thread = threading.Thread(target=_playlist_web_serve, args=(server, stop))
        thread.daemon = True
        self._server = server
        self._server_stop = stop
        self._server_thread = thread
        thread.start()
        ip = _playlist_web_local_ip()
        self["url"].setText("http://%s:%d/" % (ip, port))
        self["pin"].setText(pin)
        self["status"].setText("1. Adresse am Handy/PC öffnen\n2. PIN eingeben\n3. M3U oder Xtream eintragen und senden")
        try:self._poll_timer.start(300, True)
        except TypeError:self._poll_timer.start(300)

    def _takePending(self):
        server = self._server
        if server is None:
            return None
        lock = getattr(server, "epi_lock", None)
        if lock is not None:
            lock.acquire()
        try:
            value = getattr(server, "epi_pending", None)
            server.epi_pending = None
            return value
        finally:
            if lock is not None:
                lock.release()

    def _acceptPending(self, payload):
        name = clean_text(payload.get("name", ""))[:80] or "Playlist"
        url = clean_text(payload.get("url", ""))
        if not _playlist_web_valid_http_url(url):
            self["status"].setText("Ungültige Playlist-URL empfangen.")
            return
        profile = default_profile(name, url)
        data = load_profiles()
        data.setdefault("profiles", []).append(profile)
        data["active_id"] = profile["id"]
        save_profiles(data)
        self._saved_profile_id = profile["id"]
        self["status"].setText("Playlist gespeichert. Verbindung und Inhalte werden im Hintergrund geprüft ...")
        self._download_result = None
        self._download_job = threading.Thread(target=self._downloadWorker, args=(dict(profile),))
        self._download_job.daemon = True
        self._download_job.start()

    def _downloadWorker(self, profile):
        try:
            count = int(download_playlist(profile))
            profile["last_update"] = time.strftime("%d.%m.%Y %H:%M")
            if profile.get("m3u_url") and clean_text(profile.get("source_mode", "")) != "xtream":
                profile["expiry"] = try_fetch_expiry(profile.get("m3u_url", ""))
            self._download_result = (True, profile, count, "")
        except Exception as error:
            self._download_result = (False, profile, 0, clean_text(error))

    def _pollServer(self):
        payload = None
        if self._download_job is None:
            payload = self._takePending()
        if payload:
            self._acceptPending(payload)
        if self._download_job is not None and not self._download_job.is_alive():
            result = self._download_result
            self._download_job = None
            self._download_result = None
            if result:
                ok, profile, count, error = result
                update_profile(profile)
                if ok:
                    mode = "FAST API / Xtream" if clean_text(profile.get("source_mode", "")) == "xtream" else "M3U"
                    self["status"].setText("Playlist bereit. %s wurde erkannt; %d Kategorien/Einträge vorbereitet.\nGRÜN = Weiter" % (mode, count))
                    self["green"].setText("GRÜN  Weiter")
                else:
                    self["status"].setText("Playlist wurde gespeichert, konnte aber noch nicht geladen werden:\n%s\nGRÜN = Zur Playlist-Verwaltung" % (error or "Server nicht erreichbar"))
                    self["green"].setText("GRÜN  Weiter")
        if self._server is not None:
            if time.time() > float(getattr(self._server, "epi_expires", 0) or 0):
                self["info"].setText("Setup-Code abgelaufen · BLAU = neuen Code erzeugen")
            try:self._poll_timer.start(300, True)
            except TypeError:self._poll_timer.start(300)

    def finishSetup(self):
        if self._download_job is not None and self._download_job.is_alive():
            self["status"].setText("Die Playlist wird noch geprüft. Bitte einen Moment später GRÜN drücken.")
            return
        self.close(self._saved_profile_id or None)

    def closeSetup(self):
        self.close(None)


'''
t=t.replace(profile_anchor,web_code+profile_anchor,1)

# Integrate into the existing profile selector. Blue becomes Web Setup; MENU remains Help.
old_blue='self["blue"] = Label("BLAU  %s" % tr("help"))'
if old_blue not in t:
    raise SystemExit('profile blue label anchor missing')
t=t.replace(old_blue,'self["blue"] = Label("BLAU  Web-Setup")',1)
old_actions='''{"ok": self.openSelected, "cancel": self.requestExit, "red": self.deleteSelected,\n             "green": self.addProfile, "yellow": self.editSelected, "blue": self.openHelp,\n             "menu": self.openHelp}, -1'''
if old_actions not in t:
    raise SystemExit('profile action map anchor missing')
new_actions='''{"ok": self.openSelected, "cancel": self.requestExit, "red": self.deleteSelected,\n             "green": self.addProfile, "yellow": self.editSelected, "blue": self.openWebSetup,\n             "menu": self.openHelp}, -1'''
t=t.replace(old_actions,new_actions,1)

# Auto-open browser setup exactly once when no playlist profile exists.
init_anchor='''        self._health_timer = eTimer()\n        connect_timer(self._health_timer, self._pollHealthJob)\n        try:\n            self.onClose.append(self._stopExpiryJob)'''
if init_anchor not in t:
    raise SystemExit('profile init callback anchor missing')
init_new='''        self._health_timer = eTimer()\n        connect_timer(self._health_timer, self._pollHealthJob)\n        self._web_setup_auto_shown = False\n        try:\n            self.onLayoutFinish.append(self._autoWebSetupIfEmpty)\n        except Exception:\n            pass\n        try:\n            self.onClose.append(self._stopExpiryJob)'''
t=t.replace(init_anchor,init_new,1)

# Make empty-state guidance explicit.
old_empty='rows = ["%s - GRÜN / GREEN" % tr("no_playlist")]'
if old_empty not in t:
    raise SystemExit('empty playlist row anchor missing')
t=t.replace(old_empty,'rows = ["%s - BLAU = Web-Setup   |   GRÜN = URL" % tr("no_playlist")]',1)
old_info='self["info"].setText("Schnellimport: %s   |   M3U-Dateien: %s" % (PLAYLIST_TEXT_FILE, FTP_PLAYLIST_DIR))'
if old_info not in t:
    raise SystemExit('profile info anchor missing')
t=t.replace(old_info,'self["info"].setText("BLAU = Web-Setup   |   MENU = Hilfe   |   Schnellimport: %s" % PLAYLIST_TEXT_FILE)',1)

method_anchor='''    def requestExit(self):\n        self.session.openWithCallback(self._exitConfirmed, EpiExitConfirm)\n'''
if method_anchor not in t:
    raise SystemExit('profile requestExit anchor missing')
web_methods='''    def _autoWebSetupIfEmpty(self):\n        if self._web_setup_auto_shown:\n            return\n        self._web_setup_auto_shown = True\n        self.data = load_profiles()\n        self.profiles = self.data.get("profiles", [])\n        if not self.profiles:\n            self.openWebSetup()\n\n    def openWebSetup(self):\n        self.session.openWithCallback(self._webSetupClosed, EpiWebPlaylistSetup)\n\n    def _webSetupClosed(self, profile_id=None):\n        scan_local_playlists()\n        self.data = load_profiles()\n        self.profiles = self.data.get("profiles", [])\n        self.refreshList()\n        if profile_id:\n            set_active_profile(profile_id)\n            self.close(profile_id)\n            return\n        self._startHealthJob()\n        self._startExpiryJob()\n\n'''
t=t.replace(method_anchor,web_methods+method_anchor,1)

p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.35/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.35 local browser playlist setup for M3U and Xtream/' "$T/control/control"

python3 -m py_compile "$P"
grep -q 'PLUGIN_VERSION = "0.9.35"' "$P"
grep -q 'class EpiWebPlaylistSetup(Screen)' "$P"
grep -q 'class _EpiPlaylistWebHandler(BaseHTTPRequestHandler)' "$P"
grep -q 'from http.server import BaseHTTPRequestHandler, HTTPServer' "$P"
grep -q 'def _playlist_web_xtream_url' "$P"
grep -q 'type.*m3u_plus.*output.*ts' "$P"
grep -q 'epi_expires' "$P"
grep -q '_web_setup_auto_shown' "$P"
grep -q 'self.onLayoutFinish.append(self._autoWebSetupIfEmpty)' "$P"
grep -q '"blue": self.openWebSetup' "$P"
grep -q 'BLAU  Web-Setup' "$P"
# Existing Mediathek fixes and safety features must survive.
grep -q 'class EpiMediathekPlayer(MoviePlayer)' "$P"
grep -q 'directory_back_parent_ok' "$P"
grep -q 'list_back_parent_ok' "$P"
grep -q 'home_back_parent_ok' "$P"
# Family / normal parental controls must survive unchanged.
grep -q 'FAMILY_PIN_HASH' "$P"
grep -q 'family_skins_unlocked' "$P"
grep -q '_familyPinEntered' "$P"
grep -q 'parental_pin_hash' "$P"
python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
need=[
 'class EpiWebPlaylistSetup(Screen):',
 'class _EpiPlaylistWebHandler(BaseHTTPRequestHandler):',
 'server.epi_pending = {"name": name, "url": url, "mode": mode}',
 'self.session.openWithCallback(self._webSetupClosed, EpiWebPlaylistSetup)',
 'self.onLayoutFinish.append(self._autoWebSetupIfEmpty)',
 'if not self.profiles:\n            self.openWebSetup()',
 'urlencode({"username": username, "password": password, "type": "m3u_plus", "output": "ts"})',
 'length > 32768',
 'time.time() + 15 * 60',
]
for x in need:
    if x not in t: raise SystemExit('v0.9.35 guard missing: '+x)
# Never log or display passwords in the browser setup implementation.
a=t.index('class _EpiPlaylistWebHandler'); b=t.index('class EpiProfileSelect(Screen):',a); w=t[a:b]
if 'log_message' not in w or 'return\n' not in w:
    raise SystemExit('HTTP access-log suppression missing')
# Rai-specific app PIN must remain absent while Family PIN remains elsewhere.
ms=t.index('class EpiMediathekHome(Screen):'); me=t.index('class EpiMediaHubHome(Screen):',ms); m=t[ms:me]
if '_pin_done' in m or 'Rai' in m and 'openWithCallback(self._pin' in m:
    raise SystemExit('Rai provider PIN gate reintroduced')
print('v0.9.35 local web playlist setup guard: OK')
PY

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.35.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"
if ar p EpiMediaHub_v0.9.35.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.35.ipk)
echo "v0.9.35 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.35.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.35.ipk" > EpiMediaHub_v0.9.35.ipk.sha256
printf '{\n  "version": "0.9.35",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.35.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.35.ipk.sha256
rm -f EpiMediaHub_v0.9.34.ipk EpiMediaHub_v0.9.34.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.35 local web playlist setup'
git push
