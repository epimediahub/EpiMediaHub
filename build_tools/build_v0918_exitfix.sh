#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"
ROOT=/tmp/epimedia0918/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub
PLUGIN="$ROOT/plugin.py"

rm -rf /tmp/epimedia0918
mkdir -p /tmp/epimedia0918/{ar,data,control,pkg}
cd /tmp/epimedia0918/ar
ar x "$WORKSPACE/EpiMediaHub_v0.9.17.ipk"
tar -xzf data.tar.gz -C ../data
tar -xzf control.tar.gz -C ../control
cp debian-binary ../pkg/debian-binary

export PLUGIN
python3 - <<'PY'
import os
from pathlib import Path

p = Path(os.environ['PLUGIN'])
t = p.read_text(encoding='utf-8')
if 'PLUGIN_VERSION = "0.9.17"' not in t:
    raise SystemExit('Expected v0.9.17 base')
t = t.replace('PLUGIN_VERSION = "0.9.17"', 'PLUGIN_VERSION = "0.9.18"', 1)

start = t.index('class EpiExitConfirm(Screen):')
end = t.index('\n\nclass EpiLivePlayer(Screen):', start)
new_class = '''class EpiExitConfirm(Screen):
    skin = EXIT_CONFIRM_SKIN

    def __init__(self, session):
        Screen.__init__(self, session)
        language = current_app_language()
        copy = {
            "de": ("Epi MediaHub beenden", "Möchtest du Epi MediaHub wirklich beenden?", "Ja", "Nein", "LINKS/RECHTS oder HOCH/RUNTER auswählen   |   OK bestätigen   |   GRÜN Ja   |   ROT/EXIT Nein"),
            "en": ("Exit Epi MediaHub", "Do you really want to exit Epi MediaHub?", "Yes", "No", "LEFT/RIGHT or UP/DOWN select   |   OK confirm   |   GREEN Yes   |   RED/EXIT No"),
            "tr": ("Epi MediaHub'dan çık", "Epi MediaHub'dan gerçekten çıkmak istiyor musun?", "Evet", "Hayır", "SOL/SAĞ veya YUKARI/AŞAĞI seç   |   OK onayla   |   YEŞİL Evet   |   KIRMIZI/EXIT Hayır"),
            "it": ("Esci da Epi MediaHub", "Vuoi davvero uscire da Epi MediaHub?", "Sì", "No", "SINISTRA/DESTRA o SU/GIÙ scegli   |   OK conferma   |   VERDE Sì   |   ROSSO/EXIT No"),
            "es": ("Salir de Epi MediaHub", "¿Realmente quieres salir de Epi MediaHub?", "Sí", "No", "IZQ./DER. o ARRIBA/ABAJO seleccionar   |   OK confirmar   |   VERDE Sí   |   ROJO/EXIT No"),
        }
        title, question, yes_text, no_text, hint = copy.get(language, copy["de"])
        self.yes_text = yes_text
        self.no_text = no_text
        self["exitTitle"] = Label(title)
        self["exitQuestion"] = Label(question)
        self["yes"] = Label(yes_text)
        self["no"] = Label(no_text)
        self["exitHint"] = Label(hint)
        self["exitAccent"] = Label("")
        # Safety first: default is always NO.
        self.current = 1
        self["actions"] = ActionMap(
            ["OkCancelActions", "DirectionActions", "ColorActions", "MenuActions"],
            {
                "ok": self.accept,
                "cancel": self.cancel,
                "left": self.selectYes,
                "right": self.selectNo,
                "up": self.toggle,
                "down": self.toggle,
                "green": self.confirmYes,
                "red": self.cancel,
            },
            -20,
        )
        self.onLayoutFinish.append(self.updateUI)

    def selectYes(self):
        self.current = 0
        self.updateUI()

    def selectNo(self):
        self.current = 1
        self.updateUI()

    def toggle(self):
        self.current = 1 - int(self.current)
        self.updateUI()

    def updateUI(self):
        # Text markers make the selection visible even on images where
        # dynamic widget background colours are not supported reliably.
        try:
            self["yes"].setText(("▶ " if self.current == 0 else "   ") + self.yes_text)
            self["no"].setText(("▶ " if self.current == 1 else "   ") + self.no_text)
        except Exception:
            pass
        if parseColor is None:
            return
        try:
            accent = parseColor(theme_accent())
            normal = parseColor("#18222E")
            if self["exitAccent"].instance is not None:
                self["exitAccent"].instance.setBackgroundColor(accent)
            for index, name in enumerate(("yes", "no")):
                widget = self[name]
                if widget.instance is not None:
                    widget.instance.setBackgroundColor(accent if index == self.current else normal)
                    widget.instance.setForegroundColor(parseColor("#FFFFFF"))
        except Exception:
            pass

    def accept(self):
        # OK only executes YES when YES is explicitly selected.
        if self.current == 0:
            self.close(True)
        else:
            self.close(False)

    def confirmYes(self):
        self.current = 0
        self.updateUI()
        self.close(True)

    def cancel(self):
        self.close(False)
'''
t = t[:start] + new_class + t[end:]

