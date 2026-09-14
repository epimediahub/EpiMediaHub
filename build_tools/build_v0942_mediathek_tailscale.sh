#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.41.ipk"
T=/tmp/epimedia0942
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

if t.count('PLUGIN_VERSION = "0.9.41"') != 1:
    raise SystemExit('Expected exactly one v0.9.41 version marker')
t=t.replace('PLUGIN_VERSION = "0.9.41"','PLUGIN_VERSION = "0.9.42"',1)

# Mediathek HLS on the tested OpenATV 7.6 / GigaBlue does not start through
# service type 1. Keep the v0.9.39 native type-1 path for Live/VOD/Replay,
# but return only the public Mediathek playback route to ServiceMP3/GStreamer.
old='''def _open_mediathek_stream(session,url,title="Mediathek",source=""):\n    url=clean_text(url)\n    title=clean_text(title) or "Mediathek"\n    if not url:\n        raise RuntimeError("Kein abspielbarer Stream gefunden.")\n    ref=eServiceReference(1,0,url)'''
new='''def _open_mediathek_stream(session,url,title="Mediathek",source=""):\n    url=clean_text(url)\n    title=clean_text(title) or "Mediathek"\n    if not url:\n        raise RuntimeError("Kein abspielbarer Stream gefunden.")\n    # Public Mediathek sources are predominantly HLS. On OpenATV 7.6 the\n    # native DVB service type 1 can reject these URLs before GStreamer opens\n    # them, while 4097 handles the same HLS stream correctly.\n    ref=eServiceReference(4097,0,url)'''
if old not in t:
    raise SystemExit('Mediathek playback anchor missing')
t=t.replace(old,new,1)

# Remote-access UI and setup helpers. Tailscale packages are installed from the
# receiver feed at setup time; no auth key or account secret is embedded.
anchor='class EpiMediaHubHome(Screen):\n'
if anchor not in t:
    raise SystemExit('Home class anchor missing')
