#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"
BASE="$WORKSPACE/EpiMediaHub_v0.9.21.ipk"
TMP=/tmp/epimedia0922
ROOT="$TMP/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub"
PLUGIN="$ROOT/plugin.py"

rm -rf "$TMP"
mkdir -p "$TMP/ar" "$TMP/data" "$TMP/control" "$TMP/pkg"
cd "$TMP/ar"
ar x "$BASE"
tar -xzf data.tar.gz -C ../data
tar -xzf control.tar.gz -C ../control
cp debian-binary ../pkg/debian-binary

# Never let an IPK own persistent user data.
rm -rf "$TMP/data/etc/enigma2/EpiMediaHub" "$TMP/data/etc/enigma2/epimediahub"

export PLUGIN
python3 - <<'PY'
import os
from pathlib import Path

p = Path(os.environ['PLUGIN'])
t = p.read_text(encoding='utf-8')

# Version bump.
t = t.replace('PLUGIN_VERSION = "0.9.21"', 'PLUGIN_VERSION = "0.9.22"', 1)

# Safer home entry: an Enigma2-specific screen construction problem must show
# an in-app error instead of propagating into a GUI restart.
old_open = '        elif self.currentIndex == 3:\n            self.session.open(EpiMediathekHome)'
new_open = '''        elif self.currentIndex == 3:
            try:
                self.session.open(EpiMediathekHome)
            except Exception as error:
                try:
                    self.session.open(MessageBox, "Mediathek konnte nicht geöffnet werden:\\n%s" % str(error), MessageBox.TYPE_ERROR, timeout=8)
                except Exception:
                    pass'''
if old_open not in t:
    raise SystemExit('Mediathek home action anchor missing')
t = t.replace(old_open, new_open, 1)

# Replace the two first-generation Mediathek skins with a proven simple
# Enigma2 layout.  The content list stays a normal MenuList; poster and text
# live in separate widgets so list focus/navigation cannot be destabilised.
start = t.find('MEDIATHEK_HOME_SKIN = build_fullscreen_skin(')
end = t.find('SPLASH_SKIN = build_fullscreen_skin(', start)
if start < 0 or end < 0:
    raise SystemExit('Mediathek skin block missing')
new_skins = r'''MEDIATHEK_HOME_SKIN = build_fullscreen_skin(
    "EpiMediathekHome",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) +
    logo_widget(w=300, h=100) +
    label_widget("title", 380, 28, 845, 48, 31, "right") +
    label_widget("subtitle", 380, 78, 845, 30, 18, "right", fg="#9EADBF") +
    list_widget("list", 55, 135, 690, 455, 23, 44) +
    label_widget("provider_title", 780, 150, 430, 55, 27, "left", "top") +
    label_widget("provider_meta", 780, 215, 430, 55, 17, "left", "top", fg="#AFC0D4") +
    label_widget("provider_info", 780, 285, 430, 250, 18, "left", "top", "#0D121B", "#E7EEF7") +
    label_widget("info", 55, 600, 1170, 35, 16, "center", fg="#9EADBF") +
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
    list_widget("list", 55, 130, 565, 460, 20, 42) +
    '<widget name="poster" position="%s" size="%s" alphatest="on" scale="1" zPosition="3" />' % (pos(650, 145), size(225, 320)) +
    label_widget("preview_title", 900, 145, 325, 78, 25, "left", "top") +
    label_widget("preview_meta", 900, 228, 325, 110, 17, "left", "top", fg="#AFC0D4") +
    label_widget("preview_overview", 900, 345, 325, 220, 17, "left", "top", "#0D121B", "#E7EEF7") +
    label_widget("poster_hint", 650, 475, 225, 88, 15, "center", "top", fg="#8093A8") +
    label_widget("info", 55, 602, 1170, 32, 15, "center", fg="#9EADBF") +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)

'''
t = t[:start] + new_skins + t[end:]

