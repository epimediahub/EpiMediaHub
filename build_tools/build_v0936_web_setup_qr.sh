#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.35.ipk"
T=/tmp/epimedia0936
P="$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub/plugin.py"
VENDOR="$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub/vendor"

rm -rf "$T"
mkdir -p "$T/ar" "$T/data" "$T/control" "$T/pkg" "$VENDOR"
cd "$T/ar"
ar x "$B"
tar -xzf data.tar.gz -C ../data
tar -xzf control.tar.gz -C ../control
cp debian-binary ../pkg/debian-binary
rm -rf "$T/data/etc/enigma2/EpiMediaHub" "$T/data/etc/enigma2/epimediahub"

# Vendor a small pure-Python QR encoder. Runtime remains fully local and does
# not depend on a cloud QR service or an additional package on the receiver.
python3 -m pip install --quiet --disable-pip-version-check --no-compile --target "$VENDOR" 'segno==1.6.6'
find "$VENDOR" -maxdepth 1 -type d \( -name '*.dist-info' -o -name '__pycache__' \) -prune -exec rm -rf {} +

export P
python3 - <<'PY'
import os
from pathlib import Path
p=Path(os.environ['P'])
t=p.read_text(encoding='utf-8')
if 'PLUGIN_VERSION = "0.9.35"' not in t:
    raise SystemExit('Expected v0.9.35 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.35"','PLUGIN_VERSION = "0.9.36"',1)

# sys.path is only touched lazily when the QR helper is used.
if 'import subprocess\nimport threading\n' not in t:
    raise SystemExit('stdlib import anchor missing')
t=t.replace('import subprocess\nimport threading\n','import subprocess\nimport sys\nimport threading\n',1)

skin_old='''WEB_PLAYLIST_SETUP_SKIN = build_fullscreen_skin(\n    "EpiWebPlaylistSetup",\n    overlay_pixmap(SETTINGS_GLASS_OVERLAY) +\n    logo_widget(w=300, h=100) +\n    label_widget("title", 380, 28, 845, 48, 29, "right") +\n    label_widget("subtitle", 380, 78, 845, 30, 17, "right", fg="#9EADBF") +\n    label_widget("url", 100, 180, 1080, 58, 25, "center", "center", "#101722", "#FFFFFF") +\n    label_widget("pin", 390, 270, 500, 78, 40, "center", "center", "#141B27", "#FFFFFF") +\n    label_widget("status", 100, 385, 1080, 120, 20, "center", "center", "#0D121B", "#E7EEF7") +\n    label_widget("info", 100, 530, 1080, 55, 17, "center", "center", None, "#9EADBF") +\n    color_button("red", 55, "#8D2830") +\n    color_button("green", 350, "#267A42") +\n    color_button("yellow", 645, "#8A7624") +\n    color_button("blue", 940, "#245B8F")\n)\n'''
if skin_old not in t:
    raise SystemExit('Web setup skin anchor missing')
skin_new='''WEB_PLAYLIST_QR_PATH = "/tmp/epimediahub_websetup_qr.png"\n\nWEB_PLAYLIST_SETUP_SKIN = build_fullscreen_skin(\n    "EpiWebPlaylistSetup",\n    overlay_pixmap(SETTINGS_GLASS_OVERLAY) +\n    logo_widget(w=300, h=100) +\n    label_widget("title", 380, 28, 845, 48, 29, "right") +\n    label_widget("subtitle", 380, 78, 845, 30, 17, "right", fg="#9EADBF") +\n    '<widget name="qr" position="%s" size="%s" alphatest="blend" scale="1" zPosition="4" />' % (pos(90, 155), size(275, 275)) +\n    label_widget("url", 410, 165, 770, 58, 24, "center", "center", "#101722", "#FFFFFF") +\n    label_widget("pin", 535, 250, 520, 78, 40, "center", "center", "#141B27", "#FFFFFF") +\n    label_widget("status", 410, 350, 770, 118, 20, "center", "center", "#0D121B", "#E7EEF7") +\n    label_widget("info", 100, 505, 1080, 62, 17, "center", "center", None, "#9EADBF") +\n    color_button("red", 55, "#8D2830") +\n    color_button("green", 350, "#267A42") +\n    color_button("yellow", 645, "#8A7624") +\n    color_button("blue", 940, "#245B8F")\n)\n'''
t=t.replace(skin_old,skin_new,1)

