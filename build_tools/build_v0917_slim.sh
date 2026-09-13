#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"
BASE_COMMIT="abed2d767ed0ad4bfc05167a5a81ef0f5112bf63"
ROOT=/tmp/epimedia0917slim/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub
PLUGIN="$ROOT/plugin.py"

rm -rf /tmp/epimedia0917slim
mkdir -p /tmp/epimedia0917slim/{ar,data,control,pkg}
git show "$BASE_COMMIT:EpiMediaHub_v0.9.16.ipk" > /tmp/EpiMediaHub_v0.9.16.ipk
cd /tmp/epimedia0917slim/ar
ar x /tmp/EpiMediaHub_v0.9.16.ipk
tar -xzf data.tar.gz -C ../data
tar -xzf control.tar.gz -C ../control
cp debian-binary ../pkg/debian-binary

python3 -m pip install --quiet pillow
export ROOT
python3 - <<'PY'
import json, os
from pathlib import Path
from PIL import Image, ImageDraw
root = Path(os.environ['ROOT'])
theme_dir = root / 'themes'
themes = json.loads((theme_dir / 'catalog.json').read_text(encoding='utf-8')).get('themes', {})
out_dir = theme_dir / 'home_motifs'
out_dir.mkdir(parents=True, exist_ok=True)
W, H = 585, 163
rects = [(0,0,275,48),(310,0,585,48),(0,58,275,105),(310,58,585,105),(0,115,275,163),(310,115,585,163)]
def load_mark(theme_id):
    for folder in ('center_marks','marks'):
        p = theme_dir / folder / ('%s.png' % theme_id)
        if p.is_file():
            try:
                im = Image.open(str(p)).convert('RGBA')
                box = im.getchannel('A').getbbox()
                if box:
                    return im.crop(box)
            except Exception:
                pass
    return Image.new('RGBA',(256,256),(0,0,0,0))