remote=r'''TAILSCALE_QR_PATH = "/tmp/epimediahub_tailscale_qr.png"


def _tailscale_binary(name):
    for path in ("/usr/bin/%s" % name, "/usr/sbin/%s" % name, "/bin/%s" % name, "/sbin/%s" % name):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    try:
        return shutil.which(name) or ""
    except Exception:
        return ""


def _tailscale_ip():
    cmd = _tailscale_binary("tailscale")
    if not cmd:
        return ""
    try:
        proc = subprocess.Popen([cmd, "ip", "-4"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.communicate()[0]
        if not isinstance(out, str):
            out = out.decode("utf-8", "ignore")
        if proc.returncode == 0:
            for line in out.splitlines():
                value = clean_text(line)
                if re.match(r"^100\\.\\d+\\.\\d+\\.\\d+$", value):
                    return value
    except Exception:
        pass
    return ""


def _tailscale_state_text():
    ip = _tailscale_ip()
    if ip:
        return "Verbunden · %s" % ip
    if _tailscale_binary("tailscale"):
        return "Installiert · nicht verbunden"
    return "Nicht eingerichtet"


def _tailscale_make_qr(value):
    value = clean_text(value)
    if not value:
        return False
    try:
        vendor = os.path.join(PLUGIN_DIR, "vendor")
        if vendor not in sys.path:
            sys.path.insert(0, vendor)
        import segno
        qr = segno.make_qr(value, error="m")
        qr.save(TAILSCALE_QR_PATH, kind="png", scale=9, border=2, dark="#000000", light="#FFFFFF")
        try: os.chmod(TAILSCALE_QR_PATH, 0o600)
        except Exception: pass
        return os.path.isfile(TAILSCALE_QR_PATH) and os.path.getsize(TAILSCALE_QR_PATH) > 0
    except Exception:
        return False


def _tailscale_remove_qr():
    try:
        if os.path.exists(TAILSCALE_QR_PATH):
            os.remove(TAILSCALE_QR_PATH)
    except Exception:
        pass


TAILSCALE_SETUP_SKIN = WEB_PLAYLIST_SETUP_SKIN


class EpiTailscaleSetup(Screen):
    skin = TAILSCALE_SETUP_SKIN

    def __init__(self, session):
        Screen.__init__(self, session)
        self["logo"] = Pixmap()
        self["title"] = Label("FERNZUGRIFF")
        self["subtitle"] = Label("Tailscale · sicherer Zugriff ohne Portfreigabe")
        self["qr"] = Pixmap()
        self["url"] = Label("")
        self["pin"] = Label("")
        self["status"] = Label("Status wird geprüft …")
        self["info"] = Label("Kein Auth-Key im Plugin · Freigabe einmalig per QR-Code")
        self["red"] = Label("ROT  Zurück")
        self["green"] = Label("GRÜN  Einrichten")
        self["yellow"] = Label("")
        self["blue"] = Label("BLAU  Status aktualisieren")
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "cancel": self.closeSetup, "red": self.closeSetup,
            "green": self.startSetup, "ok": self.startSetup,
            "blue": self.refreshStatus
        }, -10)
        self._job = None
        self._result = None
        self._tailscale_proc = None
        self._poll_timer = eTimer()
        connect_timer(self._poll_timer, self._pollJob)
        try:
            self.onLayoutFinish.append(self.refreshStatus)
            self.onClose.append(self._cleanup)
        except Exception:
            pass

    def _timer(self, delay=500):
        try:self._poll_timer.start(delay, True)
        except TypeError:self._poll_timer.start(delay)
        except Exception:pass

    def _setQr(self, url=""):
        try:self["qr"].hide()
        except Exception:pass
        _tailscale_remove_qr()
        if url and _tailscale_make_qr(url):
            try:
                if self["qr"].instance is not None:
                    self["qr"].instance.setPixmapFromFile(TAILSCALE_QR_PATH)
                    self["qr"].show()
            except Exception:
                pass

    def refreshStatus(self):
        ip = _tailscale_ip()
        if ip:
            self._setQr("")
            self["pin"].setText(ip)
            self["url"].setText("")
            self["status"].setText("Fernzugriff ist aktiv.\\nSSH/SFTP/Webinterface sind über die Tailscale-IP erreichbar.")
            self["green"].setText("GRÜN  Bereits eingerichtet")
        elif _tailscale_binary("tailscale"):
            self["pin"].setText("")
            self["status"].setText("Tailscale ist installiert, aber diese Box ist noch nicht angemeldet.\\nGRÜN drücken, um die Verbindung einzurichten.")
            self["green"].setText("GRÜN  Einrichten")
        else:
            self["pin"].setText("")
            self["status"].setText("Tailscale ist noch nicht installiert.\\nGRÜN installiert und konfiguriert den Fernzugriff automatisch.")
            self["green"].setText("GRÜN  Installieren & einrichten")

    def startSetup(self):
        if self._job is not None and self._job.is_alive():
            return
        ip = _tailscale_ip()
        if ip:
            self.refreshStatus()
            return
        self._result = ("progress", "Tailscale wird eingerichtet …", "")
        self["status"].setText("Tailscale wird eingerichtet …\\nBitte Receiver eingeschaltet lassen.")
        self["green"].setText("GRÜN  Bitte warten …")
        self._job = threading.Thread(target=self._setupWorker)
        self._job.daemon = True
        self._job.start()
        self._timer(250)

    def _run(self, args):
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.communicate()[0]
        if not isinstance(out, str):
            out = out.decode("utf-8", "ignore")
        return proc.returncode, out

    def _setupWorker(self):
        try:
            if not _tailscale_binary("tailscale") or not _tailscale_binary("tailscaled"):
                self._result = ("progress", "Pakete werden geladen …", "")
                self._run(["opkg", "update"])
                code, out = self._run(["opkg", "install", "tailscale", "tailscaled"])
                if code != 0:
                    raise RuntimeError("Tailscale-Pakete konnten nicht installiert werden.\\n%s" % clean_text(out[-800:]))

            try:
                if not os.path.isdir("/etc/modules-load.d"):
                    os.makedirs("/etc/modules-load.d")
                with open("/etc/modules-load.d/tun.conf", "w") as handle:
                    handle.write("tun\\n")
            except Exception as error:
                raise RuntimeError("TUN-Autostart konnte nicht eingerichtet werden: %s" % error)

            self._run(["modprobe", "tun"])
            if os.path.isfile("/usr/sbin/update-rc.d"):
                self._run(["/usr/sbin/update-rc.d", "tailscaled", "defaults"])
            elif _tailscale_binary("update-rc.d"):
                self._run([_tailscale_binary("update-rc.d"), "tailscaled", "defaults"])
            if os.path.isfile("/etc/init.d/tailscaled"):
                self._run(["/etc/init.d/tailscaled", "start"])
            time.sleep(1.0)

            ip = _tailscale_ip()
            if ip:
                self._result = ("connected", ip, "")
                return

            cmd = _tailscale_binary("tailscale")
            if not cmd:
                raise RuntimeError("tailscale wurde nach der Installation nicht gefunden.")
            proc = subprocess.Popen([cmd, "up"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            self._tailscale_proc = proc
            output = ""
            auth_url = ""
            deadline = time.time() + 35
            while time.time() < deadline:
                line = proc.stdout.readline() if proc.stdout is not None else ""
                if line:
                    output += line
                    match = re.search(r"https://login\\.tailscale\\.com/a/[A-Za-z0-9_-]+", output)
                    if match:
                        auth_url = match.group(0)
                        self._result = ("auth", auth_url, "")
                        break
                if proc.poll() is not None:
                    break
                time.sleep(0.1)

            if not auth_url:
                match = re.search(r"https://login\\.tailscale\\.com/a/[A-Za-z0-9_-]+", output)
                if match:
                    auth_url = match.group(0)
                    self._result = ("auth", auth_url, "")

            # Keep watching after the URL has been shown. Authentication happens
            # on the user's phone/browser; once approved, the IP appears here.
            wait_deadline = time.time() + 240
            while time.time() < wait_deadline:
                ip = _tailscale_ip()
                if ip:
                    self._result = ("connected", ip, "")
                    return
                time.sleep(1.0)

            if auth_url:
                self._result = ("auth", auth_url, "Freigabe noch nicht abgeschlossen.")
            else:
                raise RuntimeError("Kein Tailscale-Anmeldelink erhalten. Bitte BLAU drücken und erneut versuchen.\\n%s" % clean_text(output[-800:]))
        except Exception as error:
            self._result = ("error", clean_text(error), "")

    def _pollJob(self):
        result = self._result
        if result:
            kind, value, extra = result
            if kind == "progress":
                self["status"].setText(value)
            elif kind == "auth":
                self._setQr(value)
                self["url"].setText(value)
                self["pin"].setText("QR SCANNEN")
                text = "QR-Code scannen und die Box im Tailscale-Konto freigeben."
                if extra:
                    text += "\\n" + extra
                self["status"].setText(text)
                self["green"].setText("GRÜN  Verbindung prüfen")
            elif kind == "connected":
                self._setQr("")
                self["url"].setText("")
                self["pin"].setText(value)
                self["status"].setText("Fernzugriff aktiv.\\nDie Box startet Tailscale künftig automatisch mit OpenATV.")
                self["green"].setText("GRÜN  Bereits eingerichtet")
            elif kind == "error":
                self._setQr("")
                self["pin"].setText("FEHLER")
                self["status"].setText(value)
                self["green"].setText("GRÜN  Erneut versuchen")
        if self._job is not None and self._job.is_alive():
            self._timer(500)
        elif result and result[0] == "connected":
            self._job = None
        elif self._job is not None:
            self._job = None

    def closeSetup(self):
        self.close()

    def _cleanup(self):
        try:self._poll_timer.stop()
        except Exception:pass
        _tailscale_remove_qr()


'''
t=t.replace(anchor, remote+anchor, 1)