# Replace all Mediathek implementation code.  Network work and image work are
# background-only; every GUI callback is guarded so provider/API/image errors
# become a message instead of taking Enigma2 down.
code_start = t.find('MEDIATHEK_API_URL = "https://mediathekviewweb.de/api/query"')
code_end = t.find('class EpiMediaHubHome(Screen):', code_start)
if code_start < 0 or code_end < 0:
    raise SystemExit('Mediathek implementation block missing')
new_code = r'''MEDIATHEK_API_URL = "https://mediathekviewweb.de/api/query"
MEDIATHEK_CHANNELS = [
    ("ARD", "ARD / Das Erste"), ("ZDF", "ZDF"), ("ZDFneo", "ZDFneo"),
    ("ZDFinfo", "ZDFinfo"), ("3sat", "3sat"), ("KiKA", "KiKA"),
    ("phoenix", "phoenix"), ("ONE", "ONE"), ("tagesschau24", "tagesschau24"),
    ("ARD-alpha", "ARD-alpha"), ("WDR", "WDR"), ("NDR", "NDR"),
    ("BR", "BR"), ("SWR", "SWR"), ("MDR", "MDR"), ("hr", "hr"),
    ("rbb", "rbb"), ("SR", "SR"), ("Radio Bremen", "Radio Bremen TV"),
    ("arte", "ARTE")
]


def mediathek_copy(key):
    lang = current_app_language()
    texts = {
        "de": {"label":"Mediathek","subtitle":"Öffentlich-rechtliche Mediatheken","search_all":"Alle Mediatheken durchsuchen","latest":"Neueste Beiträge","loading":"Beiträge werden geladen ...","play":"GRÜN  Abspielen","search":"GELB  Suche","reload":"BLAU  Neu laden","back":"ROT  Zurück","source":"Quelle: MediathekViewWeb","no_results":"Keine abspielbaren Beiträge gefunden.","search_title":"Mediathek durchsuchen"},
        "en": {"label":"Media Library","subtitle":"Public-service media libraries","search_all":"Search all media libraries","latest":"Latest programmes","loading":"Loading programmes ...","play":"GREEN  Play","search":"YELLOW  Search","reload":"BLUE  Reload","back":"RED  Back","source":"Source: MediathekViewWeb","no_results":"No playable programmes found.","search_title":"Search media library"},
        "tr": {"label":"Medyatek","subtitle":"Kamu yayıncılarının medyatekleri","search_all":"Tüm medyateklerde ara","latest":"En yeni içerikler","loading":"İçerikler yükleniyor ...","play":"YEŞİL  Oynat","search":"SARI  Ara","reload":"MAVİ  Yenile","back":"KIRMIZI  Geri","source":"Kaynak: MediathekViewWeb","no_results":"Oynatılabilir içerik bulunamadı.","search_title":"Medyatek ara"},
        "it": {"label":"Mediathek","subtitle":"Mediateche del servizio pubblico","search_all":"Cerca in tutte le mediateche","latest":"Contenuti recenti","loading":"Caricamento contenuti ...","play":"VERDE  Riproduci","search":"GIALLO  Cerca","reload":"BLU  Ricarica","back":"ROSSO  Indietro","source":"Fonte: MediathekViewWeb","no_results":"Nessun contenuto riproducibile trovato.","search_title":"Cerca nella mediateca"},
        "es": {"label":"Mediateca","subtitle":"Mediatecas de servicio público","search_all":"Buscar en todas las mediatecas","latest":"Contenidos recientes","loading":"Cargando contenidos ...","play":"VERDE  Reproducir","search":"AMARILLO  Buscar","reload":"AZUL  Recargar","back":"ROJO  Atrás","source":"Fuente: MediathekViewWeb","no_results":"No se encontraron contenidos reproducibles.","search_title":"Buscar en la mediateca"}
    }
    table = texts.get(lang, texts["de"])
    return table.get(key, texts["de"].get(key, key))


def mediathek_label():
    return mediathek_copy("label")


def _mediathek_duration(value):
    try: seconds = max(0, int(value or 0))
    except Exception: seconds = 0
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours:
        return "%d:%02d Std." % (hours, minutes)
    return "%d Min." % minutes if minutes else ""


def _mediathek_date(value):
    try:
        stamp = int(value or 0)
        if stamp > 20000000000:
            stamp = stamp // 1000
        return time.strftime("%d.%m.%Y", time.localtime(stamp)) if stamp > 0 else ""
    except Exception:
        return ""


def _mediathek_episode_hint(title, topic):
    text = "%s %s" % (clean_text(topic), clean_text(title))
    for pattern in (r'(?i)S(?:taffel)?\s*0*(\d+)\s*[/\- ]*E(?:pisode|p\.?|Folge)?\s*0*(\d+)', r'(?i)S(\d+)\s*[/\-]?E(\d+)', r'(?i)Staffel\s*(\d+).*?Folge\s*(\d+)'):
        match = re.search(pattern, text)
        if match:
            return "Staffel %d · Folge %d" % (int(match.group(1)), int(match.group(2)))
    return ""


def _mediathek_query(channel="", term="", offset=0, size=40):
    queries = []
    channel = clean_text(channel)
    term = clean_text(term)
    if channel:
        queries.append({"fields": ["channel"], "query": channel})
    if term:
        queries.append({"fields": ["title", "topic", "description"], "query": term})
    body = {"queries": queries, "sortBy": "timestamp", "sortOrder": "desc", "future": False, "offset": int(offset or 0), "size": int(size or 40)}
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
            try: response.close()
            except Exception: pass
            break
        except Exception as error:
            last_error = error
            raw = None
    if raw is None:
        raise Exception(str(last_error or "MediathekViewWeb nicht erreichbar"))
    if not isinstance(raw, str):
        try: text = raw.decode("utf-8")
        except Exception: text = raw.decode("latin-1", "replace")
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
        entries.append({
            "title": title, "topic": clean_text(item.get("topic", "")),
            "channel": clean_text(item.get("channel", "")), "description": clean_text(item.get("description", "")),
            "duration": item.get("duration", 0), "timestamp": item.get("timestamp", 0),
            "url": stream, "url_website": clean_text(item.get("url_website", "")), "type": "movie"
        })
    return entries


def _mediathek_page_image(page_url):
    page_url = clean_text(page_url)
    if not page_url.startswith(("http://", "https://")):
        return ""
    try:
        req = Request(page_url)
        req.add_header("User-Agent", "Mozilla/5.0 (Linux; Enigma2) EpiMediaHub/%s" % PLUGIN_VERSION)
        req.add_header("Accept", "text/html,application/xhtml+xml")
        response = urlopen(req, timeout=10)
        raw = response.read(700000)
        try: response.close()
        except Exception: pass
        try: html = raw.decode("utf-8", "replace")
        except Exception: html = str(raw)
        patterns = (
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)'
        )
        image = ""
        for pattern in patterns:
            match = re.search(pattern, html, re.I)
            if match:
                image = clean_text(match.group(1)).replace("&amp;", "&")
                break
        if image.startswith("//"):
            image = "https:" + image
        elif image.startswith("/"):
            parsed = urlparse(page_url)
            image = "%s://%s%s" % (parsed.scheme, parsed.netloc, image)
        return image
    except Exception:
        return ""


class EpiMediathekHome(Screen):
    skin = MEDIATHEK_HOME_SKIN

    def __init__(self, session):
        Screen.__init__(self, session)
        self["logo"] = Pixmap()
        self["title"] = Label(mediathek_copy("label"))
        self["subtitle"] = Label(mediathek_copy("subtitle"))
        self["list"] = MenuList([])
        self["provider_title"] = Label("")
        self["provider_meta"] = Label("")
        self["provider_info"] = Label("")
        self["info"] = Label("OK = öffnen   |   GELB = %s" % mediathek_copy("search_all"))
        self["red"] = Label(mediathek_copy("back"))
        self["green"] = Label("GRÜN  Öffnen")
        self["yellow"] = Label(mediathek_copy("search"))
        self["blue"] = Label("")
        self.items = list(MEDIATHEK_CHANNELS) + [("__search__", mediathek_copy("search_all"))]
        self["list"].setList([label for value, label in self.items])
        self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
            "ok": self.openSelected, "cancel": self.close, "red": self.close,
            "green": self.openSelected, "yellow": self.openSearch,
            "up": self.keyUp, "down": self.keyDown, "left": self.pageUp, "right": self.pageDown
        }, -1)
        self.onLayoutFinish.append(self._afterLayout)

    def _afterLayout(self):
        try: self["list"].onSelectionChanged.append(self.updateProviderInfo)
        except Exception: pass
        self.updateProviderInfo()

    def _move(self, method):
        try: getattr(self["list"], method)()
        except Exception: pass
        self.updateProviderInfo()
    def keyUp(self): self._move("up")
    def keyDown(self): self._move("down")
    def pageUp(self): self._move("pageUp")
    def pageDown(self): self._move("pageDown")

    def selectedProvider(self):
        try: index = int(self["list"].getSelectedIndex())
        except Exception: index = 0
        if 0 <= index < len(self.items): return self.items[index]
        return None

    def updateProviderInfo(self):
        item = self.selectedProvider()
        if not item: return
        value, label = item
        if value == "__search__":
            self["provider_title"].setText(mediathek_copy("search_all"))
            self["provider_meta"].setText("ARD · ZDF · 3sat · KiKA · ARTE · Dritte")
            self["provider_info"].setText("Durchsuche alle eingebundenen öffentlich-rechtlichen Mediatheken gleichzeitig. Die Wiedergabe erfolgt direkt im EpiMediaHub-Player.")
            return
        self["provider_title"].setText(label)
        self["provider_meta"].setText("Deutschland · kostenlos · ohne EpiMediaHub-Konto")
        self["provider_info"].setText("Neueste Beiträge und Sendungen von %s. Einzelne Videos können wegen Lizenzrechten zeitlich oder regional eingeschränkt sein." % label)

    def openSelected(self):
        item = self.selectedProvider()
        if not item: return
        value, label = item
        if value == "__search__":
            self.openSearch(); return
        try:
            self.session.open(EpiMediathekList, value, label, "")
        except Exception as error:
            self.session.open(MessageBox, "Mediathek-Liste konnte nicht geöffnet werden:\n%s" % str(error), MessageBox.TYPE_ERROR, timeout=8)

    def openSearch(self):
        try:
            self.session.openWithCallback(self.searchEntered, VirtualKeyBoard, title=mediathek_copy("search_title"), text="")
        except Exception as error:
            self.session.open(MessageBox, str(error), MessageBox.TYPE_ERROR, timeout=6)

    def searchEntered(self, value=None):
        value = clean_text(value or "")
        if value:
            try: self.session.open(EpiMediathekList, "", mediathek_copy("search_all"), value)
            except Exception as error: self.session.open(MessageBox, str(error), MessageBox.TYPE_ERROR, timeout=6)


class EpiMediathekList(Screen):
    skin = MEDIATHEK_LIST_SKIN

    def __init__(self, session, channel="", label="", term=""):
        Screen.__init__(self, session)
        self.channel = clean_text(channel)
        self.channel_label = clean_text(label) or mediathek_copy("label")
        self.term = clean_text(term)
        self.results = []
        self._load_job = None; self._load_result = None; self._loaded_once = False
        self._poster_job = None; self._poster_result = None; self._poster_token = 0; self._poster_decoder = None
        self["logo"] = Pixmap(); self["title"] = Label(self.channel_label); self["subtitle"] = Label("")
        self["list"] = MenuList([]); self["poster"] = Pixmap(); self["preview_title"] = Label("")
        self["preview_meta"] = Label(""); self["preview_overview"] = Label(""); self["poster_hint"] = Label("")
        self["info"] = Label(mediathek_copy("source")); self["red"] = Label(mediathek_copy("back"))
        self["green"] = Label(mediathek_copy("play")); self["yellow"] = Label(mediathek_copy("search")); self["blue"] = Label(mediathek_copy("reload"))
        self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
            "ok": self.playSelected, "cancel": self.close, "red": self.close, "green": self.playSelected,
            "yellow": self.openSearch, "blue": self.reload, "up": self.keyUp, "down": self.keyDown,
            "left": self.pageUp, "right": self.pageDown
        }, -1)
        self._load_timer = eTimer(); connect_timer(self._load_timer, self._pollLoad)
        self._poster_delay_timer = eTimer(); connect_timer(self._poster_delay_timer, self._startPosterLoad)
        self._poster_poll_timer = eTimer(); connect_timer(self._poster_poll_timer, self._pollPoster)
        self.onLayoutFinish.append(self._afterLayout)
        try: self.onClose.append(self._stopWorkers)
        except Exception: pass

    def _afterLayout(self):
        try: self["poster"].hide()
        except Exception: pass
        try: self["list"].onSelectionChanged.append(self._selectionChanged)
        except Exception: pass
        self.reload()

    def _stopWorkers(self):
        for timer in (self._load_timer, self._poster_delay_timer, self._poster_poll_timer):
            try: timer.stop()
            except Exception: pass
        self._poster_token += 1

    def reload(self):
        try:
            if self._load_job is not None and self._load_job.is_alive(): return
            self._loaded_once = True; self._load_result = None; self.results = []
            self["list"].setList([mediathek_copy("loading")]); self._clearPreview()
            subtitle = mediathek_copy("latest") if not self.term else "%s: %s" % (mediathek_copy("search_title"), self.term)
            self["subtitle"].setText(subtitle)
            self._load_job = threading.Thread(target=self._loadWorker); self._load_job.daemon = True; self._load_job.start()
            try: self._load_timer.start(300, True)
            except TypeError: self._load_timer.start(300)
        except Exception as error:
            self._showError(error)

    def _loadWorker(self):
        try: self._load_result = (True, _mediathek_query(self.channel, self.term, 0, 45), "")
        except Exception as error: self._load_result = (False, [], str(error))

    def _pollLoad(self):
        try:
            if self._load_job is not None and self._load_job.is_alive():
                try: self._load_timer.start(300, True)
                except TypeError: self._load_timer.start(300)
                return
            result = self._load_result; self._load_job = None; self._load_result = None
            if not result: return
            ok, items, error = result
            if not ok:
                self.results = []; self["list"].setList(["Mediathek konnte nicht geladen werden"]); self["preview_overview"].setText(error); return
            self.results = list(items or [])
            if not self.results:
                self["list"].setList([mediathek_copy("no_results")]); self._clearPreview(); return
            rows=[]
            for entry in self.results:
                topic=clean_text(entry.get("topic", "")); title=clean_text(entry.get("title", "")); dur=_mediathek_duration(entry.get("duration",0))
                shown = title if not topic or topic.lower() == title.lower() else "%s — %s" % (topic, title)
                rows.append("%s   %s" % (shown, ("· " + dur) if dur else ""))
            self["list"].setList(rows)
            self["info"].setText("%d Beiträge   |   %s" % (len(self.results), mediathek_copy("source")))
            self._selectionChanged()
        except Exception as error:
            self._showError(error)

    def selectedEntry(self):
        if not self.results: return None
        try: index = int(self["list"].getSelectedIndex())
        except Exception: index = 0
        return self.results[index] if 0 <= index < len(self.results) else None

    def _clearPreview(self):
        for name in ("preview_title", "preview_meta", "preview_overview", "poster_hint"):
            try: self[name].setText("")
            except Exception: pass
        try: self["poster"].hide()
        except Exception: pass

    def _selectionChanged(self):
        try:
            entry = self.selectedEntry()
            if not entry: return
            title=clean_text(entry.get("title", "")); topic=clean_text(entry.get("topic", "")); channel=clean_text(entry.get("channel", ""))
            date=_mediathek_date(entry.get("timestamp",0)); duration=_mediathek_duration(entry.get("duration",0)); episode=_mediathek_episode_hint(title, topic)
            self["preview_title"].setText(topic if topic and topic.lower()!=title.lower() else title)
            meta=[x for x in (channel, episode, date, duration) if x]
            self["preview_meta"].setText("\n".join(meta[:4]))
            if topic and topic.lower()!=title.lower():
                overview = "%s\n\n%s" % (title, clean_text(entry.get("description", "")))
            else:
                overview = clean_text(entry.get("description", ""))
            self["preview_overview"].setText(overview[:1100] or "Keine Beschreibung verfügbar.")
            self["poster_hint"].setText("Vorschaubild wird geladen …" if clean_text(entry.get("url_website", "")) else "")
            self._schedulePoster()
        except Exception as error:
            try: self["preview_overview"].setText(str(error))
            except Exception: pass

    def _schedulePoster(self):
        self._poster_token += 1
        try: self._poster_delay_timer.stop()
        except Exception: pass
        try: self._poster_delay_timer.start(450, True)
        except TypeError: self._poster_delay_timer.start(450)

    def _startPosterLoad(self):
        if self._poster_job is not None and self._poster_job.is_alive():
            try: self._poster_delay_timer.start(500, True)
            except TypeError: self._poster_delay_timer.start(500)
            return
        entry=self.selectedEntry()
        if not entry: return
        page=clean_text(entry.get("url_website", ""))
        if not page:
            self["poster_hint"].setText(""); return
        token=self._poster_token; snapshot=dict(entry); self._poster_result=None
        self._poster_job=threading.Thread(target=self._posterWorker,args=(token,snapshot)); self._poster_job.daemon=True; self._poster_job.start()
        try: self._poster_poll_timer.start(250, True)
        except TypeError: self._poster_poll_timer.start(250)

    def _posterWorker(self, token, entry):
        try:
            page=clean_text(entry.get("url_website", "")); image=_mediathek_page_image(page)
            path=""
            if image:
                key="mediathek_"+hashlib.sha1(page.encode("utf-8","ignore")).hexdigest()
                path=download_image_cached(image, POSTER_CACHE_DIR, key=key, timeout=10, max_bytes=4*1024*1024)
            self._poster_result=(token,path)
        except Exception:
            self._poster_result=(token,"")

    def _pollPoster(self):
        if self._poster_job is not None and self._poster_job.is_alive():
            try: self._poster_poll_timer.start(250, True)
            except TypeError: self._poster_poll_timer.start(250)
            return
        result=self._poster_result; self._poster_job=None; self._poster_result=None
        if not result: return
        token,path=result
        if token != self._poster_token: return
        if path:
            self._showPoster(path); self["poster_hint"].setText("")
        else:
            try: self["poster"].hide()
            except Exception: pass
            self["poster_hint"].setText("Kein Vorschaubild verfügbar")

    def _showPoster(self, path):
        if not path or ePicLoad is None: return
        try:
            self._poster_decoder=ePicLoad()
            try: self._poster_decoder.PictureData.get().append(self._posterDecoded)
            except Exception:
                try: self._poster_decoder.PictureData.connect(self._posterDecoded)
                except Exception: return
            self._poster_decoder.setPara((sx(225),sy(320),1,1,False,1,"#00000000"))
            self._poster_decoder.startDecode(path)
        except Exception: pass

    def _posterDecoded(self,*args):
        try:
            ptr=self._poster_decoder.getData() if self._poster_decoder is not None else None
            if ptr is not None and self["poster"].instance is not None:
                self["poster"].instance.setPixmap(ptr); self["poster"].show()
        except Exception: pass

    def _move(self, method):
        try: getattr(self["list"], method)()
        except Exception: pass
        self._selectionChanged()
    def keyUp(self): self._move("up")
    def keyDown(self): self._move("down")
    def pageUp(self): self._move("pageUp")
    def pageDown(self): self._move("pageDown")

    def openSearch(self):
        try: self.session.openWithCallback(self.searchEntered, VirtualKeyBoard, title=mediathek_copy("search_title"), text=self.term)
        except Exception as error: self._showError(error)

    def searchEntered(self,value=None):
        value=clean_text(value or "")
        if value==self.term: return
        self.term=value; self.reload()

    def playSelected(self):
        entry=self.selectedEntry()
        if not entry: return
        url=clean_text(entry.get("url", ""))
        if not url:
            self.session.open(MessageBox,"Kein abspielbarer Stream gefunden.",MessageBox.TYPE_ERROR,timeout=5); return
        try:
            ref=eServiceReference(4097,0,url); ref.setName(entry.get("title","Mediathek"))
            if EpiMoviePlayer is not None:
                self.session.open(EpiMoviePlayer,ref,["deu","ger","eng"],"",url,0,entry,[],-1)
            elif MoviePlayer is not None:
                self.session.open(MoviePlayer,ref)
            else:
                self.session.nav.playService(ref)
        except Exception as error:
            self._showError(error)

    def _showError(self,error):
        try: self.session.open(MessageBox,"Mediathek-Fehler:\n%s" % str(error),MessageBox.TYPE_ERROR,timeout=8)
        except Exception: pass


'''
t = t[:code_start] + new_code + t[code_end:]

