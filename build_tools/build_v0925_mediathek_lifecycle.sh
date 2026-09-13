#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"
BASE="$WORKSPACE/EpiMediaHub_v0.9.24.ipk"
TMP=/tmp/epimedia0925
ROOT="$TMP/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub"
PLUGIN="$ROOT/plugin.py"

rm -rf "$TMP"
mkdir -p "$TMP/ar" "$TMP/data" "$TMP/control" "$TMP/pkg"
cd "$TMP/ar"
ar x "$BASE"
tar -xzf data.tar.gz -C ../data
tar -xzf control.tar.gz -C ../control
cp debian-binary ../pkg/debian-binary
rm -rf "$TMP/data/etc/enigma2/EpiMediaHub" "$TMP/data/etc/enigma2/epimediahub"

export PLUGIN
python3 - <<'PY'
import os
from pathlib import Path
p=Path(os.environ['PLUGIN'])
t=p.read_text(encoding='utf-8')
if 'PLUGIN_VERSION = "0.9.24"' not in t:
    raise SystemExit('Expected v0.9.24 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.24"','PLUGIN_VERSION = "0.9.25"',1)

# Keep blocking calls short because v0.9.25 deliberately keeps all Mediathek
# GUI work on Enigma2's main thread to remove screen-lifecycle races entirely.
t=t.replace('urlopen(req,timeout=15)', 'urlopen(req,timeout=8)')
t=t.replace('urlopen(req,timeout=12)', 'urlopen(req,timeout=5)')
t=t.replace('urlopen(req,timeout=10)', 'urlopen(req,timeout=4)')

class_start=t.find('class EpiMediathekList(Screen):')
class_end=t.find('class EpiMediaHubHome(Screen):',class_start)
if class_start<0 or class_end<0:
    raise SystemExit('Mediathek list class boundaries not found')