# Add the remote-access status row to Settings.
rows_anchor='''            ("autostart", "%s: %s" % (tr("autostart"), tr("yes") if self.settings.get("autostart_app", False) else tr("no"))),\n            ("help", tr("playlist_help")),'''
rows_new='''            ("autostart", "%s: %s" % (tr("autostart"), tr("yes") if self.settings.get("autostart_app", False) else tr("no"))),\n            ("remoteaccess", "Fernzugriff (Tailscale): %s" % _tailscale_state_text()),\n            ("help", tr("playlist_help")),'''
if rows_anchor not in t:
    raise SystemExit('Settings rows anchor missing')
t=t.replace(rows_anchor, rows_new, 1)

edit_anchor='''        elif key == "help":\n            self.openHelp()'''
edit_new='''        elif key == "remoteaccess":\n            self.session.openWithCallback(self._remoteAccessClosed, EpiTailscaleSetup)\n        elif key == "help":\n            self.openHelp()'''
if edit_anchor not in t:
    raise SystemExit('Settings action anchor missing')
t=t.replace(edit_anchor, edit_new, 1)

method_anchor='''    def _familyPinEntered(self, pin):\n'''
method_new='''    def _remoteAccessClosed(self, *args):\n        self.refresh()\n\n    def _familyPinEntered(self, pin):\n'''
if method_anchor not in t:
    raise SystemExit('Settings callback anchor missing')
t=t.replace(method_anchor, method_new, 1)

# Release notes.
notes_anchor='_RELEASE_NOTES = {'
if notes_anchor not in t:
    raise SystemExit('Release notes anchor missing')