for theme_id in themes:
    mark = load_mark(theme_id)
    mw,mh = mark.size
    if mw and mh:
        scale = max(520.0/mw, 300.0/mh)
        mark = mark.resize((max(1,int(mw*scale)),max(1,int(mh*scale))), Image.LANCZOS)
    mark.putalpha(mark.getchannel('A').point(lambda p: int(p*0.28)))
    canvas = Image.new('RGBA',(W,H),(0,0,0,0))
    canvas.alpha_composite(mark,(int((W-mark.size[0])/2),int((H-mark.size[1])/2)))
    mask = Image.new('L',(W,H),0)
    draw = ImageDraw.Draw(mask)
    for rect in rects:
        draw.rounded_rectangle(rect,radius=9,fill=255)
    clipped = Image.new('RGBA',(W,H),(0,0,0,0))
    clipped.paste(canvas,(0,0),mask)
    try:
        clipped = clipped.quantize(colors=64, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    except Exception:
        pass
    clipped.save(str(out_dir / ('%s.png' % theme_id)), optimize=True)
print('Compact home motifs:', len(themes))
PY

export PLUGIN
python3 - <<'PY'
import os
from pathlib import Path
path = Path(os.environ['PLUGIN'])
text = path.read_text(encoding='utf-8')
def once(old,new,label):
    global text
    count=text.count(old)
    if count!=1:
        raise SystemExit('%s: expected 1 match, got %d' % (label,count))
    text=text.replace(old,new,1)
once('PLUGIN_VERSION = "0.9.16"','PLUGIN_VERSION = "0.9.17"','version')
once('ACTIVE_THEME_CENTER_MARK = "/tmp/epimediahub_active_theme_center_mark.png"\n','ACTIVE_THEME_CENTER_MARK = "/tmp/epimediahub_active_theme_center_mark.png"\nACTIVE_THEME_HOME_MOTIF = "/tmp/epimediahub_active_home_motif.png"\n','home motif path')
start=text.index('def prepare_active_theme(theme_id=None):')
end=text.index('\n\nACTIVE_THEME_ID = prepare_active_theme()',start)
replacement='''def prepare_active_theme(theme_id=None):
    theme_id = theme_id or _theme_id_from_settings_early()
    if theme_id not in THEME_CATALOG.get("themes", {}):
        theme_id = "default"
    meta = theme_meta(theme_id)
    source = os.path.join(THEME_DIR, str(meta.get("background", "default.png")))
    mark_source = os.path.join(THEME_DIR, "marks", "%s.png" % theme_id)
    center_mark_source = os.path.join(THEME_DIR, "center_marks", "%s.png" % theme_id)
    home_source = os.path.join(THEME_DIR, "home_motifs", "%s.png" % theme_id)
    try:
        for src, dst in ((source, ACTIVE_THEME_BACKGROUND), (mark_source, ACTIVE_THEME_MARK), (home_source, ACTIVE_THEME_HOME_MOTIF)):
            if os.path.isfile(src):
                shutil.copyfile(src, dst)
                try: os.chmod(dst, 0o644)
                except Exception: pass
        if os.path.isfile(center_mark_source):
            shutil.copyfile(center_mark_source, ACTIVE_THEME_CENTER_MARK)
        elif os.path.isfile(mark_source):
            shutil.copyfile(mark_source, ACTIVE_THEME_CENTER_MARK)
        try:
            if os.path.isfile(ACTIVE_THEME_CENTER_MARK): os.chmod(ACTIVE_THEME_CENTER_MARK, 0o644)
        except Exception: pass
    except Exception:
        pass
    return theme_id
'''
text=text[:start]+replacement+text[end:]
anchor='\n\ndef list_widget(name, x, y, w, h, f=24, item_h=44):'
helper='''

def theme_home_motif_pixmap(z=0):
    return '<ePixmap position="%s" size="%s" pixmap="%s" alphatest="blend" scale="1" zPosition="%d" />' % (pos(55, 210), size(1170, 325), ACTIVE_THEME_HOME_MOTIF, z)
'''
if anchor not in text: raise SystemExit('helper anchor missing')
text=text.replace(anchor,helper+anchor,1)
old_center='''    # v0.9.12: one larger centered skin badge replaces the six small tile
    # watermarks. This makes the selected club/car/design much easier to see
    # and keeps all tile labels completely unobstructed.
    theme_center_mark_pixmap(525, 262, 230, 230, 0) +
'''
new_center='''    # v0.9.17: one compact large motif is clipped across all six tile windows.
    theme_home_motif_pixmap(0) +
'''
once(old_center,new_center,'home motif')
live_start=text.index('LIVE_PLAYER_SKIN = ')
live_end=text.index('\n\nCATEGORY_MANAGER_SKIN =',live_start)
live_skin='''LIVE_PLAYER_SKIN = '<screen name="EpiLivePlayer" position="0,%d" size="%d,%d" flags="wfNoBorder" backgroundColor="#10151F">' % (sy(500), GUI_W, sy(220)) + (
    '<ePixmap position="%s" size="%s" pixmap="%s" alphatest="blend" scale="1" zPosition="0" />' % (pos(930, 12), size(300, 196), ACTIVE_THEME_CENTER_MARK) +
    label_widget("bannerAccent", 0, 0, 1280, 5, 10, "center", "center", "#FF000000") +
    '<widget name="picon" position="%s" size="%s" alphatest="on" scale="1" zPosition="3" />' % (pos(35, 10), size(92, 48)) +
    label_widget("channel", 145, 10, 540, 42, 27, "left", "center", None, "#FFFFFF") +
    '<widget name="weather_icon" position="%s" size="%s" alphatest="on" scale="1" zPosition="3" />' % (pos(785, 12), size(36, 36)) +
    label_widget("weather", 830, 10, 275, 42, 17, "right", "center", None, "#BBD4EA") +
    label_widget("clock", 1120, 10, 125, 42, 20, "right", "center", None, "#FFFFFF") +
    label_widget("now", 35, 62, 1210, 42, 21, "left", "center", None, "#F7FAFD") +
    label_widget("next", 35, 108, 1210, 35, 18, "left", "center", None, "#AFC0D4") +
    label_widget("help", 35, 162, 1210, 32, 15, "center", "center", None, "#7F93A8")
) + '</screen>'
'''
text=text[:live_start]+live_skin+text[live_end:]
once('        self["channel"] = Label("")\n','        self["channel"] = Label("")\n        self["bannerAccent"] = Label("")\n','banner accent widget')
once('        self["help"] = Label(tr("live_help"))\n','''        self["help"] = Label(tr("live_help"))
        if parseColor is not None:
            try:
                if self["bannerAccent"].instance is not None:
                    self["bannerAccent"].instance.setBackgroundColor(parseColor(theme_accent()))
            except Exception:
                pass
''','banner accent color')
exit_skin_anchor='\n\ndef ensure_data_dir():'
exit_skin='''

EXIT_CONFIRM_SKIN = '<screen name="EpiExitConfirm" position="center,center" size="%d,%d" flags="wfNoBorder" backgroundColor="#090E16">' % (sx(760), sy(330)) + (
    '<ePixmap position="%s" size="%s" pixmap="%s" alphatest="blend" scale="1" zPosition="0" />' % (pos(475, 65), size(230, 200), ACTIVE_THEME_CENTER_MARK) +
    label_widget("exitAccent", 0, 0, 760, 6, 10, "center", "center", "#FF000000") +
    label_widget("exitTitle", 50, 34, 660, 48, 30, "center", "center", None, "#FFFFFF") +
    label_widget("exitQuestion", 60, 100, 640, 62, 22, "center", "center", None, "#E9F0F7") +
    label_widget("yes", 105, 200, 245, 62, 23, "center", "center", "#18222E", "#FFFFFF") +
    label_widget("no", 410, 200, 245, 62, 23, "center", "center", "#18222E", "#FFFFFF") +
    label_widget("exitHint", 70, 282, 620, 28, 15, "center", "center", None, "#8FA3B6")
) + '</screen>'
'''
if exit_skin_anchor not in text: raise SystemExit('exit skin anchor missing')
text=text.replace(exit_skin_anchor,exit_skin+exit_skin_anchor,1)
class_anchor='\n\nclass EpiLivePlayer(Screen):'
exit_class='''

class EpiExitConfirm(Screen):
    skin = EXIT_CONFIRM_SKIN
    def __init__(self, session):
        Screen.__init__(self, session)
        language=current_app_language()
        copy={
            "de":("Epi MediaHub beenden","Möchtest du Epi MediaHub wirklich beenden?","LINKS/RECHTS auswählen   |   OK bestätigen   |   EXIT abbrechen"),
            "en":("Exit Epi MediaHub","Do you really want to exit Epi MediaHub?","LEFT/RIGHT select   |   OK confirm   |   EXIT cancel"),
            "tr":("Epi MediaHub'dan çık","Epi MediaHub'dan gerçekten çıkmak istiyor musun?","SOL/SAĞ seç   |   OK onayla   |   EXIT iptal"),
            "it":("Esci da Epi MediaHub","Vuoi davvero uscire da Epi MediaHub?","SINISTRA/DESTRA scegli   |   OK conferma   |   EXIT annulla"),
            "es":("Salir de Epi MediaHub","¿Realmente quieres salir de Epi MediaHub?","IZQ./DER. seleccionar   |   OK confirmar   |   EXIT cancelar")}
        title,question,hint=copy.get(language,copy["de"])
        self["exitTitle"]=Label(title); self["exitQuestion"]=Label(question)
        self["yes"]=Label(tr("yes")); self["no"]=Label(tr("no")); self["exitHint"]=Label(hint); self["exitAccent"]=Label("")
        self.current=1
        self["actions"]=ActionMap(["OkCancelActions","DirectionActions"],{"ok":self.accept,"cancel":self.cancel,"left":self.selectYes,"right":self.selectNo,"up":self.toggle,"down":self.toggle},-10)
        self.onLayoutFinish.append(self.updateUI)
    def selectYes(self): self.current=0; self.updateUI()
    def selectNo(self): self.current=1; self.updateUI()
    def toggle(self): self.current=1-int(self.current); self.updateUI()
    def updateUI(self):
        if parseColor is None: return
        try:
            accent=parseColor(theme_accent()); normal=parseColor("#18222E")
            if self["exitAccent"].instance is not None: self["exitAccent"].instance.setBackgroundColor(accent)
            for index,name in enumerate(("yes","no")):
                widget=self[name]
                if widget.instance is not None:
                    widget.instance.setBackgroundColor(accent if index==self.current else normal)
                    widget.instance.setForegroundColor(parseColor("#FFFFFF"))
        except Exception: pass
    def accept(self): self.close(self.current==0)
    def cancel(self): self.close(False)
'''
if class_anchor not in text: raise SystemExit('exit class anchor missing')
text=text.replace(class_anchor,exit_class+class_anchor,1)
once('{"ok": self.openSelected, "cancel": self.close, "red": self.deleteSelected,','{"ok": self.openSelected, "cancel": self.requestExit, "red": self.deleteSelected,','profile exit')
p_anchor='    def refreshList(self):\n'; p_pos=text.index(p_anchor,text.index('class EpiProfileSelect(Screen):'))
text=text[:p_pos]+'''    def requestExit(self):
        self.session.openWithCallback(self._exitConfirmed, EpiExitConfirm)

    def _exitConfirmed(self, confirmed=False):
        if confirmed:
            self.close(None)

'''+text[p_pos:]
once('                "menu": self.openHelp,\n                "cancel": self.close,\n                "left": self.keyLeft,','                "menu": self.openHelp,\n                "cancel": self.requestExit,\n                "left": self.keyLeft,','home exit')
h_anchor='    def openHelp(self):\n'; h_pos=text.index(h_anchor,text.index('class EpiMediaHubHome(Screen):'))
text=text[:h_pos]+'''    def requestExit(self):
        self.session.openWithCallback(self._exitConfirmed, EpiExitConfirm)

    def _exitConfirmed(self, confirmed=False):
        if confirmed:
            self.close()

'''+text[h_pos:]
release_anchor='_RELEASE_NOTES = {\n'
release='''_RELEASE_NOTES = {
    "0.9.17": {
        "de": ["Premium-Skin-Overhaul: Ein großes Motiv läuft fortlaufend durch alle sechs Startkacheln, jetzt platzsparend umgesetzt.", "Zapping-Banner und Exit-Bestätigung übernehmen den aktiven Skin direkt aus den vorhandenen Theme-Logos."],
        "en": ["Premium skin overhaul: one large motif continues through all six home tiles, now implemented with compact assets.", "The zapping banner and exit confirmation inherit the active skin directly from the existing theme logos."],
        "tr": ["Premium tema yenilemesi: tek büyük motif altı ana kutucukta kesintisiz devam eder ve artık kompakt biçimde uygulanır.", "Kanal bandı ve çıkış onayı aktif temayı mevcut tema logolarından doğrudan kullanır."],
        "it": ["Restyling premium: un unico grande motivo continua attraverso tutte e sei le tessere Home, ora con risorse compatte.", "Banner zapping e conferma uscita usano direttamente il logo della skin attiva."],
        "es": ["Rediseño premium: un gran motivo continúa por las seis baldosas de Inicio con recursos compactos.", "El banner de zapping y la confirmación de salida usan directamente el logotipo del skin activo."]
    },
'''
if release_anchor not in text: raise SystemExit('release notes anchor missing')
text=text.replace(release_anchor,release,1)
path.write_text(text,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.17/' /tmp/epimedia0917slim/control/control
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.17 premium skins slim fix/' /tmp/epimedia0917slim/control/control
python3 -m py_compile "$PLUGIN"
grep -q 'PLUGIN_VERSION = "0.9.17"' "$PLUGIN"
grep -q 'class EpiExitConfirm' "$PLUGIN"
grep -q 'theme_home_motif_pixmap' "$PLUGIN"

tar --owner=0 --group=0 -czf /tmp/epimedia0917slim/pkg/control.tar.gz -C /tmp/epimedia0917slim/control .
tar --owner=0 --group=0 -czf /tmp/epimedia0917slim/pkg/data.tar.gz -C /tmp/epimedia0917slim/data .
cd /tmp/epimedia0917slim/pkg
ar r "$WORKSPACE/EpiMediaHub_v0.9.17.ipk" debian-binary control.tar.gz data.tar.gz
cd "$WORKSPACE"
BYTES=$(stat -c%s EpiMediaHub_v0.9.17.ipk)
echo "Slim v0.9.17 size: $BYTES bytes"
test "$BYTES" -lt 25165824
sha256sum EpiMediaHub_v0.9.17.ipk > EpiMediaHub_v0.9.17.ipk.sha256
ar t EpiMediaHub_v0.9.17.ipk
sha256sum -c EpiMediaHub_v0.9.17.ipk.sha256
SHA=$(sha256sum EpiMediaHub_v0.9.17.ipk | cut -d ' ' -f1)
printf '{\n  "version": "0.9.17",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.17.ipk",\n  "sha256": "%s"\n}\n' "$SHA" > update.json

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add EpiMediaHub_v0.9.17.ipk EpiMediaHub_v0.9.17.ipk.sha256 update.json
git commit -m 'Replace v0.9.17 with slim premium build'
git push