new_class=r'''class EpiMediathekList(Screen):
    skin=MEDIATHEK_LIST_SKIN

    def __init__(self,session,channel="",label="",term="",source_kind="mvw"):
        Screen.__init__(self,session)
        self.channel=clean_text(channel)
        self.channel_label=clean_text(label) or "Mediathek"
        self.term=clean_text(term)
        self.source_kind=source_kind
        self.results=[]
        self._closing=False
        self._load_timer=eTimer()
        self._poster_timer=eTimer()
        connect_timer(self._load_timer,self._loadNow)
        connect_timer(self._poster_timer,self._loadPosterNow)

        self["logo"]=Pixmap()
        self["title"]=Label(self.channel_label)
        self["subtitle"]=Label("")
        self["list"]=MenuList([])
        self["poster"]=Pixmap()
        self["preview_title"]=Label("")
        self["preview_meta"]=Label("")
        self["preview_overview"]=Label("")
        self["poster_hint"]=Label("")
        self["info"]=Label("")
        self["red"]=Label("ROT  Zurück")
        self["green"]=Label("GRÜN  Abspielen")
        self["yellow"]=Label("GELB  Suche")
        self["blue"]=Label("BLAU  Neu laden")
        self["actions"]=ActionMap(["OkCancelActions","DirectionActions","ColorActions"],{
            "ok":self.playSelected,
            "green":self.playSelected,
            "cancel":self.safeClose,
            "red":self.safeClose,
            "yellow":self.openSearch,
            "blue":self.reload,
            "up":self.keyUp,
            "down":self.keyDown,
            "left":self.pageUp,
            "right":self.pageDown
        },-1)
        self.onLayoutFinish.append(self._layout)

    def _timer_start(self,timer,delay):
        try:timer.stop()
        except Exception:pass
        try:timer.start(delay,True)
        except TypeError:timer.start(delay)
        except Exception:pass

    def _layout(self):
        try:self["poster"].hide()
        except Exception:pass
        try:self["list"].onSelectionChanged.append(self._selectionChanged)
        except Exception:pass
        self.reload()

    def safeClose(self):
        # Important: do not dismantle MenuList callbacks, native pixmaps or
        # Enigma2 components manually while Screen.close() is running.  Let
        # Enigma2 own teardown.  We only stop future timers and mark the screen.
        if self._closing:return
        self._closing=True
        try:self._load_timer.stop()
        except Exception:pass
        try:self._poster_timer.stop()
        except Exception:pass
        self.close()

    def reload(self):
        if self._closing:return
        try:self._load_timer.stop()
        except Exception:pass
        try:self._poster_timer.stop()
        except Exception:pass
        self.results=[]
        try:self["list"].setList(["Beiträge werden geladen ..."])
        except Exception:return
        self._clearPreview()
        try:self["subtitle"].setText("Suche: "+self.term if self.term else "Neueste Beiträge")
        except Exception:pass
        # Delay a few ms so the loading screen is painted first.  No Python
        # worker thread is used anywhere in this screen.
        self._timer_start(self._load_timer,30)

    def _loadNow(self):
        if self._closing:return
        try:
            if self.source_kind=="rai":
                items=_rai_query(self.term,45)
            else:
                items=_mediathek_query(self.channel,self.term,0,45)
        except Exception as error:
            if not self._closing:
                try:self["list"].setList(["Mediathek konnte nicht geladen werden"])
                except Exception:pass
                try:self["preview_overview"].setText(str(error))
                except Exception:pass
            return
        if self._closing:return
        self.results=list(items or [])
        if not self.results:
            try:self["list"].setList(["Keine abspielbaren Beiträge gefunden."])
            except Exception:pass
            return
        rows=[]
        for entry in self.results:
            topic=clean_text(entry.get("topic",""))
            title=clean_text(entry.get("title",""))
            dur=_mediathek_duration(entry.get("duration",0))
            shown=title if not topic or topic.lower()==title.lower() else "%s — %s"%(topic,title)
            rows.append(shown+("  ·  "+dur if dur else ""))
        try:self["list"].setList(rows)
        except Exception:return
        try:self["info"].setText("%d Beiträge"%len(self.results))
        except Exception:pass
        self._selectionChanged()

    def selectedEntry(self):
        if not self.results:return None
        try:index=int(self["list"].getSelectedIndex())
        except Exception:index=0
        return self.results[index] if 0<=index<len(self.results) else None

    def _clearPreview(self):
        for name in ("preview_title","preview_meta","preview_overview","poster_hint"):
            try:self[name].setText("")
            except Exception:pass
        try:self["poster"].hide()
        except Exception:pass

    def _selectionChanged(self):
        if self._closing:return
        entry=self.selectedEntry()
        if not entry:return
        title=clean_text(entry.get("title",""))
        topic=clean_text(entry.get("topic",""))
        channel=clean_text(entry.get("channel",""))
        date=_mediathek_date(entry.get("timestamp",0))
        dur=_mediathek_duration(entry.get("duration",0))
        episode=_mediathek_episode_hint(title,topic)
        try:self["preview_title"].setText(topic if topic and topic.lower()!=title.lower() else title)
        except Exception:pass
        try:self["preview_meta"].setText("\n".join([x for x in (channel,episode,date,dur) if x][:4]))
        except Exception:pass
        desc=clean_text(entry.get("description",""))
        overview=((title+"\n\n") if topic and topic.lower()!=title.lower() else "")+(desc or "Keine Beschreibung verfügbar.")
        try:self["preview_overview"].setText(overview[:1500])
        except Exception:pass

        # Always show a stable provider badge immediately; richer artwork is
        # attempted only after the user has rested on an item for 650 ms.
        fallback=clean_text(entry.get("fallback_image","")) or _mediathek_fallback_icon(self.channel,self.source_kind,self.channel_label)
        if fallback and os.path.isfile(fallback):
            self._showPoster(fallback)
        else:
            try:self["poster"].hide()
            except Exception:pass
        try:self["poster_hint"].setText("Vorschaubild wird geladen …")
        except Exception:pass
        self._timer_start(self._poster_timer,650)

    def _loadPosterNow(self):
        if self._closing:return
        entry=self.selectedEntry()
        if not entry:return
        source_url=clean_text(entry.get("url",""))
        page=clean_text(entry.get("url_website",""))
        image=clean_text(entry.get("poster_url","")) or clean_text(entry.get("image_url",""))
        page_desc=""
        try:
            if page and (not image or not clean_text(entry.get("description",""))):
                meta=_mediathek_page_meta(page)
                if not image:image=clean_text(meta.get("image",""))
                page_desc=clean_text(meta.get("description",""))
            path=""
            if image:
                key="mediathek_"+hashlib.sha1((image or page).encode("utf-8","ignore")).hexdigest()
                path=download_image_cached(image,POSTER_CACHE_DIR,key=key,timeout=4,max_bytes=5*1024*1024)
        except Exception:
            path=""
        if self._closing:return
        current=self.selectedEntry()
        if not current or clean_text(current.get("url",""))!=source_url:return
        if page_desc and not clean_text(current.get("description","")):
            current["description"]=page_desc
            try:self["preview_overview"].setText(page_desc[:1500])
            except Exception:pass
        if path:
            self._showPoster(path)
            return
        fallback=clean_text(current.get("fallback_image","")) or _mediathek_fallback_icon(self.channel,self.source_kind,self.channel_label)
        if fallback and os.path.isfile(fallback):self._showPoster(fallback)
        try:self["poster_hint"].setText("" if (path or fallback) else "Kein Vorschaubild verfügbar")
        except Exception:pass

    def _showPoster(self,path):
        if self._closing or not path:return
        try:
            instance=self["poster"].instance
            if instance is not None:
                instance.setPixmapFromFile(path)
                self["poster"].show()
                self["poster_hint"].setText("")
        except Exception:pass

    def _move(self,method):
        if self._closing:return
        try:getattr(self["list"],method)()
        except Exception:pass
        self._selectionChanged()

    def keyUp(self):self._move("up")
    def keyDown(self):self._move("down")
    def pageUp(self):self._move("pageUp")
    def pageDown(self):self._move("pageDown")

    def openSearch(self):
        if self._closing:return
        try:self.session.openWithCallback(self.searchEntered,VirtualKeyBoard,title="Mediathek durchsuchen",text=self.term)
        except Exception as error:
            try:self.session.open(MessageBox,str(error),MessageBox.TYPE_ERROR,timeout=6)
            except Exception:pass

    def searchEntered(self,value=None):
        if self._closing:return
        value=clean_text(value or "")
        if value!=self.term:
            self.term=value
            self.reload()

    def playSelected(self):
        if self._closing:return
        entry=self.selectedEntry()
        url=clean_text(entry.get("url","")) if entry else ""
        if not url:return
        try:
            ref=eServiceReference(4097,0,url)
            ref.setName(entry.get("title","Mediathek"))
            if EpiMoviePlayer is not None:
                self.session.open(EpiMoviePlayer,ref,["deu","ger","ita","tur","eng"],"",url,0,entry,[],-1)
            elif MoviePlayer is not None:
                self.session.open(MoviePlayer,ref)
            else:
                self.session.nav.playService(ref)
        except Exception as error:
            try:self.session.open(MessageBox,"Wiedergabe fehlgeschlagen:\n%s"%str(error),MessageBox.TYPE_ERROR,timeout=7)
            except Exception:pass


'''

