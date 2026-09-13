#!/usr/bin/env python3
import os
from pathlib import Path

path = Path(os.environ["EPI_PLUGIN_FILE"])
text = path.read_text(encoding="utf-8")

def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit("%s: expected 1 match, got %d" % (label, count))
    text = text.replace(old, new, 1)

replace_once('PLUGIN_VERSION = "0.9.16"', 'PLUGIN_VERSION = "0.9.17"', 'version')

replace_once(
    'ACTIVE_THEME_CENTER_MARK = "/tmp/epimediahub_active_theme_center_mark.png"\n',
    'ACTIVE_THEME_CENTER_MARK = "/tmp/epimediahub_active_theme_center_mark.png"\n'
    'ACTIVE_THEME_HOME_MOTIF = "/tmp/epimediahub_active_home_motif.png"\n'
    'ACTIVE_THEME_BANNER = "/tmp/epimediahub_active_banner.png"\n'
    'ACTIVE_THEME_DIALOG = "/tmp/epimediahub_active_dialog.png"\n',
    'active theme assets'
)

start = text.index('def prepare_active_theme(theme_id=None):')
end = text.index('\n\nACTIVE_THEME_ID = prepare_active_theme()', start)
replacement = '''def prepare_active_theme(theme_id=None):
    theme_id = theme_id or _theme_id_from_settings_early()
    if theme_id not in THEME_CATALOG.get("themes", {}):
        theme_id = "default"
    meta = theme_meta(theme_id)
    source = os.path.join(THEME_DIR, str(meta.get("background", "default.png")))
    mark_source = os.path.join(THEME_DIR, "marks", "%s.png" % theme_id)
    center_mark_source = os.path.join(THEME_DIR, "center_marks", "%s.png" % theme_id)
    premium_sources = (
        (os.path.join(THEME_DIR, "home_motifs", "%s.png" % theme_id), ACTIVE_THEME_HOME_MOTIF),
        (os.path.join(THEME_DIR, "banner_motifs", "%s.png" % theme_id), ACTIVE_THEME_BANNER),
        (os.path.join(THEME_DIR, "dialog_motifs", "%s.png" % theme_id), ACTIVE_THEME_DIALOG),
    )
    try:
        for src, dst in ((source, ACTIVE_THEME_BACKGROUND), (mark_source, ACTIVE_THEME_MARK)):
            if os.path.isfile(src):
                shutil.copyfile(src, dst)
                try:
                    os.chmod(dst, 0o644)
                except Exception:
                    pass
        if os.path.isfile(center_mark_source):
            shutil.copyfile(center_mark_source, ACTIVE_THEME_CENTER_MARK)
        elif os.path.isfile(mark_source):
            shutil.copyfile(mark_source, ACTIVE_THEME_CENTER_MARK)
        for src, dst in premium_sources:
            if os.path.isfile(src):
                shutil.copyfile(src, dst)
                try:
                    os.chmod(dst, 0o644)
                except Exception:
                    pass
        try:
            if os.path.isfile(ACTIVE_THEME_CENTER_MARK):
                os.chmod(ACTIVE_THEME_CENTER_MARK, 0o644)
        except Exception:
            pass
    except Exception:
        pass
    return theme_id
'''
text = text[:start] + replacement + text[end:]

helper_anchor = '\n\ndef list_widget(name, x, y, w, h, f=24, item_h=44):'
if helper_anchor not in text:
    raise SystemExit('home motif helper anchor missing')
helper = '''

def theme_home_motif_pixmap(z=0):
    return '<ePixmap position="0,0" size="%d,%d" pixmap="%s" alphatest="blend" scale="1" zPosition="%d" />' % (
        GUI_W, GUI_H, ACTIVE_THEME_HOME_MOTIF, z
    )
'''
text = text.replace(helper_anchor, helper + helper_anchor, 1)

old_center = '''    # v0.9.12: one larger centered skin badge replaces the six small tile
    # watermarks. This makes the selected club/car/design much easier to see
    # and keeps all tile labels completely unobstructed.
    theme_center_mark_pixmap(525, 262, 230, 230, 0) +
'''
new_center = '''    # v0.9.17: one oversized motif spans the complete tile grid and is
    # clipped into the six tile windows at build time. No detached logo and
    # no repeated badge per tile: every tile shows its part of one image.
    theme_home_motif_pixmap(0) +
'''
replace_once(old_center, new_center, 'continuous home motif')