p.write_text(t, encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.22/' "$TMP/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.22 Mediathek stability and visual preview/' "$TMP/control/control"

python3 -m py_compile "$PLUGIN"
grep -q 'PLUGIN_VERSION = "0.9.22"' "$PLUGIN"
grep -q 'class EpiMediathekHome' "$PLUGIN"
grep -q 'class EpiMediathekList' "$PLUGIN"
grep -q '_mediathek_page_image' "$PLUGIN"
grep -q 'preview_overview' "$PLUGIN"
grep -q 'Mediathek konnte nicht geöffnet werden' "$PLUGIN"

# API health is informative only; a third-party outage must not block packaging.
python3 - <<'PY' || true
import json
from urllib.request import Request,urlopen
body=json.dumps({"queries":[{"fields":["channel"],"query":"ARD"}],"sortBy":"timestamp","sortOrder":"desc","future":False,"offset":0,"size":2}).encode()
r=Request('https://mediathekviewweb.de/api/query',data=body,headers={'Content-Type':'application/json','User-Agent':'EpiMediaHub-v0922-smoke'})
data=json.loads(urlopen(r,timeout=10).read().decode('utf-8','replace'))
print('Mediathek smoke results:',len(data.get('result',{}).get('results',[])))
PY

tar --owner=0 --group=0 -czf "$TMP/pkg/control.tar.gz" -C "$TMP/control" .
tar --owner=0 --group=0 -czf "$TMP/pkg/data.tar.gz" -C "$TMP/data" .
cd "$TMP/pkg"
ar r "$WORKSPACE/EpiMediaHub_v0.9.22.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$WORKSPACE"

# User-data and size safety checks.
if ar p EpiMediaHub_v0.9.22.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2
  exit 1
fi
SIZE=$(stat -c%s EpiMediaHub_v0.9.22.ipk)
echo "v0.9.22 size: $SIZE bytes"
if [ "$SIZE" -gt 25165824 ]; then
  echo 'ERROR: package exceeds 24 MiB guard' >&2
  exit 1
fi
SHA=$(sha256sum EpiMediaHub_v0.9.22.ipk | awk '{print $1}')
echo "$SHA  EpiMediaHub_v0.9.22.ipk" > EpiMediaHub_v0.9.22.ipk.sha256
printf '{\n  "version": "0.9.22",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.22.ipk",\n  "sha256": "%s"\n}\n' "$SHA" > update.json
sha256sum -c EpiMediaHub_v0.9.22.ipk.sha256

rm -f EpiMediaHub_v0.9.21.ipk EpiMediaHub_v0.9.21.ipk.sha256
rm -f .github/workflows/inspect-v0921-mediathek-crash.yml
rm -f inspection/plugin_v0921.py inspection/v0921-mediathek-crash.txt

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.22 Mediathek stability and visual update'
git push