ip_anchor='''def _playlist_web_local_ip():\n'''
if ip_anchor not in t:
    raise SystemExit('Web local IP anchor missing')
qr_helper='''def _playlist_web_generate_qr(value):\n    value = clean_text(value)\n    if not value:\n        return False\n    try:\n        vendor = os.path.join(PLUGIN_DIR, "vendor")\n        if vendor not in sys.path:\n            sys.path.insert(0, vendor)\n        import segno\n        qr = segno.make_qr(value, error="m")\n        qr.save(WEB_PLAYLIST_QR_PATH, kind="png", scale=9, border=2, dark="#000000", light="#FFFFFF")\n        try:\n            os.chmod(WEB_PLAYLIST_QR_PATH, 0o600)\n        except Exception:\n            pass\n        return os.path.isfile(WEB_PLAYLIST_QR_PATH) and os.path.getsize(WEB_PLAYLIST_QR_PATH) > 0\n    except Exception:\n        return False\n\n\ndef _playlist_web_remove_qr():\n    try:\n        if os.path.exists(WEB_PLAYLIST_QR_PATH):\n            os.remove(WEB_PLAYLIST_QR_PATH)\n    except Exception:\n        pass\n\n\n'''
t=t.replace(ip_anchor,qr_helper+ip_anchor,1)

init_old='''        self["url"] = Label("Webserver wird gestartet ...")\n        self["pin"] = Label("------")\n        self["status"] = Label("Öffne die angezeigte Adresse im Browser und gib dort den PIN ein.")\n'''
if init_old not in t:
    raise SystemExit('Web setup widget init anchor missing')
init_new='''        self["qr"] = Pixmap()\n        self["url"] = Label("Webserver wird gestartet ...")\n        self["pin"] = Label("------")\n        self["status"] = Label("QR-Code scannen oder die angezeigte Adresse im Browser öffnen und den PIN eingeben.")\n'''
t=t.replace(init_old,init_new,1)

stop_anchor='''        try:self._poll_timer.stop()\n        except Exception:pass\n        if server is not None:\n'''
if stop_anchor not in t:
    raise SystemExit('stop server anchor missing')
stop_new='''        try:self._poll_timer.stop()\n        except Exception:pass\n        _playlist_web_remove_qr()\n        try:self["qr"].hide()\n        except Exception:pass\n        if server is not None:\n'''
t=t.replace(stop_anchor,stop_new,1)

fail_old='''            self["url"].setText("Webserver konnte nicht gestartet werden")\n            self["pin"].setText("------")\n            self["status"].setText("Die Ports 8765-8770 sind belegt. BLAU drücken, um es erneut zu versuchen.")\n            return\n'''
if fail_old not in t:
    raise SystemExit('server failure anchor missing')
fail_new='''            self["url"].setText("Webserver konnte nicht gestartet werden")\n            self["pin"].setText("------")\n            try:self["qr"].hide()\n            except Exception:pass\n            self["status"].setText("Die Ports 8765-8770 sind belegt. BLAU drücken, um es erneut zu versuchen.")\n            return\n'''
t=t.replace(fail_old,fail_new,1)

url_old='''        ip = _playlist_web_local_ip()\n        self["url"].setText("http://%s:%d/" % (ip, port))\n        self["pin"].setText(pin)\n        self["status"].setText("1. Adresse am Handy/PC öffnen\\n2. PIN eingeben\\n3. M3U oder Xtream eintragen und senden")\n'''
if url_old not in t:
    raise SystemExit('web setup URL anchor missing')