live_start = text.index('LIVE_PLAYER_SKIN = ')
live_end = text.index('\n\nCATEGORY_MANAGER_SKIN =', live_start)
live_skin = '''LIVE_PLAYER_SKIN = '<screen name="EpiLivePlayer" position="0,%d" size="%d,%d" flags="wfNoBorder" backgroundColor="#080D14">' % (
    sy(500), GUI_W, sy(220)
) + (
    '<ePixmap position="0,0" size="%d,%d" pixmap="%s" alphatest="blend" scale="1" zPosition="-2" />' % (GUI_W, sy(220), ACTIVE_THEME_BANNER) +
    '<widget name="picon" position="%s" size="%s" alphatest="on" scale="1" zPosition="2" />' % (pos(35, 10), size(92, 48)) +
    label_widget("channel", 145, 10, 540, 42, 27, "left", "center", None, "#FFFFFF") +
    '<widget name="weather_icon" position="%s" size="%s" alphatest="on" scale="1" zPosition="2" />' % (pos(785, 12), size(36, 36)) +
    label_widget("weather", 830, 10, 275, 42, 17, "right", "center", None, "#C8DBEC") +
    label_widget("clock", 1120, 10, 125, 42, 20, "right", "center", None, "#FFFFFF") +
    label_widget("now", 35, 62, 1210, 42, 21, "left", "center", None, "#F7FAFD") +
    label_widget("next", 35, 108, 1210, 35, 18, "left", "center", None, "#B7C7D7") +
    label_widget("help", 35, 162, 1210, 32, 15, "center", "center", None, "#8EA3B7")
) + '</screen>'
'''
text = text[:live_start] + live_skin + text[live_end:]

exit_skin_anchor = '\n\ndef ensure_data_dir():'
if exit_skin_anchor not in text:
    raise SystemExit('exit skin anchor missing')
exit_skin = '''

EXIT_CONFIRM_SKIN = '<screen name="EpiExitConfirm" position="center,center" size="%d,%d" flags="wfNoBorder" backgroundColor="#090E16">' % (sx(760), sy(330)) + (
    '<ePixmap position="0,0" size="%s" pixmap="%s" alphatest="blend" scale="1" zPosition="-2" />' % (size(760, 330), ACTIVE_THEME_DIALOG) +
    label_widget("exitTitle", 50, 34, 660, 48, 30, "center", "center", None, "#FFFFFF") +
    label_widget("exitQuestion", 60, 100, 640, 62, 22, "center", "center", None, "#E9F0F7") +
    label_widget("yes", 105, 200, 245, 62, 23, "center", "center", "#18222E", "#FFFFFF") +
    label_widget("no", 410, 200, 245, 62, 23, "center", "center", "#18222E", "#FFFFFF") +
    label_widget("exitHint", 70, 282, 620, 28, 15, "center", "center", None, "#8FA3B6")
) + '</screen>'
'''
text = text.replace(exit_skin_anchor, exit_skin + exit_skin_anchor, 1)

class_anchor = '\n\nclass EpiLivePlayer(Screen):'
if class_anchor not in text:
    raise SystemExit('exit class anchor missing')
exit_class = '''

class EpiExitConfirm(Screen):
    skin = EXIT_CONFIRM_SKIN

    def __init__(self, session):
        Screen.__init__(self, session)
        language = current_app_language()
        copy = {
            "de": ("Epi MediaHub beenden", "Möchtest du Epi MediaHub wirklich beenden?", "LINKS/RECHTS auswählen   |   OK bestätigen   |   EXIT abbrechen"),
            "en": ("Exit Epi MediaHub", "Do you really want to exit Epi MediaHub?", "LEFT/RIGHT select   |   OK confirm   |   EXIT cancel"),
            "tr": ("Epi MediaHub'dan çık", "Epi MediaHub'dan gerçekten çıkmak istiyor musun?", "SOL/SAĞ seç   |   OK onayla   |   EXIT iptal"),
            "it": ("Esci da Epi MediaHub", "Vuoi davvero uscire da Epi MediaHub?", "SINISTRA/DESTRA scegli   |   OK conferma   |   EXIT annulla"),
            "es": ("Salir de Epi MediaHub", "¿Realmente quieres salir de Epi MediaHub?", "IZQ./DER. seleccionar   |   OK confirmar   |   EXIT cancelar"),
        }
        title, question, hint = copy.get(language, copy["de"])
        self["exitTitle"] = Label(title)
        self["exitQuestion"] = Label(question)
        self["yes"] = Label(tr("yes"))
        self["no"] = Label(tr("no"))
        self["exitHint"] = Label(hint)
        self.current = 1
        self["actions"] = ActionMap(
            ["OkCancelActions", "DirectionActions"],
            {
                "ok": self.accept,
                "cancel": self.cancel,
                "left": self.selectYes,
                "right": self.selectNo,
                "up": self.toggle,
                "down": self.toggle,
            },
            -10
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
        if parseColor is None:
            return
        try:
            selected = parseColor(theme_accent())
            normal = parseColor("#18222E")
            for index, name in enumerate(("yes", "no")):
                widget = self[name]
                if widget.instance is not None:
                    widget.instance.setBackgroundColor(selected if index == self.current else normal)
                    widget.instance.setForegroundColor(parseColor("#FFFFFF"))
        except Exception:
            pass

    def accept(self):
        self.close(self.current == 0)

    def cancel(self):
        self.close(False)
'''
text = text.replace(class_anchor, exit_class + class_anchor, 1)