notes='''_RELEASE_NOTES = {\n    "0.9.42": {\n        "de": ["Mediathek-Wiedergabe auf OpenATV 7.6 repariert: öffentliche HLS-Videos nutzen wieder den kompatiblen 4097-GStreamer-Pfad; Live/VOD/Replay behalten den funktionierenden nativen Player-Pfad.", "Neu unter Einstellungen: Fernzugriff (Tailscale). Installation, TUN-Modul und Autostart werden automatisch eingerichtet; neue Boxen werden einmalig sicher per QR-Code freigegeben.", "Es wird kein Tailscale-Auth-Key im Plugin oder Repository gespeichert."],\n        "en": ["Fixed Mediathek playback on OpenATV 7.6 by routing public HLS video through the compatible 4097 GStreamer service while keeping the working native path for Live/VOD/Replay.", "New Settings entry for Tailscale remote access with automatic package/TUN/autostart setup and one-time QR authorization.", "No Tailscale auth key is embedded in the plugin or repository."],\n    },'''
t=t.replace(notes_anchor, notes, 1)

p.write_text(t, encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.42/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.42 Mediathek playback and Tailscale remote access/' "$T/control/control"

python3 -m py_compile "$P"
find "$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub" -type d -name __pycache__ -prune -exec rm -rf {} +

# New v0.9.42 guards.
grep -Fq 'PLUGIN_VERSION = "0.9.42"' "$P"
grep -Fq 'ref=eServiceReference(4097,0,url)' "$P"
grep -Fq 'class EpiTailscaleSetup(Screen)' "$P"
grep -Fq '("remoteaccess", "Fernzugriff (Tailscale): %s" % _tailscale_state_text())' "$P"
grep -Fq 'opkg", "install", "tailscale", "tailscaled"' "$P"
grep -Fq 'with open("/etc/modules-load.d/tun.conf", "w")' "$P"
grep -Fq 'update-rc.d", "tailscaled", "defaults"' "$P"
grep -Fq 'https://login\\.tailscale\\.com/a/' "$P"

# Existing safety/features must remain.
grep -Fq 'class EpiMediathekPlayer(MoviePlayer)' "$P"
grep -Fq 'directory_back_parent_ok' "$P"
grep -Fq 'list_back_parent_ok' "$P"
grep -Fq 'home_back_parent_ok' "$P"
grep -Fq 'class EpiEPGGridScreen(Screen)' "$P"
grep -Fq 'def xtream_catchup_url' "$P"
grep -Fq 'class EpiWebPlaylistSetup(Screen)' "$P"
grep -Fq 'def _playlist_web_generate_qr' "$P"
grep -Fq 'FAMILY_PIN_HASH' "$P"
grep -Fq 'family_skins_unlocked' "$P"
grep -Fq 'parental_pin_hash' "$P"
grep -Fq 'log_path = "/tmp/epimediahub_update.log"' "$P"
grep -Fq '["opkg", "install", target]' "$P"

python3 - <<'PY'
import os,re
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
# Mediathek alone is restored to 4097; the remaining native playback refs stay intact.
if t.count('eServiceReference(4097,0,url)') != 1:
    raise SystemExit('Expected exactly one Mediathek 4097 compact ref')
if len(re.findall(r'eServiceReference\(\s*1\s*,',t)) != 5:
    raise SystemExit('Expected five remaining native type-1 playback refs')
ms=t.index('class EpiMediathekHome(Screen):'); me=t.index('class EpiMediaHubHome(Screen):',ms); m=t[ms:me]
if '_pin_done' in m or ('Rai' in m and 'openWithCallback(self._pin' in m):
    raise SystemExit('Rai provider PIN gate reintroduced')
# Never embed a reusable Tailscale auth key.
if re.search(r'tskey-[A-Za-z0-9_-]+', t):
    raise SystemExit('Embedded Tailscale auth key detected')
print('v0.9.42 regression/security guards: OK')
PY

sh -n "$T/control/preinst"
sh -n "$T/control/postinst"

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.42.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"

ar t EpiMediaHub_v0.9.42.ipk | grep -Fxq debian-binary
ar t EpiMediaHub_v0.9.42.ipk | grep -Fxq control.tar.gz
ar t EpiMediaHub_v0.9.42.ipk | grep -Fxq data.tar.gz
if ar p EpiMediaHub_v0.9.42.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.42.ipk)
echo "v0.9.42 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.42.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.42.ipk" > EpiMediaHub_v0.9.42.ipk.sha256
printf '{\n  "version": "0.9.42",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.42.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.42.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add EpiMediaHub_v0.9.42.ipk EpiMediaHub_v0.9.42.ipk.sha256 update.json
git commit -m 'Publish EpiMediaHub v0.9.42 Mediathek and Tailscale remote access'
git push