url_new='''        ip = _playlist_web_local_ip()\n        setup_url = "http://%s:%d/" % (ip, port)\n        self["url"].setText(setup_url)\n        self["pin"].setText(pin)\n        if _playlist_web_generate_qr(setup_url):\n            try:\n                if self["qr"].instance is not None:\n                    self["qr"].instance.setPixmapFromFile(WEB_PLAYLIST_QR_PATH)\n                self["qr"].show()\n            except Exception:\n                try:self["qr"].hide()\n                except Exception:pass\n        else:\n            try:self["qr"].hide()\n            except Exception:pass\n        self["status"].setText("1. QR scannen oder Adresse öffnen\\n2. PIN eingeben\\n3. M3U oder Xtream eintragen und senden")\n'''
t=t.replace(url_old,url_new,1)

p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.36/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.36 local QR web playlist setup for M3U and Xtream/' "$T/control/control"

python3 -m py_compile "$P"
grep -q 'PLUGIN_VERSION = "0.9.36"' "$P"
grep -q 'WEB_PLAYLIST_QR_PATH = "/tmp/epimediahub_websetup_qr.png"' "$P"
grep -q 'self\["qr"\] = Pixmap()' "$P"
grep -q 'def _playlist_web_generate_qr' "$P"
grep -q 'segno.make_qr' "$P"
grep -q 'self\["qr"\].instance.setPixmapFromFile' "$P"
grep -q 'QR scannen oder Adresse öffnen' "$P"
grep -q 'class EpiWebPlaylistSetup(Screen)' "$P"
grep -q 'class _EpiPlaylistWebHandler(BaseHTTPRequestHandler)' "$P"
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

# Prove the exact bundled QR encoder can create a PNG without network access.
PYTHONPATH="$VENDOR" python3 - <<'PY'
import os, tempfile
import segno
p=os.path.join(tempfile.gettempdir(),'epimediahub_qr_guard.png')
segno.make_qr('http://192.168.1.50:8765/', error='m').save(p, kind='png', scale=9, border=2)
if not os.path.isfile(p) or os.path.getsize(p) <= 100:
    raise SystemExit('Bundled QR encoder failed to create PNG')
os.remove(p)
print('Bundled local QR encoder guard: OK')
PY

python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
need=[
 'class EpiWebPlaylistSetup(Screen):',
 'def _playlist_web_generate_qr(value):',
 'segno.make_qr(value, error="m")',
 'self["qr"] = Pixmap()',
 'self["qr"].instance.setPixmapFromFile(WEB_PLAYLIST_QR_PATH)',
 'setup_url = "http://%s:%d/" % (ip, port)',
 'self.session.openWithCallback(self._webSetupClosed, EpiWebPlaylistSetup)',
 'self.onLayoutFinish.append(self._autoWebSetupIfEmpty)',
 'urlencode({"username": username, "password": password, "type": "m3u_plus", "output": "ts"})',
 'time.time() + 15 * 60',
]
for x in need:
    if x not in t: raise SystemExit('v0.9.36 guard missing: '+x)
# QR encodes only the receiver-local URL, never the PIN or playlist credentials.
start=t.index('def _playlist_web_generate_qr(value):')
end=t.index('def _playlist_web_local_ip():',start)
q=t[start:end]
if 'epi_pin' in q or 'password' in q or 'username' in q:
    raise SystemExit('QR helper unexpectedly contains credentials')
# Rai-specific app PIN must remain absent while Family PIN remains elsewhere.
ms=t.index('class EpiMediathekHome(Screen):'); me=t.index('class EpiMediaHubHome(Screen):',ms); m=t[ms:me]
if '_pin_done' in m or ('Rai' in m and 'openWithCallback(self._pin' in m):
    raise SystemExit('Rai provider PIN gate reintroduced')
print('v0.9.36 local QR web setup guard: OK')
PY

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.36.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"
if ar p EpiMediaHub_v0.9.36.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.36.ipk)
echo "v0.9.36 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.36.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.36.ipk" > EpiMediaHub_v0.9.36.ipk.sha256
printf '{\n  "version": "0.9.36",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.36.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.36.ipk.sha256
rm -f EpiMediaHub_v0.9.35.ipk EpiMediaHub_v0.9.35.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.36 QR web playlist setup'
git push