replace_once(
    '{"ok": self.openSelected, "cancel": self.close, "red": self.deleteSelected,',
    '{"ok": self.openSelected, "cancel": self.requestExit, "red": self.deleteSelected,',
    'profile exit action'
)
profile_anchor = '    def refreshList(self):\n'
profile_pos = text.index(profile_anchor, text.index('class EpiProfileSelect(Screen):'))
profile_methods = (
    '    def requestExit(self):\n'
    '        self.session.openWithCallback(self._exitConfirmed, EpiExitConfirm)\n\n'
    '    def _exitConfirmed(self, confirmed=False):\n'
    '        if confirmed:\n'
    '            self.close(None)\n\n'
)
text = text[:profile_pos] + profile_methods + text[profile_pos:]

replace_once(
    '                "menu": self.openHelp,\n                "cancel": self.close,\n                "left": self.keyLeft,',
    '                "menu": self.openHelp,\n                "cancel": self.requestExit,\n                "left": self.keyLeft,',
    'home exit action'
)
home_anchor = '    def openHelp(self):\n'
home_pos = text.index(home_anchor, text.index('class EpiMediaHubHome(Screen):'))
home_methods = (
    '    def requestExit(self):\n'
    '        self.session.openWithCallback(self._exitConfirmed, EpiExitConfirm)\n\n'
    '    def _exitConfirmed(self, confirmed=False):\n'
    '        if confirmed:\n'
    '            self.close()\n\n'
)
text = text[:home_pos] + home_methods + text[home_pos:]

release_anchor = '_RELEASE_NOTES = {\n'
if release_anchor not in text:
    raise SystemExit('release notes anchor missing')
release = '''_RELEASE_NOTES = {
    "0.9.17": {
        "de": ["Premium-Skin-Overhaul: Ein großes Logo-/Markenmotiv läuft jetzt fortlaufend durch alle sechs Startkacheln statt separat daneben zu stehen.", "Der Senderwechsel-Banner übernimmt den aktiven Skin mit dezentem Logo und Akzentfarbe; beim Beenden erscheint ein skinabhängiges Ja/Nein-Bestätigungsfenster."],
        "en": ["Premium skin overhaul: one large club/brand motif now continues through all six home tiles instead of sitting separately beside them.", "The channel-change banner now inherits the active skin with subtle branding and accent colour; exiting uses a skin-matched Yes/No confirmation dialog."],
        "tr": ["Premium tema yenilemesi: tek büyük kulüp/marka motifi artık ayrı durmak yerine altı ana kutucuğun tamamında kesintisiz devam ediyor.", "Kanal değiştirme bandı aktif temanın logo ve vurgu rengini kullanır; çıkışta temaya uygun Evet/Hayır onayı gösterilir."],
        "it": ["Restyling premium delle skin: un unico grande motivo club/marchio continua ora attraverso tutte e sei le tessere Home invece di apparire separato.", "Il banner del cambio canale eredita la skin attiva con branding discreto e colore accento; all'uscita compare una conferma Sì/No coordinata alla skin."],
        "es": ["Rediseño premium de skins: un gran motivo de club/marca continúa ahora a través de las seis baldosas de Inicio en lugar de aparecer separado.", "El banner al cambiar de canal hereda el skin activo con marca y color de acento discretos; al salir aparece una confirmación Sí/No adaptada al skin."]
    },
'''
text = text.replace(release_anchor, release, 1)

path.write_text(text, encoding='utf-8')
