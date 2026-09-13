#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"
BASE="$WORKSPACE/EpiMediaHub_v0.9.20.ipk"
TMP=/tmp/epimedia0920media
ROOT="$TMP/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub"
PLUGIN="$ROOT/plugin.py"

rm -rf "$TMP"
mkdir -p "$TMP/ar" "$TMP/data" "$TMP/control" "$TMP/pkg"
cd "$TMP/ar"
ar x "$BASE"
tar -xzf data.tar.gz -C ../data
tar -xzf control.tar.gz -C ../control
cp debian-binary ../pkg/debian-binary

# User data must never be owned by the update package.
rm -rf "$TMP/data/etc/enigma2/EpiMediaHub" "$TMP/data/etc/enigma2/epimediahub"

# Create a lightweight Mediathek home icon (TV + play symbol).
export ROOT PLUGIN
python3 - <<'PY'
import os
from pathlib import Path
from PIL import Image, ImageDraw
root = Path(os.environ['ROOT'])
img = Image.new('RGBA', (96, 96), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((12, 18, 84, 72), radius=9, outline=(245, 248, 252, 245), width=6)
d.line((36, 82, 60, 82), fill=(245, 248, 252, 235), width=5)
d.line((48, 72, 48, 82), fill=(245, 248, 252, 235), width=5)
d.polygon([(41, 34), (41, 58), (62, 46)], fill=(245, 248, 252, 245))
img.save(str(root / 'home_mediathek.png'), optimize=True)
PY

python3 - <<'PY'
import os
from pathlib import Path

p = Path(os.environ['PLUGIN'])
t = p.read_text(encoding='utf-8')

old_icons = 'HOME_ICONS = [os.path.join(PLUGIN_DIR, "home_%s.png" % name) for name in ("live", "movies", "series", "search", "playlist", "settings")]'
new_icons = 'HOME_ICONS = [os.path.join(PLUGIN_DIR, "home_%s.png" % name) for name in ("live", "movies", "series", "mediathek", "playlist", "settings")]'
if old_icons not in t:
    raise SystemExit('HOME_ICONS anchor missing')
t = t.replace(old_icons, new_icons, 1)

old_tiles = 'self.tiles = [tr("live"), tr("movies"), tr("series"), tr("search"), tr("switch_playlist"), tr("settings")]'
new_tiles = 'self.tiles = [tr("live"), tr("movies"), tr("series"), mediathek_label(), tr("switch_playlist"), tr("settings")]'
if t.count(old_tiles) < 2:
    raise SystemExit('home tile anchors missing')
t = t.replace(old_tiles, new_tiles, 2)

old_ok = '        elif self.currentIndex == 3:\n            self.globalSearch()'
new_ok = '        elif self.currentIndex == 3:\n            self.session.open(EpiMediathekHome)'
if old_ok not in t:
    raise SystemExit('home search action anchor missing')
t = t.replace(old_ok, new_ok, 1)

skin_anchor = 'SPLASH_SKIN = build_fullscreen_skin('
if skin_anchor not in t:
    raise SystemExit('splash skin anchor missing')
mediathek_skins = r'''MEDIATHEK_HOME_SKIN = build_fullscreen_skin(
    "EpiMediathekHome",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) +
    logo_widget(w=300, h=100) +
    label_widget("title", 380, 28, 845, 48, 31, "right") +
    label_widget("subtitle", 380, 78, 845, 30, 18, "right", fg="#9EADBF") +
    list_widget("list", 70, 135, 1140, 455, 23, 44) +
    label_widget("info", 70, 598, 1140, 35, 16, "center", fg="#9EADBF") +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)

MEDIATHEK_LIST_SKIN = build_fullscreen_skin(
    "EpiMediathekList",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) +
    logo_widget(w=300, h=100) +
    label_widget("title", 380, 28, 845, 48, 29, "right") +
    label_widget("subtitle", 380, 78, 845, 30, 17, "right", fg="#9EADBF") +
    list_widget("list", 55, 128, 1170, 345, 20, 42) +
    label_widget("detail", 55, 485, 1170, 125, 17, "left", "top", "#0D121B", "#E7EEF7") +
    label_widget("info", 55, 615, 1170, 28, 15, "center", fg="#9EADBF") +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)

'''
t = t.replace(skin_anchor, mediathek_skins + skin_anchor, 1)

class_anchor = 'class EpiMediaHubHome(Screen):'
if class_anchor not in t:
    raise SystemExit('home class anchor missing')
mediathek_code = r'''MEDIATHEK_API_URL = "https://mediathekviewweb.de/api/query"
MEDIATHEK_CHANNELS = [
    ("ARD", "ARD / Das Erste"),
    ("ZDF", "ZDF"),
    ("ZDFneo", "ZDFneo"),
    ("ZDFinfo", "ZDFinfo"),
    ("3sat", "3sat"),
    ("KiKA", "KiKA"),
    ("phoenix", "phoenix"),
    ("ONE", "ONE"),
    ("tagesschau24", "tagesschau24"),
    ("ARD-alpha", "ARD-alpha"),
    ("WDR", "WDR"),
    ("NDR", "NDR"),
    ("BR", "BR"),
    ("SWR", "SWR"),
    ("MDR", "MDR"),
    ("hr", "hr"),
    ("rbb", "rbb"),
    ("SR", "SR"),
    ("Radio Bremen", "Radio Bremen TV"),
    ("arte", "arte")
]


def mediathek_copy(key):
    lang = current_app_language()
    texts = {
        "de": {
            "label": "Mediathek", "subtitle": "ARD, ZDF & öffentlich-rechtliche Sender",
            "search_all": "Suche in allen Mediatheken", "latest": "Neueste Sendungen",
            "loading": "Mediathek wird geladen ...", "play": "GRÜN  Abspielen",
            "search": "GELB  Suche", "reload": "BLAU  Neu laden", "back": "ROT  Zurück",
            "source": "Quelle: MediathekViewWeb", "no_results": "Keine abspielbaren Beiträge gefunden.",
            "search_title": "Mediathek durchsuchen"
        },
        "en": {
            "label": "Media Library", "subtitle": "ARD, ZDF & public broadcasters",
            "search_all": "Search all media libraries", "latest": "Latest programmes",
            "loading": "Loading media library ...", "play": "GREEN  Play",
            "search": "YELLOW  Search", "reload": "BLUE  Reload", "back": "RED  Back",
            "source": "Source: MediathekViewWeb", "no_results": "No playable programmes found.",
            "search_title": "Search media library"
        },
        "tr": {
            "label": "Medyatek", "subtitle": "ARD, ZDF ve kamu kanalları",
            "search_all": "Tüm medyateklerde ara", "latest": "En yeni programlar",
            "loading": "Medyatek yükleniyor ...", "play": "YEŞİL  Oynat",
            "search": "SARI  Ara", "reload": "MAVİ  Yenile", "back": "KIRMIZI  Geri",
            "source": "Kaynak: MediathekViewWeb", "no_results": "Oynatılabilir içerik bulunamadı.",
            "search_title": "Medyatek ara"
        },
        "it": {
            "label": "Mediathek", "subtitle": "ARD, ZDF e canali pubblici",
            "search_all": "Cerca in tutte le mediateche", "latest": "Programmi più recenti",
            "loading": "Caricamento mediateca ...", "play": "VERDE  Riproduci",
            "search": "GIALLO  Cerca", "reload": "BLU  Ricarica", "back": "ROSSO  Indietro",
            "source": "Fonte: MediathekViewWeb", "no_results": "Nessun contenuto riproducibile trovato.",
            "search_title": "Cerca nella mediateca"
        },
        "es": {
            "label": "Mediateca", "subtitle": "ARD, ZDF y canales públicos",
            "search_all": "Buscar en todas las mediatecas", "latest": "Programas recientes",
            "loading": "Cargando mediateca ...", "play": "VERDE  Reproducir",
            "search": "AMARILLO  Buscar", "reload": "AZUL  Recargar", "back": "ROJO  Atrás",
            "source": "Fuente: MediathekViewWeb", "no_results": "No se encontraron contenidos reproducibles.",
            "search_title": "Buscar en la mediateca"
        }
    }
    table = texts.get(lang, texts["de"])
    return table.get(key, texts["de"].get(key, key))


def mediathek_label():
    return mediathek_copy("label")


def _mediathek_duration(value):
    try:
        seconds = max(0, int(value or 0))
    except Exception:
        seconds = 0
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%02d:%02d" % (minutes, secs)


def _mediathek_query(channel="", term="", offset=0, size=40):
    queries = []
    channel = clean_text(channel)
    term = clean_text(term)
    if channel:
        queries.append({"fields": ["channel"], "query": channel})
    if term:
        queries.append({"fields": ["title", "topic", "description"], "query": term})
    body = {
        "queries": queries,
        "sortBy": "timestamp",
        "sortOrder": "desc",
        "future": False,
        "offset": int(offset or 0),
        "size": int(size or 40)
    }
    payload = json.dumps(body).encode("utf-8")
    last_error = None
    raw = None
    for content_type in ("application/json", "text/plain"):
        try:
            req = Request(MEDIATHEK_API_URL, data=payload)
            req.add_header("Content-Type", content_type)
            req.add_header("Accept", "application/json")
            req.add_header("User-Agent", "EpiMediaHub/%s" % PLUGIN_VERSION)
            response = urlopen(req, timeout=15)
            raw = response.read()
            try:
                response.close()
            except Exception:
                pass
            break
        except Exception as error:
            last_error = error
            raw = None
    if raw is None:
        raise Exception(str(last_error or "MediathekViewWeb nicht erreichbar"))
    if not isinstance(raw, str):
        try:
            text = raw.decode("utf-8")
        except Exception:
            text = raw.decode("latin-1", "replace")
    else:
        text = raw
    data = json.loads(text)
    result = data.get("result", {}) if isinstance(data, dict) else {}
    rows = result.get("results", []) if isinstance(result, dict) else []
    entries = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        stream = clean_text(item.get("url_video_hd", "")) or clean_text(item.get("url_video", "")) or clean_text(item.get("url_video_low", ""))
        if not stream:
            continue
        title = clean_text(item.get("title", "")) or clean_text(item.get("topic", "")) or "Mediathek"
        entry = {
            "title": title,
            "topic": clean_text(item.get("topic", "")),
            "channel": clean_text(item.get("channel", "")),
            "description": clean_text(item.get("description", "")),
            "duration": item.get("duration", 0),
            "timestamp": item.get("timestamp", 0),
            "url": stream,
            "url_website": clean_text(item.get("url_website", "")),
            "type": "movie"
        }
        entries.append(entry)
    return entries


class EpiMediathekHome(Screen):
    skin = MEDIATHEK_HOME_SKIN

    def __init__(self, session):
        Screen.__init__(self, session)
        self["logo"] = Pixmap()
        self["title"] = Label(mediathek_copy("label"))
        self["subtitle"] = Label(mediathek_copy("subtitle"))
        self["list"] = MenuList([])
        self["info"] = Label("OK = öffnen   |   GELB = %s" % mediathek_copy("search_all"))
        self["red"] = Label(mediathek_copy("back"))
        self["green"] = Label("GRÜN  Öffnen")
        self["yellow"] = Label(mediathek_copy("search"))
        self["blue"] = Label("")
        self.items = list(MEDIATHEK_CHANNELS) + [("__search__", mediathek_copy("search_all"))]
        self["list"].setList([label for value, label in self.items])
        self["actions"] = ActionMap(
            ["OkCancelActions", "DirectionActions", "ColorActions"],
            {
                "ok": self.openSelected, "cancel": self.close, "red": self.close,
                "green": self.openSelected, "yellow": self.openSearch,
                "up": self.keyUp, "down": self.keyDown,
                "left": self.pageUp, "right": self.pageDown
            }, -10
        )

    def keyUp(self):
        try: self["list"].up()
        except Exception: pass

    def keyDown(self):
        try: self["list"].down()
        except Exception: pass

    def pageUp(self):
        try: self["list"].pageUp()
        except Exception: pass

    def pageDown(self):
        try: self["list"].pageDown()
        except Exception: pass

    def openSelected(self):
        try:
            index = int(self["list"].getSelectedIndex())
        except Exception:
            index = 0
        if index < 0 or index >= len(self.items):
            return
        value, label = self.items[index]
        if value == "__search__":
            self.openSearch()
            return
        self.session.open(EpiMediathekList, value, label, "")

    def openSearch(self):
        self.session.openWithCallback(
            self.searchEntered, VirtualKeyBoard,
            title=mediathek_copy("search_title"), text=""
        )

    def searchEntered(self, value=None):
        value = clean_text(value or "")
        if value:
            self.session.open(EpiMediathekList, "", mediathek_copy("search_all"), value)


class EpiMediathekList(Screen):
    skin = MEDIATHEK_LIST_SKIN

    def __init__(self, session, channel="", label="", term=""):
        Screen.__init__(self, session)
        self.channel = clean_text(channel)
        self.channel_label = clean_text(label) or mediathek_copy("label")
        self.term = clean_text(term)
        self.results = []
        self._load_job = None
        self._load_result = None
        self._loaded_once = False
        self["logo"] = Pixmap()
        self["title"] = Label(self.channel_label)
        self["subtitle"] = Label("")
        self["list"] = MenuList([])
        self["detail"] = Label("")
        self["info"] = Label(mediathek_copy("source"))
        self["red"] = Label(mediathek_copy("back"))
        self["green"] = Label(mediathek_copy("play"))
        self["yellow"] = Label(mediathek_copy("search"))
        self["blue"] = Label(mediathek_copy("reload"))
        self["actions"] = ActionMap(
            ["OkCancelActions", "DirectionActions", "ColorActions"],
            {
                "ok": self.playSelected, "cancel": self.close, "red": self.close,
                "green": self.playSelected, "yellow": self.openSearch, "blue": self.reload,
                "up": self.keyUp, "down": self.keyDown,
                "left": self.pageUp, "right": self.pageDown
            }, -10
        )
        self._load_timer = eTimer()
        connect_timer(self._load_timer, self._pollLoad)
        self.onShown.append(self._ensureLoaded)
        try:
            self["list"].onSelectionChanged.append(self.updateDetail)
        except Exception:
            pass
        try:
            self.onClose.append(self._stopLoader)
        except Exception:
            pass

    def _stopLoader(self):
        try: self._load_timer.stop()
        except Exception: pass

    def _ensureLoaded(self):
        if not self._loaded_once:
            self.reload()

    def reload(self):
        if self._load_job is not None and self._load_job.is_alive():
            return
        self._loaded_once = True
        self._load_result = None
        self["list"].setList([mediathek_copy("loading")])
        self["detail"].setText("")
        subtitle = mediathek_copy("latest")
        if self.term:
            subtitle = "%s: %s" % (mediathek_copy("search_title"), self.term)
        self["subtitle"].setText(subtitle)
        self._load_job = threading.Thread(target=self._loadWorker)
        self._load_job.daemon = True
        self._load_job.start()
        try:
            self._load_timer.start(300, True)
        except TypeError:
            self._load_timer.start(300)

    def _loadWorker(self):
        try:
            items = _mediathek_query(self.channel, self.term, 0, 45)
            self._load_result = (True, items, "")
        except Exception as error:
            self._load_result = (False, [], str(error))

    def _pollLoad(self):
        if self._load_job is not None and self._load_job.is_alive():
            try:
                self._load_timer.start(300, True)
            except TypeError:
                self._load_timer.start(300)
            return
        result = self._load_result
        self._load_job = None
        self._load_result = None
        if not result:
            return
        ok, items, error = result
        if not ok:
            self.results = []
            self["list"].setList(["Mediathek konnte nicht geladen werden"])
            self["detail"].setText(error)
            return
        self.results = items
        if not items:
            self["list"].setList([mediathek_copy("no_results")])
            self["detail"].setText("")
            return
        rows = []
        for entry in items:
            channel = entry.get("channel", "")
            title = entry.get("title", "")
            duration = _mediathek_duration(entry.get("duration", 0))
            rows.append("%s   |   %s   |   %s" % (channel, title, duration))
        self["list"].setList(rows)
        self["info"].setText("%d Beiträge   |   %s" % (len(items), mediathek_copy("source")))
        self.updateDetail()

    def selectedEntry(self):
        if not self.results:
            return None
        try:
            index = int(self["list"].getSelectedIndex())
        except Exception:
            index = 0
        if index < 0 or index >= len(self.results):
            return None
        return self.results[index]

    def updateDetail(self):
        entry = self.selectedEntry()
        if not entry:
            return
        topic = clean_text(entry.get("topic", ""))
        desc = clean_text(entry.get("description", ""))
        channel = clean_text(entry.get("channel", ""))
        duration = _mediathek_duration(entry.get("duration", 0))
        head = "%s   |   %s" % (channel, duration)
        if topic:
            head += "   |   %s" % topic
        self["detail"].setText("%s\n%s" % (head, desc[:900]))

    def keyUp(self):
        try: self["list"].up()
        except Exception: pass
        self.updateDetail()

    def keyDown(self):
        try: self["list"].down()
        except Exception: pass
        self.updateDetail()

    def pageUp(self):
        try: self["list"].pageUp()
        except Exception: pass
        self.updateDetail()

    def pageDown(self):
        try: self["list"].pageDown()
        except Exception: pass
        self.updateDetail()

    def openSearch(self):
        self.session.openWithCallback(
            self.searchEntered, VirtualKeyBoard,
            title=mediathek_copy("search_title"), text=self.term
        )

    def searchEntered(self, value=None):
        value = clean_text(value or "")
        if value == self.term:
            return
        self.term = value
        self._loaded_once = False
        self.reload()

    def playSelected(self):
        entry = self.selectedEntry()
        if not entry:
            return
        url = clean_text(entry.get("url", ""))
        if not url:
            self.session.open(MessageBox, "Kein abspielbarer Stream gefunden.", MessageBox.TYPE_ERROR, timeout=5)
            return
        try:
            ref = eServiceReference(4097, 0, url)
            ref.setName(entry.get("title", "Mediathek"))
            if EpiMoviePlayer is not None:
                self.session.open(EpiMoviePlayer, ref, ["deu", "ger", "eng"], "", url, 0, entry, [], -1)
            elif MoviePlayer is not None:
                self.session.open(MoviePlayer, ref)
            else:
                self.session.nav.playService(ref)
        except Exception as error:
            self.session.open(MessageBox, "Wiedergabe fehlgeschlagen:\n%s" % str(error), MessageBox.TYPE_ERROR, timeout=6)


'''
t = t.replace(class_anchor, mediathek_code + class_anchor, 1)

# Keep the displayed version exactly 0.9.20 as requested.
if 'PLUGIN_VERSION = "0.9.20"' not in t:
    raise SystemExit('version anchor missing')

p.write_text(t, encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.20/' "$TMP/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.20 Mediathek ARD ZDF/' "$TMP/control/control"

python3 -m py_compile "$PLUGIN"
grep -q 'class EpiMediathekHome' "$PLUGIN"
grep -q 'class EpiMediathekList' "$PLUGIN"
grep -q 'home_mediathek' "$PLUGIN"
grep -q 'MEDIATHEK_API_URL' "$PLUGIN"
grep -q 'self.session.open(EpiMediathekHome)' "$PLUGIN"

# Optional live smoke test: log API health but do not make packaging depend on a third-party outage.
python3 - <<'PY' || true
import json
from urllib.request import Request, urlopen
body=json.dumps({"queries":[{"fields":["channel"],"query":"ARD"}],"sortBy":"timestamp","sortOrder":"desc","future":False,"offset":0,"size":2}).encode()
r=Request('https://mediathekviewweb.de/api/query',data=body,headers={'Content-Type':'application/json','User-Agent':'EpiMediaHub-build-smoke'})
raw=urlopen(r,timeout=10).read().decode('utf-8','replace')
data=json.loads(raw)
print('Mediathek API smoke results:',len(data.get('result',{}).get('results',[])))
PY

# Rebuild package.
tar --owner=0 --group=0 -czf "$TMP/pkg/control.tar.gz" -C "$TMP/control" .
tar --owner=0 --group=0 -czf "$TMP/pkg/data.tar.gz" -C "$TMP/data" .
cd "$TMP/pkg"
ar r "$WORKSPACE/EpiMediaHub_v0.9.20.new.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$WORKSPACE"

# Safety checks: user configuration must not be package-owned, and package remains compact.
if ar p EpiMediaHub_v0.9.20.new.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2
  exit 1
fi
SIZE=$(stat -c%s EpiMediaHub_v0.9.20.new.ipk)
echo "v0.9.20 Mediathek size: $SIZE bytes"
if [ "$SIZE" -gt 25165824 ]; then
  echo 'ERROR: package exceeds 24 MiB guard' >&2
  exit 1
fi

mv -f EpiMediaHub_v0.9.20.new.ipk EpiMediaHub_v0.9.20.ipk
SHA=$(sha256sum EpiMediaHub_v0.9.20.ipk | awk '{print $1}')
echo "$SHA  EpiMediaHub_v0.9.20.ipk" > EpiMediaHub_v0.9.20.ipk.sha256
python3 - <<PY
import json
p='update.json'
d=json.load(open(p,encoding='utf-8'))
d['version']='0.9.20'
d['url']='https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.20.ipk'
d['sha256']='$SHA'
open(p,'w',encoding='utf-8').write(json.dumps(d,indent=2)+'\n')
PY
sha256sum -c EpiMediaHub_v0.9.20.ipk.sha256

# Remove temporary inspection material from the repository.
rm -f .github/workflows/inspect-enigma-v0920-mediathek.yml .github/workflows/inspect-v0920-home-lines.yml
rm -f inspection/plugin_v0920.py inspection/v0920-mediathek-hooks.txt inspection/v0920-home-lines.txt

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.20 Mediathek feature update'
git push