t=t[:class_start]+new_class+t[class_end:]
p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.25/' "$TMP/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.25 lifecycle-safe Mediathek navigation/' "$TMP/control/control"

python3 -m py_compile "$PLUGIN"
grep -q 'PLUGIN_VERSION = "0.9.25"' "$PLUGIN"
grep -q 'class EpiMediathekList' "$PLUGIN"
grep -q 'No Python' "$PLUGIN"
# The rebuilt Mediathek list must contain no threading and no onClose teardown.
python3 - <<'PY'
import os
from pathlib import Path
p=Path(os.environ['PLUGIN'])
t=p.read_text(encoding='utf-8')
a=t.index('class EpiMediathekList(Screen):')
b=t.index('class EpiMediaHubHome(Screen):',a)
block=t[a:b]
for forbidden in ('threading.Thread','onClose.append','PictureData','_poster_job','_load_job'):
    if forbidden in block:
        raise SystemExit('Forbidden lifecycle primitive remains in Mediathek list: '+forbidden)
print('Mediathek lifecycle guard: OK')
PY

tar --owner=0 --group=0 -czf "$TMP/pkg/control.tar.gz" -C "$TMP/control" .
tar --owner=0 --group=0 -czf "$TMP/pkg/data.tar.gz" -C "$TMP/data" .
cd "$TMP/pkg"
ar r "$WORKSPACE/EpiMediaHub_v0.9.25.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$WORKSPACE"

if ar p EpiMediaHub_v0.9.25.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2
  exit 1
fi
SIZE=$(stat -c%s EpiMediaHub_v0.9.25.ipk)
echo "v0.9.25 size: $SIZE bytes"
[ "$SIZE" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
SHA=$(sha256sum EpiMediaHub_v0.9.25.ipk | awk '{print $1}')
echo "$SHA  EpiMediaHub_v0.9.25.ipk" > EpiMediaHub_v0.9.25.ipk.sha256
printf '{\n  "version": "0.9.25",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.25.ipk",\n  "sha256": "%s"\n}\n' "$SHA" > update.json
sha256sum -c EpiMediaHub_v0.9.25.ipk.sha256
rm -f EpiMediaHub_v0.9.24.ipk EpiMediaHub_v0.9.24.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.25 lifecycle-safe Mediathek'
git push