notes_anchor = '_RELEASE_NOTES = {\n'
if notes_anchor in t:
    notes = '''_RELEASE_NOTES = {
    "0.9.18": {
        "de": ["Exit-Dialog repariert: Ja/Nein lässt sich jetzt zuverlässig mit Pfeiltasten auswählen.", "Nein ist standardmäßig markiert; Grün bestätigt Ja, Rot/EXIT bricht ab und OK führt nur die markierte Auswahl aus."],
        "en": ["Fixed the exit dialog: Yes/No can now be selected reliably with the arrow keys.", "No is selected by default; Green confirms Yes, Red/EXIT cancels, and OK only executes the highlighted choice."],
        "tr": ["Çıkış penceresi düzeltildi: Evet/Hayır artık yön tuşlarıyla güvenilir biçimde seçilebilir.", "Varsayılan seçim Hayır; Yeşil Evet'i onaylar, Kırmızı/EXIT iptal eder ve OK yalnızca seçili seçeneği uygular."],
        "it": ["Corretto il dialogo di uscita: Sì/No ora si selezionano correttamente con i tasti freccia.", "No è selezionato di default; Verde conferma Sì, Rosso/EXIT annulla e OK esegue solo la scelta evidenziata."],
        "es": ["Corregido el diálogo de salida: Sí/No ahora se selecciona correctamente con las flechas.", "No queda seleccionado por defecto; Verde confirma Sí, Rojo/EXIT cancela y OK ejecuta solo la opción marcada."]
    },
'''
    t = t.replace(notes_anchor, notes, 1)

p.write_text(t, encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.18/' /tmp/epimedia0918/control/control
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.18 exit confirmation fix/' /tmp/epimedia0918/control/control
python3 -m py_compile "$PLUGIN"
grep -q 'PLUGIN_VERSION = "0.9.18"' "$PLUGIN"
grep -q '"green": self.confirmYes' "$PLUGIN"
grep -q 'self.current = 1' "$PLUGIN"

tar --owner=0 --group=0 -czf /tmp/epimedia0918/pkg/control.tar.gz -C /tmp/epimedia0918/control .
tar --owner=0 --group=0 -czf /tmp/epimedia0918/pkg/data.tar.gz -C /tmp/epimedia0918/data .
cd /tmp/epimedia0918/pkg
ar r "$WORKSPACE/EpiMediaHub_v0.9.18.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$WORKSPACE"
SIZE=$(stat -c%s EpiMediaHub_v0.9.18.ipk)
echo "v0.9.18 size: $SIZE bytes"
if [ "$SIZE" -gt 25165824 ]; then
    echo "ERROR: v0.9.18 exceeds 24 MiB guard" >&2
    exit 1
fi
SHA=$(sha256sum EpiMediaHub_v0.9.18.ipk | awk '{print $1}')
echo "$SHA  EpiMediaHub_v0.9.18.ipk" > EpiMediaHub_v0.9.18.ipk.sha256
python3 - <<PY
import json
p='update.json'
d=json.load(open(p,encoding='utf-8'))
d['version']='0.9.18'
d['url']='https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.18.ipk'
d['sha256']='$SHA'
open(p,'w',encoding='utf-8').write(json.dumps(d,indent=2)+'\n')
PY
sha256sum -c EpiMediaHub_v0.9.18.ipk.sha256
rm -f EpiMediaHub_v0.9.17.ipk EpiMediaHub_v0.9.17.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A EpiMediaHub_v0.9.17.ipk EpiMediaHub_v0.9.17.ipk.sha256 EpiMediaHub_v0.9.18.ipk EpiMediaHub_v0.9.18.ipk.sha256 update.json
git commit -m 'Publish EpiMediaHub v0.9.18 exit confirmation fix'
git push
