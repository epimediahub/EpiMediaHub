# -*- coding: utf-8 -*-
from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Screens.ChoiceBox import ChoiceBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from enigma import eServiceReference, eTimer, getDesktop
try:
    from enigma import iPlayableService, iServiceInformation
except Exception:
    iPlayableService = None
    iServiceInformation = None
try:
    from Components.ServiceEventTracker import ServiceEventTracker
except Exception:
    ServiceEventTracker = None
try:
    from Components.Language import language as enigma_language
except Exception:
    enigma_language = None
try:
    from enigma import eSize
except Exception:
    eSize = None
try:
    from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaTest
    from Tools.LoadPixmap import LoadPixmap
    from enigma import eListboxPythonMultiContent, gFont, RT_HALIGN_LEFT, RT_VALIGN_CENTER
    try:
        from enigma import BT_SCALE, BT_KEEP_ASPECT_RATIO
    except Exception:
        BT_SCALE = 0
        BT_KEEP_ASPECT_RATIO = 0
    HAS_MULTICONTENT = True
except Exception:
    MultiContentEntryText = None
    MultiContentEntryPixmapAlphaTest = None
    LoadPixmap = None
    eListboxPythonMultiContent = None
    gFont = None
    RT_HALIGN_LEFT = 0
    RT_VALIGN_CENTER = 0
    BT_SCALE = 0
    BT_KEEP_ASPECT_RATIO = 0
    HAS_MULTICONTENT = False
try:
    from enigma import ePicLoad
except Exception:
    ePicLoad = None

import base64
import calendar
import gzip
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
try:
    import ssl
except Exception:
    ssl = None
try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
except Exception:
    ThreadPoolExecutor = None
    as_completed = None
try:
    import requests
    from requests.adapters import HTTPAdapter
    try:
        from urllib3.util.retry import Retry as RequestsRetry
    except Exception:
        RequestsRetry = None
except Exception:
    requests = None
    HTTPAdapter = None
    RequestsRetry = None
try:
    import sqlite3
except Exception:
    sqlite3 = None
import time
import uuid
import xml.etree.ElementTree as ET

try:
    from skin import parseColor
except Exception:
    parseColor = None

try:
    from Screens.InfoBar import MoviePlayer
except Exception:
    MoviePlayer = None

try:
    import Screens.Standby as Standby
    from Screens.Standby import TryQuitMainloop
except Exception:
    Standby = None
    TryQuitMainloop = None

try:
    from Components.config import config
except Exception:
    config = None

try:
    from RecordTimer import RecordTimerEntry, AFTEREVENT
    from ServiceReference import ServiceReference
except Exception:
    RecordTimerEntry = None
    AFTEREVENT = None
    ServiceReference = None

try:
    from urllib.request import urlopen, Request
    from urllib.parse import urlparse, parse_qs, urlencode, quote, unquote
except ImportError:
    from urllib2 import urlopen, Request
    from urlparse import urlparse, parse_qs
    from urllib import urlencode, quote, unquote

try:
    from http.server import BaseHTTPRequestHandler, HTTPServer
except ImportError:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer


PLUGIN_VERSION = "0.9.41"
PLUGIN_DIR = os.path.dirname(os.path.realpath(__file__))
SPLASH_LOGO = os.path.join(PLUGIN_DIR, "splash.png")
HEADER_LOGO = os.path.join(PLUGIN_DIR, "header.png")
HOME_ICONS = [os.path.join(PLUGIN_DIR, "home_%s.png" % name) for name in ("live", "movies", "series", "mediathek", "playlist", "settings")]
MEDIATHEK_ICON_DIR = os.path.join(PLUGIN_DIR, "mediathek_picons")
HOME_GLASS_OVERLAY = os.path.join(PLUGIN_DIR, "home_glass_overlay.png")
SETTINGS_GLASS_OVERLAY = os.path.join(PLUGIN_DIR, "settings_glass_overlay.png")
BROWSER_GLASS_OVERLAY = os.path.join(PLUGIN_DIR, "browser_glass_overlay.png")
INTRO_FRAMES = [os.path.join(PLUGIN_DIR, "intro_%02d.png" % index) for index in range(10)]
INTRO_SOUND = os.path.join(PLUGIN_DIR, "intro_sound.wav")
WEATHER_ICONS = {name: os.path.join(PLUGIN_DIR, "weather_%s.png" % name) for name in ("sun", "cloud", "rain", "snow", "storm", "fog")}
CATEGORY_SERVICE_ICONS = {
    "netflix": os.path.join(PLUGIN_DIR, "category_netflix.png"),
    "prime": os.path.join(PLUGIN_DIR, "category_prime.png"),
    "disney": os.path.join(PLUGIN_DIR, "category_disney.png"),
    "sky": os.path.join(PLUGIN_DIR, "category_sky.png"),
    "max": os.path.join(PLUGIN_DIR, "category_max.png"),
    "paramount": os.path.join(PLUGIN_DIR, "category_paramount.png"),
    "apple": os.path.join(PLUGIN_DIR, "category_apple.png"),
    "dazn": os.path.join(PLUGIN_DIR, "category_dazn.png"),
}

DATA_DIR = "/etc/enigma2/epimediahub"
FTP_PLAYLIST_DIR = "/etc/enigma2/EpiMediaHub/playlists"
PLAYLIST_TEXT_FILE = "/etc/enigma2/EpiMediaHub/playlists.txt"
PROFILES_FILE = os.path.join(DATA_DIR, "profiles.json")
GLOBAL_SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
METADATA_CACHE_FILE = os.path.join(DATA_DIR, "metadata_cache.json")
POSTER_CACHE_DIR = os.path.join(DATA_DIR, "posters")
IMAGE_DEBUG_FILE = os.path.join(DATA_DIR, "image_debug.log")
PICON_CACHE_DIR = os.path.join(DATA_DIR, "picons")
ACTOR_CACHE_DIR = os.path.join(DATA_DIR, "actor_categories")
ACTOR_CACHE_FILE = os.path.join(DATA_DIR, "actor_category_cache.json")
SAGA_CACHE_DIR = os.path.join(DATA_DIR, "saga_categories")
SAGA_CACHE_FILE = os.path.join(DATA_DIR, "saga_category_cache.json")
WEATHER_CACHE_FILE = os.path.join(DATA_DIR, "weather_cache.json")
LEGACY_CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
LEGACY_PLAYLIST_FILE = os.path.join(DATA_DIR, "playlist.m3u")
LEGACY_FAVORITES_FILE = os.path.join(DATA_DIR, "favorites.json")
LEGACY_SSH_URL_FILE = os.path.join(DATA_DIR, "playlist_url.txt")

# -------------------- Themes / skins (v0.9.9) --------------------
# Theme artwork ships with the plugin. The currently selected background is
# copied to one stable /tmp path so every screen can reference the same pixmap.
# Changing a theme therefore does not require rebuilding all Enigma2 skin XML.
THEME_DIR = os.path.join(PLUGIN_DIR, "themes")
THEME_CATALOG_FILE = os.path.join(THEME_DIR, "catalog.json")
ACTIVE_THEME_BACKGROUND = "/tmp/epimediahub_active_theme.png"
ACTIVE_THEME_MARK = "/tmp/epimediahub_active_theme_mark.png"
ACTIVE_THEME_CENTER_MARK = "/tmp/epimediahub_active_theme_center_mark.png"
ACTIVE_THEME_HOME_MOTIF = "/tmp/epimediahub_active_home_motif.png"
ACTIVE_THEME_BANNER_MARK = "/tmp/epimediahub_active_banner_mark.png"
PLAYLIST_STATUS_ONLINE = os.path.join(PLUGIN_DIR, "playlist_status_online.png")
PLAYLIST_STATUS_OFFLINE = os.path.join(PLUGIN_DIR, "playlist_status_offline.png")

# Hidden Family Skin access. Only the SHA-256 digest is shipped; the code itself
# is never written to settings.json. Unlock state is persisted locally.
FAMILY_PIN_HASH = "ed946f65d2c785d90e827c5ffd879ce3b49c68d4c88013074176a7e73bc58bcf"



def _load_theme_catalog_early():
    try:
        with open(THEME_CATALOG_FILE, "r") as handle:
            value = json.load(handle)
        if isinstance(value, dict) and isinstance(value.get("themes"), dict):
            return value
    except Exception:
        pass
    return {
        "groups": [{"id": "standard", "label": "Epi MediaHub", "themes": ["default"]}],
        "themes": {"default": {"label": "Epi Dark", "group": "standard", "accent": "#1E88D8", "background": "default.png"}},
    }


THEME_CATALOG = _load_theme_catalog_early()


def _theme_id_from_settings_early():
    try:
        with open(GLOBAL_SETTINGS_FILE, "r") as handle:
            settings = json.load(handle)
        value = str(settings.get("skin_theme", "default")).strip()
    except Exception:
        value = "default"
    if value not in THEME_CATALOG.get("themes", {}):
        value = "default"
    return value


def theme_meta(theme_id=None):
    theme_id = theme_id or _theme_id_from_settings_early()
    themes = THEME_CATALOG.get("themes", {})
    return themes.get(theme_id) or themes.get("default", {})


def theme_display_name(theme_id=None):
    return str(theme_meta(theme_id).get("label", "Epi Dark"))


def theme_accent(theme_id=None):
    value = str(theme_meta(theme_id).get("accent", "#1E88D8"))
    return value if value.startswith("#") else "#1E88D8"


def theme_focus_background(theme_id=None):
    # Enigma2 uses #AARRGGBB with 00 = opaque and FF = fully transparent.
    # Keep focus neutral/dark so even white or yellow themes never turn the
    # whole selected tile into a bright block. The theme colour is carried by
    # the slim focus bar instead.
    return "#80101620"


def theme_focus_foreground(theme_id=None):
    return "#FFFFFF"


def prepare_active_theme(theme_id=None):
    theme_id = theme_id or _theme_id_from_settings_early()
    if theme_id not in THEME_CATALOG.get("themes", {}):
        theme_id = "default"
    meta = theme_meta(theme_id)
    source = os.path.join(THEME_DIR, str(meta.get("background", "default.png")))
    mark_source = os.path.join(THEME_DIR, "marks", "%s.png" % theme_id)
    center_mark_source = os.path.join(THEME_DIR, "center_marks", "%s.png" % theme_id)
    home_source = os.path.join(THEME_DIR, "home_motifs", "%s.png" % theme_id)
    banner_source = os.path.join(THEME_DIR, "banner_marks", "%s.png" % theme_id)
    try:
        for src, dst in ((source, ACTIVE_THEME_BACKGROUND), (mark_source, ACTIVE_THEME_MARK), (home_source, ACTIVE_THEME_HOME_MOTIF), (banner_source, ACTIVE_THEME_BANNER_MARK)):
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


ACTIVE_THEME_ID = prepare_active_theme()

_EPG_MEMORY_CACHE = {}
_EPG_QUICK_MEMORY_CACHE = {}
_XTREAM_EPG_MEMORY_CACHE = {}
_XTREAM_FULL_EPG_MEMORY_CACHE = {}
_DB_SCHEMA_READY = set()
_PICON_PIXMAP_CACHE = {}

try:
    _desktop = getDesktop(0).size()
    GUI_W = int(_desktop.width())
    GUI_H = int(_desktop.height())
except Exception:
    GUI_W, GUI_H = 1280, 720


def sx(value):
    return max(1, int(float(value) * GUI_W / 1280.0))


def sy(value):
    return max(1, int(float(value) * GUI_H / 720.0))


def sf(value):
    scale = min(float(GUI_W) / 1280.0, float(GUI_H) / 720.0)
    return max(12, int(float(value) * scale))


def pos(x, y):
    return "%d,%d" % (sx(x), sy(y))


def size(w, h):
    return "%d,%d" % (sx(w), sy(h))


def font(n):
    return "Regular;%d" % sf(n)


def build_fullscreen_skin(name, widgets):
    theme_layer = '<ePixmap position="0,0" size="%d,%d" pixmap="%s" alphatest="off" scale="1" zPosition="-10" />' % (GUI_W, GUI_H, ACTIVE_THEME_BACKGROUND)
    return '<screen name="%s" position="0,0" size="%d,%d" flags="wfNoBorder" backgroundColor="#070A10">%s%s</screen>' % (
        name, GUI_W, GUI_H, theme_layer, widgets
    )


def logo_widget(name="logo", x=42, y=18, w=390, h=130):
    return '<widget name="%s" position="%s" size="%s" pixmap="%s" alphatest="on" scale="1" />' % (
        name, pos(x, y), size(w, h), HEADER_LOGO
    )


def label_widget(name, x, y, w, h, f=22, align="left", valign="center", bg=None, fg="#F4F7FB"):
    attrs = [
        'name="%s"' % name,
        'position="%s"' % pos(x, y),
        'size="%s"' % size(w, h),
        'font="%s"' % font(f),
        'halign="%s"' % align,
        'valign="%s"' % valign,
        'foregroundColor="%s"' % fg,
    ]
    if bg:
        attrs.append('backgroundColor="%s"' % bg)
        attrs.append('transparent="0"')
    else:
        attrs.append('transparent="1"')
    return '<widget %s />' % " ".join(attrs)


def home_tile_widget(name, x, y, w=550, h=95, f=29):
    # v0.9.7: tile glass is baked into HOME_GLASS_OVERLAY. Keeping the Label
    # itself fully transparent is important on OpenATV: semi-transparent ARGB
    # widget backgrounds can otherwise reveal the receiver skin/desktop rather
    # than the EpiMediaHub ePixmap directly below it.
    return '<widget name="%s" position="%s" size="%s" font="%s" halign="center" valign="center" foregroundColor="#F8FAFC" transparent="1" shadowColor="#000000" shadowOffset="2,2" zPosition="1" />' % (
        name, pos(x, y), size(w, h), font(f)
    )


def overlay_pixmap(path, z=-5):
    return '<ePixmap position="0,0" size="%d,%d" pixmap="%s" alphatest="blend" scale="1" zPosition="%d" />' % (GUI_W, GUI_H, path, z)


def theme_mark_pixmap(x, y, w=150, h=76, z=2):
    return '<ePixmap position="%s" size="%s" pixmap="%s" alphatest="blend" scale="1" zPosition="%d" />' % (
        pos(x, y), size(w, h), ACTIVE_THEME_MARK, z
    )


def theme_center_mark_pixmap(x, y, w=230, h=230, z=0):
    return '<ePixmap position="%s" size="%s" pixmap="%s" alphatest="blend" scale="1" zPosition="%d" />' % (
        pos(x, y), size(w, h), ACTIVE_THEME_CENTER_MARK, z
    )


def theme_home_motif_pixmap(z=0):
    return '<ePixmap position="%s" size="%s" pixmap="%s" alphatest="blend" scale="1" zPosition="%d" />' % (pos(55, 210), size(1170, 325), ACTIVE_THEME_HOME_MOTIF, z)


def list_widget(name, x, y, w, h, f=24, item_h=44):
    # v0.9.7: the glass panel is an EpiMediaHub-owned PNG directly above the
    # active theme background. The MenuList itself is transparent so Enigma2
    # never composites a semi-transparent widget against the receiver/OpenATV
    # desktop. This removes the last OpenATV bleed-through from categories,
    # channel lists, VOD/series lists and search results.
    return '<widget name="%s" position="%s" size="%s" font="%s" itemHeight="%d" scrollbarMode="showOnDemand" foregroundColor="#F4F7FB" backgroundColor="#00101418" transparent="1" selectionColor="#FFFFFF" selectionBackgroundColor="#00232D39" />' % (
        name, pos(x, y), size(w, h), font(f), sy(item_h)
    )


def color_button(name, text_x, bg):
    return label_widget(name, text_x, 662, 275, 38, 18, "center", "center", bg, "#FFFFFF")


HOME_SKIN = build_fullscreen_skin(
    "EpiMediaHubHome",
    overlay_pixmap(HOME_GLASS_OVERLAY) +
    logo_widget() +
    label_widget("subtitle", 470, 35, 750, 45, 23, "right") +
    label_widget("hint", 470, 83, 750, 28, 16, "right", fg="#9EADBF") +
    # Clock + weather form one centered information block on the home screen.
    # The clock is deliberately large and uses the receiver's local system time.
    label_widget("clock", 455, 105, 430, 38, 30, "center", fg="#F4F7FB") +
    '<widget name="weather_icon" position="%s" size="%s" alphatest="on" scale="1" />' % (pos(395, 142), size(58, 58)) +
    label_widget("weather", 465, 140, 420, 36, 24, "center", fg="#E7F2FC") +
    label_widget("weather_detail", 465, 174, 420, 25, 17, "center", fg="#9ED4F2") +
    home_tile_widget("tile0", 55, 210, 550, 95, 29) +
    home_tile_widget("tile1", 675, 210, 550, 95, 29) +
    home_tile_widget("tile2", 55, 325, 550, 95, 29) +
    home_tile_widget("tile3", 675, 325, 550, 95, 29) +
    home_tile_widget("tile4", 55, 440, 550, 95, 27) +
    home_tile_widget("tile5", 675, 440, 550, 95, 27) +
    # v0.9.17: one compact large motif is clipped across all six tile windows.
    theme_home_motif_pixmap(0) +
    # Thin accent bars provide a clear focus cue while the tile itself remains translucent.
    label_widget("mark0", 55, 210, 8, 95, 12, "center", "center", "#FF000000") +
    label_widget("mark1", 675, 210, 8, 95, 12, "center", "center", "#FF000000") +
    label_widget("mark2", 55, 325, 8, 95, 12, "center", "center", "#FF000000") +
    label_widget("mark3", 675, 325, 8, 95, 12, "center", "center", "#FF000000") +
    label_widget("mark4", 55, 440, 8, 95, 12, "center", "center", "#FF000000") +
    label_widget("mark5", 675, 440, 8, 95, 12, "center", "center", "#FF000000") +
    '<ePixmap position="%s" size="%s" pixmap="%s" alphatest="on" scale="1" zPosition="3" />' % (pos(82, 222), size(70, 70), HOME_ICONS[0]) +
    '<ePixmap position="%s" size="%s" pixmap="%s" alphatest="on" scale="1" zPosition="3" />' % (pos(702, 222), size(70, 70), HOME_ICONS[1]) +
    '<ePixmap position="%s" size="%s" pixmap="%s" alphatest="on" scale="1" zPosition="3" />' % (pos(82, 337), size(70, 70), HOME_ICONS[2]) +
    '<ePixmap position="%s" size="%s" pixmap="%s" alphatest="on" scale="1" zPosition="3" />' % (pos(702, 337), size(70, 70), HOME_ICONS[3]) +
    '<ePixmap position="%s" size="%s" pixmap="%s" alphatest="on" scale="1" zPosition="3" />' % (pos(82, 452), size(70, 70), HOME_ICONS[4]) +
    '<ePixmap position="%s" size="%s" pixmap="%s" alphatest="on" scale="1" zPosition="3" />' % (pos(702, 452), size(70, 70), HOME_ICONS[5]) +
    label_widget("status", 55, 565, 1170, 42, 18, "center", "center") +
    label_widget("version", 1030, 620, 195, 28, 15, "right", fg="#708093")
)

PROFILE_SKIN = build_fullscreen_skin(
    "EpiProfileSelect",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) +
    logo_widget(w=345, h=115) +
    label_widget("title", 430, 35, 795, 48, 31, "right") +
    label_widget("subtitle", 430, 86, 795, 30, 18, "right", fg="#9EADBF") +
    list_widget("list", 70, 155, 1140, 390, 25, 48) +
    "".join('<widget name="profile_status%d" position="%s" size="%s" alphatest="on" scale="1" zPosition="4" />' %
            (i, pos(80, 164 + (i * 48)), size(28, 28)) for i in range(8)) +
    label_widget("info", 70, 560, 1140, 38, 17, "center", fg="#9EADBF") +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)

HELP_SKIN = build_fullscreen_skin(
    "EpiHelpScreen",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) +
    logo_widget(w=300, h=100) +
    label_widget("title", 380, 28, 845, 48, 31, "right") +
    label_widget("subtitle", 380, 78, 845, 30, 18, "right", fg="#9EADBF") +
    list_widget("list", 55, 135, 390, 455, 20, 48) +
    label_widget("detail", 475, 135, 750, 455, 19, "left", "top", "#0D121B", "#E7EEF7") +
    label_widget("info", 55, 600, 1170, 35, 16, "center", fg="#9EADBF") +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)

CATEGORY_SKIN = build_fullscreen_skin(
    "EpiCategoryScreen",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) +
    logo_widget(w=300, h=100) +
    label_widget("title", 380, 28, 845, 48, 31, "right") +
    label_widget("info", 380, 78, 845, 30, 18, "right", fg="#9EADBF") +
    list_widget("list", 70, 135, 1140, 460, 24, 44) +
    # Category icons stay separate from MenuList so they never interfere with
    # navigation. Live uses representative Picons; movies/series use a small
    # service badge when the category name identifies a platform.
    ''.join('<widget name="category_picon%d" position="%s" size="%s" alphatest="on" scale="1" zPosition="3" />' %
            (i, pos(76, 140 + (i * 44)), size(62, 34)) for i in range(10)) +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)

CONTENT_SKIN = build_fullscreen_skin(
    "EpiContentScreen",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) +
    logo_widget(w=300, h=100) +
    label_widget("title", 380, 28, 845, 48, 29, "right") +
    label_widget("info", 380, 78, 845, 30, 17, "right", fg="#9EADBF") +
    list_widget("list", 70, 135, 1140, 460, 21, 42) +
    # Live-TV deliberately uses the normal Enigma2 string MenuList again.
    # Picons are separate transparent Pixmap widgets, so they cannot interfere
    # with list focus or remote-control navigation.
    ''.join('<widget name="live_picon%d" position="%s" size="%s" alphatest="on" scale="1" zPosition="3" />' %
            (i, pos(76, 139 + (i * 42)), size(62, 34)) for i in range(10)) +
    # VOD/series preview: larger poster and substantially more readable text.
    # The list itself is resized at runtime only for movies/series; live keeps
    # the complete width for Picon + Now/Next EPG rows.
    label_widget("preview_panel", 620, 135, 590, 460, 1, "left", "top", None, "#0D121B") +
    '<widget name="preview_poster" position="%s" size="%s" alphatest="on" scale="1" />' % (pos(642, 155), size(235, 340)) +
    label_widget("preview_title", 900, 150, 290, 82, 25, "left", "top") +
    label_widget("preview_meta", 900, 238, 290, 125, 17, "left", "top", fg="#AFC0D4") +
    label_widget("preview_overview", 900, 370, 290, 205, 18, "left", "top", fg="#DCE7F3") +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)

SEASON_SKIN = build_fullscreen_skin(
    "EpiSeasonScreen",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) +
    logo_widget(w=300, h=100) +
    label_widget("title", 380, 28, 845, 48, 29, "right") +
    label_widget("info", 380, 78, 845, 30, 17, "right", fg="#9EADBF") +
    list_widget("list", 70, 135, 1140, 460, 24, 48) +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)

SETTINGS_SKIN = build_fullscreen_skin(
    "EpiSettings",
    overlay_pixmap(SETTINGS_GLASS_OVERLAY) +
    logo_widget(w=320, h=108) +
    label_widget("title", 390, 32, 835, 45, 30, "right") +
    label_widget("subtitle", 390, 80, 835, 30, 17, "right", fg="#9EADBF") +
    # Active-theme strip: same translucent language as the home tiles.
    label_widget("themePanel", 70, 120, 1140, 58, 18, "left", "center") +
    label_widget("themeAccent", 70, 120, 8, 58, 12, "center", "center", "#FF000000") +
    label_widget("themeName", 100, 120, 790, 58, 20, "left", "center", None, "#F8FAFC") +
    '<widget name="themePreview" position="%s" size="%s" pixmap="%s" alphatest="blend" scale="1" zPosition="3" />' % (pos(1010, 109), size(170, 76), ACTIVE_THEME_MARK) +
    # Settings list is intentionally more transparent so the selected skin
    # remains visible here too.
    '<widget name="list" position="%s" size="%s" font="%s" itemHeight="%d" scrollbarMode="showOnDemand" foregroundColor="#F4F7FB" backgroundColor="#00101418" transparent="1" selectionColor="#FFFFFF" selectionBackgroundColor="#00313B48" zPosition="1" />' % (pos(70, 192), size(1140, 392), font(21), sy(46)) +
    label_widget("info", 70, 595, 1140, 35, 16, "center", fg="#B4C7D9") +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)

DETAIL_SKIN = build_fullscreen_skin(
    "EpiDetailScreen",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) +
    logo_widget(w=300, h=100) +
    label_widget("title", 380, 30, 845, 45, 29, "right") +
    '<widget name="poster" position="%s" size="%s" alphatest="on" scale="1" />' % (pos(70, 145), size(290, 420)) +
    label_widget("rating", 400, 145, 810, 38, 22, "left", fg="#F5D96B") +
    label_widget("meta", 400, 190, 810, 40, 19, "left", fg="#AFC0D4") +
    label_widget("overview", 400, 245, 810, 320, 20, "left", "top", "#0D121B") +
    label_widget("source", 70, 590, 1140, 30, 15, "left", fg="#708093") +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)

EPG_SKIN = build_fullscreen_skin(
    "EpiEPGScreen",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) +
    logo_widget(w=300, h=100) +
    label_widget("title", 380, 28, 845, 48, 29, "right") +
    label_widget("now", 70, 135, 1140, 85, 20, "left", "center", "#0D121B") +
    list_widget("list", 70, 235, 1140, 355, 21, 46) +
    label_widget("info", 70, 600, 1140, 30, 16, "center", fg="#9EADBF") +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)

EPG_GRID_SKIN = build_fullscreen_skin(
    "EpiEPGGridScreen",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) +
    logo_widget(w=300, h=100) +
    label_widget("title", 380, 28, 845, 48, 29, "right") +
    label_widget("timeline", 70, 120, 1140, 42, 18, "center", "center", "#121A25", "#DDE8F5") +
    list_widget("list", 70, 170, 1140, 300, 18, 50) +
    label_widget("detail", 70, 482, 1140, 103, 18, "left", "top", "#0D121B", "#E7EEF7") +
    label_widget("info", 70, 595, 1140, 35, 15, "center", fg="#9EADBF") +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)

MEDIATHEK_HOME_SKIN = build_fullscreen_skin(
    "EpiMediathekHome",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) + logo_widget(w=300,h=100) +
    label_widget("title",380,28,845,48,31,"right") +
    label_widget("subtitle",380,78,845,30,18,"right",fg="#9EADBF") +
    list_widget("list",165,135,540,440,25,58) +
    ''.join('<widget name="country_icon%d" position="%s" size="%s" alphatest="on" scale="1" zPosition="5" />' % (i,pos(72,145+(i*58)),size(78,44)) for i in range(6)) +
    label_widget("provider_title",745,145,465,58,30,"left","top") +
    label_widget("provider_meta",745,212,465,58,18,"left","top",fg="#AFC0D4") +
    label_widget("provider_info",745,285,465,250,20,"left","top","#0D121B","#E7EEF7") +
    label_widget("info",55,600,1170,34,16,"center",fg="#9EADBF") +
    color_button("red",55,"#8D2830") + color_button("green",350,"#267A42") +
    color_button("yellow",645,"#8A7624") + color_button("blue",940,"#245B8F")
)

MEDIATHEK_DIRECTORY_SKIN = build_fullscreen_skin(
    "EpiMediathekDirectory",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) + logo_widget(w=300,h=100) +
    label_widget("title",380,28,845,48,31,"right") + label_widget("subtitle",380,78,845,30,18,"right",fg="#9EADBF") +
    list_widget("list",160,130,570,465,23,50) +
    ''.join('<widget name="provider_icon%d" position="%s" size="%s" alphatest="on" scale="1" zPosition="5" />' % (i,pos(72,136+(i*50)),size(72,40)) for i in range(9)) +
    '<widget name="hero_icon" position="%s" size="%s" alphatest="on" scale="1" zPosition="4" />' % (pos(790,145),size(180,100)) +
    label_widget("provider_title",790,260,410,65,28,"left","top") +
    label_widget("provider_meta",790,330,410,82,18,"left","top",fg="#AFC0D4") +
    label_widget("provider_info",790,420,410,155,18,"left","top","#0D121B","#E7EEF7") +
    label_widget("info",55,603,1170,31,16,"center",fg="#9EADBF") +
    color_button("red",55,"#8D2830") + color_button("green",350,"#267A42") +
    color_button("yellow",645,"#8A7624") + color_button("blue",940,"#245B8F")
)

MEDIATHEK_LIST_SKIN = build_fullscreen_skin(
    "EpiMediathekList",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) + logo_widget(w=300,h=100) +
    label_widget("title",380,28,845,48,29,"right") + label_widget("subtitle",380,78,845,30,17,"right",fg="#9EADBF") +
    list_widget("list",45,125,475,470,20,50) +
    '<widget name="poster" position="%s" size="%s" alphatest="on" scale="1" zPosition="3" />' % (pos(545,138),size(305,410)) +
    label_widget("preview_title",880,138,345,88,27,"left","top") +
    label_widget("preview_meta",880,232,345,105,18,"left","top",fg="#AFC0D4") +
    label_widget("preview_overview",880,345,345,220,18,"left","top","#0D121B","#E7EEF7") +
    label_widget("poster_hint",545,555,305,34,15,"center","center",fg="#8093A8") +
    label_widget("info",45,603,1180,31,15,"center",fg="#9EADBF") +
    color_button("red",55,"#8D2830") + color_button("green",350,"#267A42") +
    color_button("yellow",645,"#8A7624") + color_button("blue",940,"#245B8F")
)

SPLASH_SKIN = build_fullscreen_skin(
    "EpiSplash",
    '<widget name="intro" position="0,0" size="%d,%d" alphatest="off" scale="1" />' % (GUI_W, GUI_H) +
    label_widget("version", 0, 646, 1280, 28, 15, "center", fg="#6F8298") +
    label_widget("skip", 0, 678, 1280, 24, 14, "center", fg="#8296AB")
)


# Bottom banner overlay for Live-TV. The screen only occupies the lower area,
# so the video remains fully visible behind it.
LIVE_PLAYER_SKIN = '<screen name="EpiLivePlayer" position="0,%d" size="%d,%d" flags="wfNoBorder" backgroundColor="#10151F">' % (sy(500), GUI_W, sy(220)) + (
    '<ePixmap position="%s" size="%s" pixmap="%s" alphatest="blend" scale="1" zPosition="0" />' % (pos(1010, 20), size(230, 180), ACTIVE_THEME_BANNER_MARK) +
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


CATEGORY_MANAGER_SKIN = build_fullscreen_skin(
    "EpiCategoryManager",
    overlay_pixmap(BROWSER_GLASS_OVERLAY) +
    logo_widget(w=300, h=100) +
    label_widget("title", 380, 28, 845, 48, 29, "right") +
    label_widget("info", 380, 78, 845, 30, 17, "right", fg="#9EADBF") +
    list_widget("list", 70, 135, 1140, 460, 21, 44) +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)

PIN_SKIN = build_fullscreen_skin(
    "EpiPinScreen",
    logo_widget(w=300, h=100) +
    label_widget("title", 250, 210, 780, 55, 31, "center") +
    label_widget("pin", 390, 300, 500, 70, 40, "center", "center", "#141B27") +
    label_widget("info", 250, 400, 780, 40, 17, "center", fg="#9EADBF")
)


EXIT_CONFIRM_SKIN = '<screen name="EpiExitConfirm" position="center,center" size="%d,%d" flags="wfNoBorder" backgroundColor="#090E16">' % (sx(760), sy(330)) + (
    '<ePixmap position="%s" size="%s" pixmap="%s" alphatest="blend" scale="1" zPosition="0" />' % (pos(475, 65), size(230, 200), ACTIVE_THEME_CENTER_MARK) +
    label_widget("exitAccent", 0, 0, 760, 6, 10, "center", "center", "#FF000000") +
    label_widget("exitTitle", 50, 34, 660, 48, 30, "center", "center", None, "#FFFFFF") +
    label_widget("exitQuestion", 60, 100, 640, 62, 22, "center", "center", None, "#E9F0F7") +
    label_widget("yes", 105, 200, 245, 62, 23, "center", "center", "#18222E", "#FFFFFF") +
    label_widget("no", 410, 200, 245, 62, 23, "center", "center", "#18222E", "#FFFFFF") +
    label_widget("exitHint", 70, 282, 620, 28, 15, "center", "center", None, "#8FA3B6")
) + '</screen>'


def ensure_data_dir():
    for path in (DATA_DIR, FTP_PLAYLIST_DIR, POSTER_CACHE_DIR, PICON_CACHE_DIR, ACTOR_CACHE_DIR, SAGA_CACHE_DIR):
        try:
            if not os.path.isdir(path):
                os.makedirs(path)
        except Exception:
            pass
    try:
        os.chmod(DATA_DIR, 0o700)
    except Exception:
        pass

    # XStreamity-style text import: one M3U/M3U-Plus URL per line, followed
    # optionally by '# Playlistname'.  The file is created once and is never
    # overwritten, so it can safely be maintained via FTP/SFTP.
    try:
        if not os.path.exists(PLAYLIST_TEXT_FILE):
            with open(PLAYLIST_TEXT_FILE, "w") as handle:
                handle.write(
                    "# Epi MediaHub - einfache Playlist-Verwaltung\n"
                    "# Eine Playlist pro Zeile: M3U-PLUS-URL # Playlistname\n"
                    "# Beispiel:\n"
                    "# http://server:port/get.php?username=USER&password=PASS&type=m3u_plus&output=ts # Wohnzimmer\n"
                )
            try:
                os.chmod(PLAYLIST_TEXT_FILE, 0o600)
            except Exception:
                pass
    except Exception:
        pass


def clean_text(value):
    if value is None:
        return ""
    try:
        return value.strip()
    except Exception:
        return str(value).strip()

def first_text(mapping, *keys):
    if not isinstance(mapping, dict):
        return ""
    for key in keys:
        value = clean_text(mapping.get(key, ""))
        if value:
            return value
    return ""


def read_json(path, default):
    try:
        with open(path, "r") as handle:
            return json.load(handle)
    except Exception:
        return default


def write_json(path, value):
    ensure_data_dir()
    try:
        with open(path, "w") as handle:
            json.dump(value, handle, indent=2)
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        return True
    except Exception:
        return False



def load_global_settings():
    settings = read_json(GLOBAL_SETTINGS_FILE, {})
    if not isinstance(settings, dict):
        settings = {}
    settings.setdefault("tmdb_api_key", "")
    settings.setdefault("app_language", "system")
    settings.setdefault("skin_theme", "default")
    settings.setdefault("family_skins_unlocked", False)
    settings.setdefault("metadata_language", "de-DE")
    settings.setdefault("actor_category_images", True)
    settings.setdefault("resume_enabled", True)
    settings.setdefault("parental_enabled", False)
    settings.setdefault("parental_pin_hash", "")
    settings.setdefault("parental_auto_adult", True)
    settings.setdefault("update_manifest_url", "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/update.json")
    settings.setdefault("auto_update_check", True)
    # Optional boot autostart. Kept disabled by default so installing/updating
    # Epi MediaHub never changes the receiver's normal startup behaviour.
    settings.setdefault("autostart_app", False)
    settings.setdefault("last_update_check", 0)
    settings.setdefault("last_update_error", "")
    settings.setdefault("last_update_success", "")
    # The release-notes window is shown once after each installed app version.
    settings.setdefault("last_seen_version", "")
    settings.setdefault("fast_api_timeout", 20)
    # Weather is intentionally lightweight and asynchronous. Empty location
    # means IP-based automatic location detection by wttr.in.
    settings.setdefault("weather_enabled", True)
    settings.setdefault("weather_location", "")
    return settings

def save_global_settings(settings):
    global _APP_LANGUAGE_CACHE
    _APP_LANGUAGE_CACHE = None
    return write_json(GLOBAL_SETTINGS_FILE, settings)


# -------------------- App language / localisation --------------------

_APP_LANGUAGE_CACHE = None
SUPPORTED_APP_LANGUAGES = ("de", "en", "tr", "it", "es")


def system_app_language():
    try:
        value = clean_text(enigma_language.getLanguage() if enigma_language is not None else "")
    except Exception:
        value = ""
    value = value.lower().replace("-", "_")
    prefix = value.split("_", 1)[0]
    return prefix if prefix in SUPPORTED_APP_LANGUAGES else "de"


def current_app_language():
    global _APP_LANGUAGE_CACHE
    if _APP_LANGUAGE_CACHE in SUPPORTED_APP_LANGUAGES:
        return _APP_LANGUAGE_CACHE
    settings = read_json(GLOBAL_SETTINGS_FILE, {})
    selected = clean_text(settings.get("app_language", "system")).lower() if isinstance(settings, dict) else "system"
    if selected == "system" or selected not in SUPPORTED_APP_LANGUAGES:
        selected = system_app_language()
    _APP_LANGUAGE_CACHE = selected
    return selected


_TRANSLATIONS = {
    "de": {
        "system": "Systemsprache", "german": "Deutsch", "english": "Englisch", "turkish": "Türkisch", "italian": "Italienisch", "spanish": "Spanisch",
        "live": "LIVE-TV", "movies": "FILME", "series": "SERIEN", "search": "SUCHE", "switch_playlist": "PLAYLIST WECHSELN", "settings": "EINSTELLUNGEN",
        "back": "Zurück", "favorite": "Favorit", "favorites": "Favoriten", "sort": "Sortieren", "all": "ALLE", "recent": "Zuletzt angesehen",
        "select_category": "Kategorie auswählen", "manage_categories": "Kategorien verwalten", "visible": "sichtbar", "entries": "Einträge", "movie_info": "Filminfos",
        "help": "Hilfe", "help_guides": "Hilfe & Anleitungen", "playlist": "Playlist", "no_playlist": "Keine Playlist",
        "app_language": "App-Sprache", "metadata_language": "Sprache der Filminfos", "on": "Ein", "off": "Aus", "yes": "Ja", "no": "Nein",
        "system_active": "System ({language})", "active": "AKTIV",
        "home_hint": "OK auswählen   |   MENU = Hilfe & Anleitungen   |   INFO in Listen = EPG / Filminfos",
        "live_help": "CH +/- oder Pfeile = Sender wechseln   |   INFO = Banner   |   OK/EXIT = Senderliste",
        "channel_unavailable": "Dieser Stream ist derzeit nicht verfügbar oder defekt. Bitte versuchen Sie es später noch einmal.",
        "channel_unavailable_title": "STREAM NICHT VERFÜGBAR",
        "now": "JETZT", "next": "DANACH", "no_title": "Ohne Titel", "channel": "Sender",
        "epg_loading": "EPG wird geladen …", "no_epg": "Keine EPG-Daten für diesen Sender",
        "season_select": "Staffel auswählen", "season": "Staffel", "episode": "Folge", "episodes": "Folgen", "specials": "Specials", "more_episodes": "Weitere Folgen",
        "season_info": "{count} Staffeln / Bereiche   |   OK = Folgen anzeigen", "season_empty": "In dieser Staffel wurden keine Folgen gefunden.",
        "series_empty": "Für diese Serie wurden keine Episoden gefunden.", "series_load_error": "Serienfolgen konnten nicht geladen werden:\n{error}",
        "continue_question": "Wiedergabe bei ca. Minute {minutes} fortsetzen?", "playback_failed": "Wiedergabe fehlgeschlagen:\n{error}",
        "no_entries": "Keine Einträge vorhanden.", "no_recent": "Noch nichts angesehen.",
        "recent_info": "Zuletzt angesehene Inhalte – neueste zuerst",
        "settings_title": "EINSTELLUNGEN", "settings_change": "OK = Einstellung ändern   |   Kategorien ausblenden: in LIVE-TV/FILME/SERIEN über MENU",
        "load_playlist": "Playlist laden", "scan": "FTP/SFTP Scan", "update_epg": "EPG jetzt aktualisieren",
        "playlist_name": "Playlist-Name", "data_mode": "Datenmodus", "m3u_source": "M3U-Quelle", "audio_language": "Bevorzugte Audiosprache",
        "tmdb_key": "TMDb API-Key / Token (für Schauspielerbilder)", "movie_infos": "Filminfos", "actor_images": "Schauspielerbilder",
        "resume": "Wiedergabe fortsetzen", "weather": "Standort & Wetter anzeigen", "weather_location": "Wetter-Standort / PLZ",
        "parental": "Kindersicherung", "adult_auto": "18+ Kategorien automatisch sperren", "pin": "Kindersicherungs-PIN",
        "clear_cache": "Metadaten-Cache löschen", "update_source": "Update-Quelle", "auto_updates": "Automatisch nach Updates suchen (24h)",
        "autostart": "Epi MediaHub beim Start und nach Standby automatisch öffnen", "playlist_help": "Hilfe & Anleitungen zu Playlists", "check_updates": "Nach Updates suchen (aktuell v{version})",
        "configured": "eingerichtet", "not_configured": "nicht eingerichtet", "set": "gesetzt", "not_set": "nicht gesetzt", "automatic": "Automatisch über Internet-IP",
        "category_info": "Kategorie auswählen   |   MENU = Kategorien verwalten   |   {count} sichtbar",
        "search_area": "Gesamten Bereich durchsuchen", "search_results": "Suchergebnisse: {query}",
        "added_favorite": "Zu Favoriten hinzugefügt", "removed_favorite": "Aus Favoriten entfernt",
        "help_title": "HILFE & ANLEITUNGEN", "help_subtitle": "Playlists per URL, FTP/SFTP oder SSH einrichten",
        "help_info": "HOCH/RUNTER = Thema wählen   |   GRÜN = FTP/SFTP Scan   |   EXIT = Zurück",
        "profile_title": "PLAYLISTEN", "profile_subtitle": "URL, SSH und FTP/SFTP gemeinsam verwalten",
        "delete": "Löschen", "add_url": "URL hinzufügen", "edit": "Bearbeiten",
    },
    "en": {
        "system": "System language", "german": "German", "english": "English", "turkish": "Turkish", "italian": "Italian", "spanish": "Spanish",
        "live": "LIVE TV", "movies": "MOVIES", "series": "SERIES", "search": "SEARCH", "switch_playlist": "SWITCH PLAYLIST", "settings": "SETTINGS",
        "back": "Back", "favorite": "Favorite", "favorites": "Favorites", "sort": "Sort", "all": "ALL", "recent": "Recently watched",
        "select_category": "Select category", "manage_categories": "Manage categories", "visible": "visible", "entries": "entries", "movie_info": "Movie info",
        "help": "Help", "help_guides": "Help & Guides", "playlist": "Playlist", "no_playlist": "No playlist",
        "app_language": "App language", "metadata_language": "Movie info language", "on": "On", "off": "Off", "yes": "Yes", "no": "No",
        "system_active": "System ({language})", "active": "ACTIVE",
        "home_hint": "OK select   |   MENU = Help & Guides   |   INFO in lists = EPG / movie info",
        "live_help": "CH +/- or arrows = change channel   |   INFO = banner   |   OK/EXIT = channel list",
        "channel_unavailable": "This stream is currently unavailable or broken. Please try again later.",
        "channel_unavailable_title": "STREAM UNAVAILABLE",
        "now": "NOW", "next": "NEXT", "no_title": "No title", "channel": "Channel",
        "epg_loading": "EPG is loading …", "no_epg": "No EPG data for this channel",
        "season_select": "Select season", "season": "Season", "episode": "Episode", "episodes": "Episodes", "specials": "Specials", "more_episodes": "More episodes",
        "season_info": "{count} seasons / sections   |   OK = show episodes", "season_empty": "No episodes were found in this season.",
        "series_empty": "No episodes were found for this series.", "series_load_error": "Series episodes could not be loaded:\n{error}",
        "continue_question": "Resume playback at about minute {minutes}?", "playback_failed": "Playback failed:\n{error}",
        "no_entries": "No entries available.", "no_recent": "Nothing watched yet.",
        "recent_info": "Recently watched – newest first",
        "settings_title": "SETTINGS", "settings_change": "OK = change setting   |   Hide categories in LIVE TV/MOVIES/SERIES via MENU",
        "load_playlist": "Load playlist", "scan": "FTP/SFTP scan", "update_epg": "Update EPG now",
        "playlist_name": "Playlist name", "data_mode": "Data mode", "m3u_source": "M3U source", "audio_language": "Preferred audio language",
        "tmdb_key": "TMDb API key / token (for actor images)", "movie_infos": "Movie info", "actor_images": "Actor images",
        "resume": "Resume playback", "weather": "Show location & weather", "weather_location": "Weather location / postal code",
        "parental": "Parental control", "adult_auto": "Automatically lock 18+ categories", "pin": "Parental PIN",
        "clear_cache": "Clear metadata cache", "update_source": "Update source", "auto_updates": "Automatically check for updates (24h)",
        "autostart": "Open Epi MediaHub at startup and after standby", "playlist_help": "Playlist help & guides", "check_updates": "Check for updates (current v{version})",
        "configured": "configured", "not_configured": "not configured", "set": "set", "not_set": "not set", "automatic": "Automatic via internet IP",
        "category_info": "Select category   |   MENU = manage categories   |   {count} visible",
        "search_area": "Search entire section", "search_results": "Search results: {query}",
        "added_favorite": "Added to favorites", "removed_favorite": "Removed from favorites",
        "help_title": "HELP & GUIDES", "help_subtitle": "Set up playlists via URL, FTP/SFTP or SSH",
        "help_info": "UP/DOWN = select topic   |   GREEN = FTP/SFTP scan   |   EXIT = Back",
        "profile_title": "PLAYLISTS", "profile_subtitle": "Manage URL, SSH and FTP/SFTP together",
        "delete": "Delete", "add_url": "Add URL", "edit": "Edit",
    },
    "tr": {
        "system": "Sistem dili", "german": "Almanca", "english": "İngilizce", "turkish": "Türkçe", "italian": "İtalyanca", "spanish": "İspanyolca",
        "live": "CANLI TV", "movies": "FİLMLER", "series": "DİZİLER", "search": "ARA", "switch_playlist": "OYNATMA LİSTESİ DEĞİŞTİR", "settings": "AYARLAR",
        "back": "Geri", "favorite": "Favori", "favorites": "Favoriler", "sort": "Sırala", "all": "TÜMÜ", "recent": "Son izlenenler",
        "select_category": "Kategori seç", "manage_categories": "Kategorileri yönet", "visible": "görünür", "entries": "öğe", "movie_info": "Film bilgisi",
        "help": "Yardım", "help_guides": "Yardım ve Kılavuzlar", "playlist": "Oynatma listesi", "no_playlist": "Oynatma listesi yok",
        "app_language": "Uygulama dili", "metadata_language": "Film bilgisi dili", "on": "Açık", "off": "Kapalı", "yes": "Evet", "no": "Hayır",
        "system_active": "Sistem ({language})", "active": "AKTİF",
        "home_hint": "OK = seç   |   MENU = Yardım   |   Listelerde INFO = EPG / film bilgisi",
        "live_help": "CH +/- veya oklar = kanal değiştir   |   INFO = bilgi bandı   |   OK/EXIT = kanal listesi",
        "channel_unavailable": "Bu yayın şu anda kullanılamıyor veya bozuk. Lütfen daha sonra tekrar deneyin.",
        "channel_unavailable_title": "YAYIN KULLANILAMIYOR",
        "now": "ŞİMDİ", "next": "SONRA", "no_title": "Başlıksız", "channel": "Kanal",
        "epg_loading": "EPG yükleniyor …", "no_epg": "Bu kanal için EPG verisi yok",
        "season_select": "Sezon seç", "season": "Sezon", "episode": "Bölüm", "episodes": "Bölümler", "specials": "Özel bölümler", "more_episodes": "Diğer bölümler",
        "season_info": "{count} sezon / bölüm   |   OK = bölümleri göster", "season_empty": "Bu sezonda bölüm bulunamadı.",
        "series_empty": "Bu dizi için bölüm bulunamadı.", "series_load_error": "Dizi bölümleri yüklenemedi:\n{error}",
        "continue_question": "Yaklaşık {minutes}. dakikadan devam edilsin mi?", "playback_failed": "Oynatma başarısız:\n{error}",
        "no_entries": "Kayıt yok.", "no_recent": "Henüz izlenen içerik yok.", "recent_info": "Son izlenenler – en yeni önce",
        "settings_title": "AYARLAR", "settings_change": "OK = ayarı değiştir   |   Kategorileri LIVE TV/FİLMLER/DİZİLER içinde MENU ile gizle",
        "load_playlist": "Listeyi yükle", "scan": "FTP/SFTP tara", "update_epg": "EPG'yi şimdi güncelle",
        "playlist_name": "Oynatma listesi adı", "data_mode": "Veri modu", "m3u_source": "M3U kaynağı", "audio_language": "Tercih edilen ses dili",
        "tmdb_key": "TMDb API anahtarı / token (oyuncu resimleri için)", "movie_infos": "Film bilgileri", "actor_images": "Oyuncu resimleri",
        "resume": "Oynatmaya devam et", "weather": "Konum ve hava durumunu göster", "weather_location": "Hava durumu konumu / posta kodu",
        "parental": "Ebeveyn kontrolü", "adult_auto": "18+ kategorileri otomatik kilitle", "pin": "Ebeveyn PIN'i",
        "clear_cache": "Meta veri önbelleğini temizle", "update_source": "Güncelleme kaynağı", "auto_updates": "Güncellemeleri otomatik kontrol et (24s)",
        "autostart": "Epi MediaHub'ı açılışta ve beklemeden sonra otomatik aç", "playlist_help": "Oynatma listesi yardım ve kılavuzları", "check_updates": "Güncellemeleri kontrol et (v{version})",
        "configured": "ayarlandı", "not_configured": "ayarlanmadı", "set": "ayarlandı", "not_set": "ayarlanmadı", "automatic": "İnternet IP'si ile otomatik",
        "category_info": "Kategori seç   |   MENU = kategorileri yönet   |   {count} görünür",
        "search_area": "Tüm bölümü ara", "search_results": "Arama sonuçları: {query}", "added_favorite": "Favorilere eklendi", "removed_favorite": "Favorilerden kaldırıldı",
        "help_title": "YARDIM VE KILAVUZLAR", "help_subtitle": "URL, FTP/SFTP veya SSH ile oynatma listesi kur", "help_info": "YUKARI/AŞAĞI = konu seç   |   YEŞİL = FTP/SFTP tara   |   EXIT = Geri",
        "profile_title": "OYNATMA LİSTELERİ", "profile_subtitle": "URL, SSH ve FTP/SFTP'yi birlikte yönet", "delete": "Sil", "add_url": "URL ekle", "edit": "Düzenle",
    },
    "it": {
        "system": "Lingua di sistema", "german": "Tedesco", "english": "Inglese", "turkish": "Turco", "italian": "Italiano", "spanish": "Spagnolo",
        "live": "TV LIVE", "movies": "FILM", "series": "SERIE", "search": "CERCA", "switch_playlist": "CAMBIA PLAYLIST", "settings": "IMPOSTAZIONI",
        "back": "Indietro", "favorite": "Preferito", "favorites": "Preferiti", "sort": "Ordina", "all": "TUTTI", "recent": "Visti di recente",
        "select_category": "Seleziona categoria", "manage_categories": "Gestisci categorie", "visible": "visibili", "entries": "elementi", "movie_info": "Info film",
        "help": "Aiuto", "help_guides": "Aiuto e guide", "playlist": "Playlist", "no_playlist": "Nessuna playlist",
        "app_language": "Lingua app", "metadata_language": "Lingua info film", "on": "Sì", "off": "No", "yes": "Sì", "no": "No",
        "system_active": "Sistema ({language})", "active": "ATTIVA",
        "home_hint": "OK = seleziona   |   MENU = Aiuto   |   INFO nelle liste = EPG / info film",
        "live_help": "CH +/- o frecce = cambia canale   |   INFO = banner   |   OK/EXIT = lista canali",
        "channel_unavailable": "Questo stream non è al momento disponibile o è difettoso. Riprova più tardi.", "channel_unavailable_title": "STREAM NON DISPONIBILE",
        "now": "ORA", "next": "DOPO", "no_title": "Senza titolo", "channel": "Canale", "epg_loading": "Caricamento EPG …", "no_epg": "Nessun dato EPG per questo canale",
        "season_select": "Seleziona stagione", "season": "Stagione", "episode": "Episodio", "episodes": "Episodi", "specials": "Speciali", "more_episodes": "Altri episodi",
        "season_info": "{count} stagioni / sezioni   |   OK = mostra episodi", "season_empty": "Nessun episodio trovato in questa stagione.", "series_empty": "Nessun episodio trovato per questa serie.",
        "series_load_error": "Impossibile caricare gli episodi:\n{error}", "continue_question": "Riprendere la riproduzione circa al minuto {minutes}?", "playback_failed": "Riproduzione non riuscita:\n{error}",
        "no_entries": "Nessun elemento disponibile.", "no_recent": "Nessun contenuto visto finora.", "recent_info": "Visti di recente – più recenti prima",
        "settings_title": "IMPOSTAZIONI", "settings_change": "OK = modifica impostazione   |   Nascondi categorie in TV LIVE/FILM/SERIE con MENU",
        "load_playlist": "Carica playlist", "scan": "Scansione FTP/SFTP", "update_epg": "Aggiorna EPG ora", "playlist_name": "Nome playlist", "data_mode": "Modalità dati", "m3u_source": "Sorgente M3U",
        "audio_language": "Lingua audio preferita", "tmdb_key": "Chiave API / token TMDb (per foto attori)", "movie_infos": "Info film", "actor_images": "Foto attori",
        "resume": "Riprendi riproduzione", "weather": "Mostra posizione e meteo", "weather_location": "Località meteo / CAP", "parental": "Controllo genitori",
        "adult_auto": "Blocca automaticamente categorie 18+", "pin": "PIN controllo genitori", "clear_cache": "Cancella cache metadati", "update_source": "Fonte aggiornamenti",
        "auto_updates": "Controlla aggiornamenti automaticamente (24h)", "autostart": "Apri Epi MediaHub all'avvio e dopo lo standby", "playlist_help": "Aiuto e guide playlist",
        "check_updates": "Cerca aggiornamenti (v{version})", "configured": "configurato", "not_configured": "non configurato", "set": "impostato", "not_set": "non impostato", "automatic": "Automatico via IP internet",
        "category_info": "Seleziona categoria   |   MENU = gestisci categorie   |   {count} visibili", "search_area": "Cerca in tutta la sezione", "search_results": "Risultati: {query}",
        "added_favorite": "Aggiunto ai preferiti", "removed_favorite": "Rimosso dai preferiti", "help_title": "AIUTO E GUIDE", "help_subtitle": "Configura playlist via URL, FTP/SFTP o SSH",
        "help_info": "SU/GIÙ = scegli argomento   |   VERDE = scansione FTP/SFTP   |   EXIT = Indietro", "profile_title": "PLAYLIST", "profile_subtitle": "Gestisci URL, SSH e FTP/SFTP insieme",
        "delete": "Elimina", "add_url": "Aggiungi URL", "edit": "Modifica",
    },
    "es": {
        "system": "Idioma del sistema", "german": "Alemán", "english": "Inglés", "turkish": "Turco", "italian": "Italiano", "spanish": "Español",
        "live": "TV EN DIRECTO", "movies": "PELÍCULAS", "series": "SERIES", "search": "BUSCAR", "switch_playlist": "CAMBIAR LISTA", "settings": "AJUSTES",
        "back": "Atrás", "favorite": "Favorito", "favorites": "Favoritos", "sort": "Ordenar", "all": "TODOS", "recent": "Vistos recientemente",
        "select_category": "Seleccionar categoría", "manage_categories": "Gestionar categorías", "visible": "visibles", "entries": "elementos", "movie_info": "Info de película",
        "help": "Ayuda", "help_guides": "Ayuda y guías", "playlist": "Lista", "no_playlist": "Sin lista", "app_language": "Idioma de la app", "metadata_language": "Idioma de info de películas",
        "on": "Activado", "off": "Desactivado", "yes": "Sí", "no": "No", "system_active": "Sistema ({language})", "active": "ACTIVA",
        "home_hint": "OK = seleccionar   |   MENU = Ayuda   |   INFO en listas = EPG / info de película",
        "live_help": "CH +/- o flechas = cambiar canal   |   INFO = banner   |   OK/EXIT = lista de canales",
        "channel_unavailable": "Este stream no está disponible actualmente o está defectuoso. Inténtelo de nuevo más tarde.", "channel_unavailable_title": "STREAM NO DISPONIBLE",
        "now": "AHORA", "next": "DESPUÉS", "no_title": "Sin título", "channel": "Canal", "epg_loading": "Cargando EPG …", "no_epg": "No hay datos EPG para este canal",
        "season_select": "Seleccionar temporada", "season": "Temporada", "episode": "Episodio", "episodes": "Episodios", "specials": "Especiales", "more_episodes": "Más episodios",
        "season_info": "{count} temporadas / secciones   |   OK = mostrar episodios", "season_empty": "No se encontraron episodios en esta temporada.", "series_empty": "No se encontraron episodios para esta serie.",
        "series_load_error": "No se pudieron cargar los episodios:\n{error}", "continue_question": "¿Continuar aproximadamente desde el minuto {minutes}?", "playback_failed": "Error de reproducción:\n{error}",
        "no_entries": "No hay elementos disponibles.", "no_recent": "Todavía no se ha visto nada.", "recent_info": "Vistos recientemente – más recientes primero",
        "settings_title": "AJUSTES", "settings_change": "OK = cambiar ajuste   |   Oculta categorías en TV/PELÍCULAS/SERIES con MENU",
        "load_playlist": "Cargar lista", "scan": "Escanear FTP/SFTP", "update_epg": "Actualizar EPG ahora", "playlist_name": "Nombre de lista", "data_mode": "Modo de datos", "m3u_source": "Fuente M3U",
        "audio_language": "Idioma de audio preferido", "tmdb_key": "Clave API / token TMDb (para fotos de actores)", "movie_infos": "Info de películas", "actor_images": "Fotos de actores",
        "resume": "Continuar reproducción", "weather": "Mostrar ubicación y tiempo", "weather_location": "Ubicación del tiempo / CP", "parental": "Control parental",
        "adult_auto": "Bloquear categorías 18+ automáticamente", "pin": "PIN parental", "clear_cache": "Borrar caché de metadatos", "update_source": "Fuente de actualizaciones",
        "auto_updates": "Buscar actualizaciones automáticamente (24h)", "autostart": "Abrir Epi MediaHub al iniciar y después del standby", "playlist_help": "Ayuda y guías de listas",
        "check_updates": "Buscar actualizaciones (v{version})", "configured": "configurado", "not_configured": "no configurado", "set": "establecido", "not_set": "no establecido", "automatic": "Automático por IP de internet",
        "category_info": "Seleccionar categoría   |   MENU = gestionar categorías   |   {count} visibles", "search_area": "Buscar en toda la sección", "search_results": "Resultados: {query}",
        "added_favorite": "Añadido a favoritos", "removed_favorite": "Eliminado de favoritos", "help_title": "AYUDA Y GUÍAS", "help_subtitle": "Configura listas por URL, FTP/SFTP o SSH",
        "help_info": "ARRIBA/ABAJO = elegir tema   |   VERDE = escanear FTP/SFTP   |   EXIT = Atrás", "profile_title": "LISTAS", "profile_subtitle": "Gestiona URL, SSH y FTP/SFTP juntos",
        "delete": "Eliminar", "add_url": "Añadir URL", "edit": "Editar",
    },
}


# Extra strings used by detail/EPG/status screens. Keeping these separate
# makes the core table above easier to read and extend.
_TRANSLATIONS["de"].update({
    "no_rating": "Noch keine Bewertung", "ratings": "Bewertungen", "minutes": "Min.", "info_loading": "Infos werden geladen …",
    "no_description": "Keine Beschreibung vom Anbieter verfügbar.", "data_source": "Datenquelle", "details_loading": "Details werden im Hintergrund ergänzt …",
    "epg_provider_loading": "EPG wird direkt vom Anbieter geladen …", "epg_background": "FAST API: Sender-EPG wird im Hintergrund abgerufen",
    "epg_provider_unavailable": "EPG vom Anbieter nicht verfügbar: {error}", "epg_no_current": "Für diesen Sender läuft aktuell kein EPG-Ereignis.",
    "epg_none_found": "Keine EPG-Daten für diesen Sender gefunden.", "epg_source": "EPG direkt über FAST API / lokalen XMLTV-Cache",
    "epg_none_available": "Keine Sender-EPG-Daten verfügbar. XMLTV wird automatisch im Hintergrund aktualisiert.",
    "provider_info_error": "Anbieter-Infos konnten nicht ergänzt werden: {error}",
})
_TRANSLATIONS["en"].update({
    "no_rating": "No rating yet", "ratings": "ratings", "minutes": "min", "info_loading": "Loading information …",
    "no_description": "No description available from the provider.", "data_source": "Data source", "details_loading": "Adding details in the background …",
    "epg_provider_loading": "Loading EPG directly from the provider …", "epg_background": "FAST API: channel EPG is loading in the background",
    "epg_provider_unavailable": "Provider EPG unavailable: {error}", "epg_no_current": "There is currently no EPG event for this channel.",
    "epg_none_found": "No EPG data found for this channel.", "epg_source": "EPG via FAST API / local XMLTV cache",
    "epg_none_available": "No channel EPG data available. XMLTV updates automatically in the background.",
    "provider_info_error": "Provider information could not be added: {error}",
})
_TRANSLATIONS["tr"].update({
    "no_rating": "Henüz puan yok", "ratings": "oy", "minutes": "dk", "info_loading": "Bilgiler yükleniyor …",
    "no_description": "Sağlayıcıdan açıklama yok.", "data_source": "Veri kaynağı", "details_loading": "Ayrıntılar arka planda ekleniyor …",
    "epg_provider_loading": "EPG sağlayıcıdan yükleniyor …", "epg_background": "FAST API: kanal EPG'si arka planda yükleniyor",
    "epg_provider_unavailable": "Sağlayıcı EPG'si kullanılamıyor: {error}", "epg_no_current": "Bu kanalda şu anda EPG etkinliği yok.",
    "epg_none_found": "Bu kanal için EPG verisi bulunamadı.", "epg_source": "FAST API / yerel XMLTV önbelleği üzerinden EPG",
    "epg_none_available": "Kanal EPG verisi yok. XMLTV arka planda otomatik güncellenir.",
    "provider_info_error": "Sağlayıcı bilgileri eklenemedi: {error}",
})
_TRANSLATIONS["it"].update({
    "no_rating": "Nessuna valutazione", "ratings": "valutazioni", "minutes": "min", "info_loading": "Caricamento informazioni …",
    "no_description": "Nessuna descrizione disponibile dal provider.", "data_source": "Fonte dati", "details_loading": "Dettagli aggiunti in background …",
    "epg_provider_loading": "Caricamento EPG dal provider …", "epg_background": "FAST API: EPG del canale in caricamento in background",
    "epg_provider_unavailable": "EPG del provider non disponibile: {error}", "epg_no_current": "Nessun evento EPG attivo per questo canale.",
    "epg_none_found": "Nessun dato EPG trovato per questo canale.", "epg_source": "EPG via FAST API / cache XMLTV locale",
    "epg_none_available": "Nessun dato EPG disponibile. XMLTV si aggiorna automaticamente in background.",
    "provider_info_error": "Impossibile aggiungere le informazioni del provider: {error}",
})
_TRANSLATIONS["es"].update({
    "no_rating": "Sin valoración", "ratings": "valoraciones", "minutes": "min", "info_loading": "Cargando información …",
    "no_description": "No hay descripción disponible del proveedor.", "data_source": "Fuente de datos", "details_loading": "Añadiendo detalles en segundo plano …",
    "epg_provider_loading": "Cargando EPG directamente del proveedor …", "epg_background": "FAST API: EPG del canal cargándose en segundo plano",
    "epg_provider_unavailable": "EPG del proveedor no disponible: {error}", "epg_no_current": "No hay un evento EPG activo para este canal.",
    "epg_none_found": "No se encontraron datos EPG para este canal.", "epg_source": "EPG mediante FAST API / caché XMLTV local",
    "epg_none_available": "No hay datos EPG del canal. XMLTV se actualiza automáticamente en segundo plano.",
    "provider_info_error": "No se pudo añadir la información del proveedor: {error}",
})

_TRANSLATIONS["de"].update({
    "pin_default": "PIN eingeben", "pin_help": "0-9 eingeben   |   LINKS = löschen   |   OK = bestätigen   |   EXIT = abbrechen", "pin_four": "Bitte eine vierstellige PIN eingeben.",
    "no_categories_kind": "Keine Kategorien für {kind} vorhanden.", "playlist_preparing": "Die Playlist wird gerade im Hintergrund vorbereitet.\nBitte einen Moment warten.",
    "playlist_no_data": "Für diese Playlist wurden noch keine Daten geladen.\nÖffne Einstellungen und wähle GRÜN = Playlist laden.", "no_kind_entries": "Keine Einträge für {kind} erkannt.",
    "no_playlist_loaded": "Noch keine Playlist geladen.", "search_index_error": "Suche konnte den Serverindex nicht laden:\n{error}",
    "loading_busy": "Es wird bereits eine Kategorie geladen …", "loading_category": "{name} wird im Hintergrund geladen …", "loading_all": "Alle {kind} werden im Hintergrund geladen …",
    "loading_search": "Suchindex für {kind} wird im Hintergrund geladen …", "content_load_error": "Inhalte konnten nicht geladen werden:\n{error}",
    "no_favorites": "Noch keine sichtbaren Favoriten in {kind}.", "favorites_kind": "Favoriten - {kind}",
})
_TRANSLATIONS["en"].update({
    "pin_default": "Enter PIN", "pin_help": "Enter 0-9   |   LEFT = delete   |   OK = confirm   |   EXIT = cancel", "pin_four": "Please enter a four-digit PIN.",
    "no_categories_kind": "No categories available for {kind}.", "playlist_preparing": "The playlist is being prepared in the background.\nPlease wait a moment.",
    "playlist_no_data": "No data has been loaded for this playlist yet.\nOpen Settings and choose GREEN = Load playlist.", "no_kind_entries": "No entries detected for {kind}.",
    "no_playlist_loaded": "No playlist loaded yet.", "search_index_error": "Search could not load the server index:\n{error}",
    "loading_busy": "A category is already loading …", "loading_category": "{name} is loading in the background …", "loading_all": "All {kind} are loading in the background …",
    "loading_search": "Search index for {kind} is loading in the background …", "content_load_error": "Content could not be loaded:\n{error}",
    "no_favorites": "No visible favorites in {kind} yet.", "favorites_kind": "Favorites - {kind}",
})
_TRANSLATIONS["tr"].update({
    "pin_default": "PIN girin", "pin_help": "0-9 gir   |   SOL = sil   |   OK = onayla   |   EXIT = iptal", "pin_four": "Lütfen dört haneli PIN girin.",
    "no_categories_kind": "{kind} için kategori yok.", "playlist_preparing": "Oynatma listesi arka planda hazırlanıyor.\nLütfen biraz bekleyin.",
    "playlist_no_data": "Bu liste için henüz veri yüklenmedi.\nAyarlar'da YEŞİL = Listeyi yükle seçin.", "no_kind_entries": "{kind} için öğe bulunamadı.",
    "no_playlist_loaded": "Henüz oynatma listesi yüklenmedi.", "search_index_error": "Arama sunucu dizinini yükleyemedi:\n{error}",
    "loading_busy": "Bir kategori zaten yükleniyor …", "loading_category": "{name} arka planda yükleniyor …", "loading_all": "Tüm {kind} arka planda yükleniyor …",
    "loading_search": "{kind} arama dizini arka planda yükleniyor …", "content_load_error": "İçerik yüklenemedi:\n{error}",
    "no_favorites": "{kind} içinde görünür favori yok.", "favorites_kind": "Favoriler - {kind}",
})
_TRANSLATIONS["it"].update({
    "pin_default": "Inserisci PIN", "pin_help": "Inserisci 0-9   |   SINISTRA = cancella   |   OK = conferma   |   EXIT = annulla", "pin_four": "Inserisci un PIN di quattro cifre.",
    "no_categories_kind": "Nessuna categoria disponibile per {kind}.", "playlist_preparing": "La playlist viene preparata in background.\nAttendi un momento.",
    "playlist_no_data": "Nessun dato caricato per questa playlist.\nApri Impostazioni e scegli VERDE = Carica playlist.", "no_kind_entries": "Nessun elemento rilevato per {kind}.",
    "no_playlist_loaded": "Nessuna playlist caricata.", "search_index_error": "Impossibile caricare l'indice del server:\n{error}",
    "loading_busy": "Una categoria è già in caricamento …", "loading_category": "{name} viene caricata in background …", "loading_all": "Tutti i contenuti {kind} vengono caricati in background …",
    "loading_search": "Indice di ricerca per {kind} in caricamento …", "content_load_error": "Impossibile caricare i contenuti:\n{error}",
    "no_favorites": "Nessun preferito visibile in {kind}.", "favorites_kind": "Preferiti - {kind}",
})
_TRANSLATIONS["es"].update({
    "pin_default": "Introducir PIN", "pin_help": "0-9 = introducir   |   IZQUIERDA = borrar   |   OK = confirmar   |   EXIT = cancelar", "pin_four": "Introduzca un PIN de cuatro dígitos.",
    "no_categories_kind": "No hay categorías para {kind}.", "playlist_preparing": "La lista se está preparando en segundo plano.\nEspere un momento.",
    "playlist_no_data": "Todavía no hay datos para esta lista.\nAbra Ajustes y elija VERDE = Cargar lista.", "no_kind_entries": "No se detectaron elementos para {kind}.",
    "no_playlist_loaded": "Todavía no hay una lista cargada.", "search_index_error": "La búsqueda no pudo cargar el índice del servidor:\n{error}",
    "loading_busy": "Ya se está cargando una categoría …", "loading_category": "{name} se carga en segundo plano …", "loading_all": "Todo {kind} se carga en segundo plano …",
    "loading_search": "El índice de búsqueda de {kind} se carga en segundo plano …", "content_load_error": "No se pudo cargar el contenido:\n{error}",
    "no_favorites": "No hay favoritos visibles en {kind}.", "favorites_kind": "Favoritos - {kind}",
})



# Theme labels added in v0.9.0. Kept here so older translation dictionaries stay
# readable and the feature can be extended independently.
_TRANSLATIONS["de"].update({
    "skin": "Skin / Design", "skin_category": "Skin-Kategorie", "skin_select": "Skin auswählen",
    "skin_saved": "Skin gespeichert. Schließe Epi MediaHub einmal komplett und öffne die App erneut, damit die Startseite den neuen Hintergrund lädt.",
})
_TRANSLATIONS["en"].update({
    "skin": "Skin / design", "skin_category": "Skin category", "skin_select": "Select skin",
    "skin_saved": "Skin saved. Close Epi MediaHub completely once and reopen it so the home screen loads the new background.",
})
_TRANSLATIONS["tr"].update({
    "skin": "Tema / tasarım", "skin_category": "Tema kategorisi", "skin_select": "Tema seç",
    "skin_saved": "Tema kaydedildi. Ana ekranın yeni arka planı yüklemesi için Epi MediaHub'ı tamamen kapatıp yeniden açın.",
})
_TRANSLATIONS["it"].update({
    "skin": "Skin / design", "skin_category": "Categoria skin", "skin_select": "Seleziona skin",
    "skin_saved": "Skin salvata. Chiudi completamente Epi MediaHub e riaprilo per caricare il nuovo sfondo nella schermata principale.",
})
_TRANSLATIONS["es"].update({
    "skin": "Skin / diseño", "skin_category": "Categoría de skin", "skin_select": "Elegir skin",
    "skin_saved": "Skin guardado. Cierra Epi MediaHub por completo y vuelve a abrirlo para que la pantalla principal cargue el nuevo fondo.",
})


def tr(key, **kwargs):
    lang = current_app_language()
    table = _TRANSLATIONS.get(lang, _TRANSLATIONS["de"])
    text = table.get(key, _TRANSLATIONS["de"].get(key, key))
    try:
        return text.format(**kwargs)
    except Exception:
        return text


# Release notes are embedded per version so the app can show a one-time
# "What's new" window after an update, even when the receiver is offline.
_RELEASE_NOTES = {
    "0.9.41": {
        "de": ["Start-Crash bei leerer Playlist-Verwaltung behoben: Das automatische QR/Web-Setup öffnet erst, wenn der Playlist-Screen vollständig modal aktiv ist.", "OpenATV-7.6-Schutz: current_dialog/in_exec werden geprüft; falls nötig wird das Öffnen per Enigma2-Timer verschoben.", "Audio-Fix, Mediathek, EPG/Replay, QR-Web-Setup und Family-Funktionen bleiben erhalten."],
        "en": ["Fixed startup crash with no playlists: automatic QR/web setup now opens only after the playlist screen is fully active and modal.", "OpenATV 7.6 guard checks current_dialog/in_exec and defers opening via Enigma2 timer when required.", "Audio fix, Mediathek, EPG/replay, QR web setup and Family features are preserved."],
    },
    "0.9.40": {
        "de": ["Updater-Speicherfix: keine doppelte Vollsicherung von EPG-, Picon- und Metadaten-Caches mehr nach /tmp; das verhindert opkg-Abbrüche auf Boxen mit knappem temporärem Speicher.", "Der Updater protokolliert künftig die echte opkg-Ausgabe unter /tmp/epimediahub_update.log und zeigt bei Fehlern die letzten Meldungen direkt an.", "Audio-Kompatibilitätsfix aus v0.9.39 sowie Mediathek, EPG/Replay, QR-Web-Setup und Family-Funktionen bleiben erhalten."],
        "en": ["Updater memory fix: no more duplicate full backups of EPG, picon and metadata caches to /tmp, preventing opkg failures on receivers with limited temporary storage.", "The updater now logs real opkg output to /tmp/epimediahub_update.log and shows the last error lines directly.", "The v0.9.39 audio compatibility fix plus Mediathek, EPG/replay, QR web setup and Family features are preserved."],
        "tr": ["Güncelleyici bellek düzeltmesi: EPG, picon ve meta veri önbellekleri artık /tmp içine iki kez tam olarak yedeklenmiyor; sınırlı geçici bellekte opkg hataları önleniyor.", "Güncelleyici gerçek opkg çıktısını /tmp/epimediahub_update.log dosyasına kaydeder ve son hata satırlarını gösterir.", "v0.9.39 ses düzeltmesi ile Mediathek, EPG/tekrar, QR web kurulumu ve Family özellikleri korunur."],
        "it": ["Correzione memoria updater: niente più doppio backup completo delle cache EPG, picon e metadati in /tmp, evitando errori opkg sui ricevitori con memoria temporanea limitata.", "L'updater salva ora l'output reale di opkg in /tmp/epimediahub_update.log e mostra direttamente le ultime righe di errore.", "Restano invariati il fix audio v0.9.39, Mediathek, EPG/replay, setup web QR e funzioni Family."],
        "es": ["Corrección de memoria del actualizador: ya no se duplican copias completas de cachés EPG, picon y metadatos en /tmp, evitando fallos de opkg con poco espacio temporal.", "El actualizador guarda la salida real de opkg en /tmp/epimediahub_update.log y muestra las últimas líneas de error.", "Se conservan el arreglo de audio v0.9.39, Mediathek, EPG/replay, configuración web QR y funciones Family."],
    },
    "0.9.39": {
        "de": ["Audio-Kompatibilitätsfix für OpenATV 7.6: Live-TV, Filme/Serien, Replay und Mediathek nutzen für Remote-Streams jetzt den nativen Enigma2/GStreamer-Pfad (Service-Typ 1) statt des ersetzbaren 4097-Playerpfads.", "Intro-Audio, Aufnahmen/Timer, Mediathek-Navigation, EPG/Catchup, Family-PIN und alle Einstellungen aus v0.9.38 bleiben unverändert."],
        "en": ["OpenATV 7.6 audio compatibility fix: Live TV, movies/series, replay and Mediathek remote streams now use the native Enigma2/GStreamer path (service type 1) instead of the replaceable 4097 player path.", "Intro audio, recording/timers, Mediathek navigation, EPG/catchup, Family PIN and all v0.9.38 settings remain unchanged."],
        "tr": ["OpenATV 7.6 ses uyumluluk düzeltmesi: Canlı TV, film/dizi, tekrar ve Mediathek uzak akışları artık değiştirilebilir 4097 oynatıcı yolu yerine yerel Enigma2/GStreamer yolunu (servis tipi 1) kullanıyor.", "Giriş sesi, kayıt/zamanlayıcı, Mediathek gezinmesi, EPG/Catchup, Family PIN ve v0.9.38 ayarları değişmedi."],
        "it": ["Correzione compatibilità audio OpenATV 7.6: TV live, film/serie, replay e flussi remoti Mediathek usano ora il percorso nativo Enigma2/GStreamer (tipo servizio 1) invece del percorso 4097 sostituibile.", "Audio intro, registrazioni/timer, navigazione Mediathek, EPG/Catchup, Family PIN e impostazioni v0.9.38 restano invariati."],
        "es": ["Corrección de compatibilidad de audio para OpenATV 7.6: TV en directo, películas/series, replay y flujos remotos de Mediathek usan ahora la ruta nativa Enigma2/GStreamer (tipo de servicio 1) en lugar de la ruta 4097 reemplazable.", "Audio de introducción, grabaciones/temporizadores, navegación Mediathek, EPG/Catchup, Family PIN y ajustes de v0.9.38 permanecen sin cambios."],
    },
    "0.9.38": {
        "de": ["Mediathek-Anbieteransicht: Picons und Anbieternamen haben jetzt getrennte Spalten und überdecken sich nicht mehr."],
        "en": ["Mediathek provider view: icons and provider names now use separate columns and no longer overlap."],
        "tr": ["Mediathek sağlayıcı görünümünde simgeler ve sağlayıcı adları artık ayrı sütunlarda ve üst üste gelmiyor."],
        "it": ["Vista provider Mediathek: icone e nomi ora usano colonne separate e non si sovrappongono più."],
        "es": ["Vista de proveedores Mediathek: los iconos y los nombres ahora usan columnas separadas y ya no se superponen."],
    },
    "0.9.37": {
        "de": [
            "Xtream Catch-up/Replay: Archivsender und verfügbare vergangene Sendungen lassen sich direkt aus dem EPG starten.",
            "Neue Mehrsender-EPG-Rasteransicht mit Live/Replay, Aufnahme-Timer und Erinnerungs-/Zap-Timer über Enigma2.",
        ],
        "en": [
            "Xtream catch-up/replay for provider archive channels directly from the EPG.",
            "New multi-channel EPG grid with live/replay playback plus native Enigma2 recording and reminder timers.",
        ],
        "tr": [
            "Xtream arşiv kanalları için EPG üzerinden Catch-up/Replay desteği.",
            "Canlı/Replay, kayıt ve hatırlatma zamanlayıcılı yeni çok kanallı EPG görünümü.",
        ],
        "it": [
            "Catch-up/Replay Xtream per i canali archivio direttamente dalla guida EPG.",
            "Nuova griglia EPG multicanale con Live/Replay, registrazioni e promemoria Enigma2.",
        ],
        "es": [
            "Catch-up/Replay Xtream para canales con archivo directamente desde la EPG.",
            "Nueva parrilla EPG multicanal con Live/Replay, grabaciones y recordatorios Enigma2.",
        ],
    },
    "0.9.20": {
        "de": ["Sicherheitsfix für Updates: Playlists, Profile und Einstellungen werden vor Paketwechseln gesichert und danach wiederhergestellt.", "Der Playlist-Ordner gehört nicht mehr zum IPK-Paket und kann von opkg bei Updates nicht mehr als Paketinhalt entfernt werden."],
        "en": ["Update safety fix: playlists, profiles and settings are backed up before package replacement and restored afterwards.", "The playlist directory is no longer package-owned, preventing opkg from removing it as package content during updates."],
        "tr": ["Güncelleme güvenlik düzeltmesi: oynatma listeleri, profiller ve ayarlar paket değişiminden önce yedeklenir ve sonra geri yüklenir.", "Oynatma listesi klasörü artık IPK paketine ait değildir."],
        "it": ["Correzione sicurezza aggiornamenti: playlist, profili e impostazioni vengono salvati prima della sostituzione del pacchetto e ripristinati dopo.", "La cartella playlist non appartiene più al pacchetto IPK."],
        "es": ["Corrección de seguridad de actualizaciones: listas, perfiles y ajustes se respaldan antes del cambio de paquete y se restauran después.", "La carpeta de listas ya no pertenece al paquete IPK."]
    },
    "0.9.19": {
        "de": ["Senderbanner besser lesbar: Das Skin-Logo ist deutlich transparenter, kleiner und weiter rechts platziert.", "Intro neu synchronisiert: 10 Animationsframes und eine neue markantere Epi-Signaturmelodie laufen jetzt auf derselben 3,2-Sekunden-Zeitleiste."],
        "en": ["Improved Live-TV banner readability: the skin logo is much more transparent, smaller and moved farther right.", "Intro resynced: all 10 animation frames and a new, more memorable Epi signature melody now share the same 3.2-second timeline."],
        "tr": ["Canlı TV bandı daha okunaklı: tema logosu daha şeffaf, daha küçük ve daha sağda.", "Giriş yeniden senkronize edildi: 10 animasyon karesi ve yeni, daha akılda kalıcı Epi melodisi aynı 3,2 saniyelik zaman çizgisinde ilerliyor."],
        "it": ["Banner Live-TV più leggibile: il logo del tema è molto più trasparente, più piccolo e spostato a destra.", "Intro risincronizzata: i 10 fotogrammi e la nuova melodia Epi più riconoscibile condividono ora la stessa timeline di 3,2 secondi."],
        "es": ["Banner de TV en directo más legible: el logo del tema es mucho más transparente, pequeño y está más a la derecha.", "Intro resincronizada: los 10 fotogramas y una nueva melodía Epi más reconocible comparten ahora la misma línea temporal de 3,2 segundos."]
    },
    "0.9.18": {
        "de": ["Exit-Dialog repariert: Ja/Nein lässt sich jetzt zuverlässig mit Pfeiltasten auswählen.", "Nein ist standardmäßig markiert; Grün bestätigt Ja, Rot/EXIT bricht ab und OK führt nur die markierte Auswahl aus."],
        "en": ["Fixed the exit dialog: Yes/No can now be selected reliably with the arrow keys.", "No is selected by default; Green confirms Yes, Red/EXIT cancels, and OK only executes the highlighted choice."],
        "tr": ["Çıkış penceresi düzeltildi: Evet/Hayır artık yön tuşlarıyla güvenilir biçimde seçilebilir.", "Varsayılan seçim Hayır; Yeşil Evet'i onaylar, Kırmızı/EXIT iptal eder ve OK yalnızca seçili seçeneği uygular."],
        "it": ["Corretto il dialogo di uscita: Sì/No ora si selezionano correttamente con i tasti freccia.", "No è selezionato di default; Verde conferma Sì, Rosso/EXIT annulla e OK esegue solo la scelta evidenziata."],
        "es": ["Corregido el diálogo de salida: Sí/No ahora se selecciona correctamente con las flechas.", "No queda seleccionado por defecto; Verde confirma Sí, Rojo/EXIT cancela y OK ejecuta solo la opción marcada."]
    },
    "0.9.17": {
        "de": ["Premium-Skin-Overhaul: Ein großes Motiv läuft fortlaufend durch alle sechs Startkacheln, jetzt platzsparend umgesetzt.", "Zapping-Banner und Exit-Bestätigung übernehmen den aktiven Skin direkt aus den vorhandenen Theme-Logos."],
        "en": ["Premium skin overhaul: one large motif continues through all six home tiles, now implemented with compact assets.", "The zapping banner and exit confirmation inherit the active skin directly from the existing theme logos."],
        "tr": ["Premium tema yenilemesi: tek büyük motif altı ana kutucukta kesintisiz devam eder ve artık kompakt biçimde uygulanır.", "Kanal bandı ve çıkış onayı aktif temayı mevcut tema logolarından doğrudan kullanır."],
        "it": ["Restyling premium: un unico grande motivo continua attraverso tutte e sei le tessere Home, ora con risorse compatte.", "Banner zapping e conferma uscita usano direttamente il logo della skin attiva."],
        "es": ["Rediseño premium: un gran motivo continúa por las seis baldosas de Inicio con recursos compactos.", "El banner de zapping y la confirmación de salida usan directamente el logotipo del skin activo."]
    },
    "0.9.15": {
        "de": ["Schnelles Scrollen durch Kategorien optimiert: Kategorie-Icons werden verzögert und nur bei Bedarf neu gezeichnet, damit OpenATV flüssig bleibt.", "LIVE-TV hat jetzt die Kategorie Zuletzt angesehen; erfolgreich gestartete Sender werden automatisch gespeichert, auch beim Zappen."],
        "en": ["Optimized fast category scrolling: category icons are deferred and only redrawn when needed to keep OpenATV responsive.", "Live TV now has a Recently watched category; successfully tuned channels are stored automatically, including while zapping."],
        "tr": ["Hızlı kategori kaydırma optimize edildi; OpenATV akıcı kalması için kategori simgeleri gecikmeli ve yalnızca gerektiğinde yenilenir.", "Canlı TV artık Son izlenenler kategorisine sahip; başarılı açılan kanallar kanal değiştirirken de otomatik kaydedilir."],
        "it": ["Ottimizzato lo scorrimento rapido delle categorie: le icone vengono aggiornate con ritardo e solo quando serve per mantenere OpenATV fluido.", "La TV Live ora ha la categoria Visti di recente; i canali avviati correttamente vengono salvati anche durante lo zapping."],
        "es": ["Optimizado el desplazamiento rápido por categorías: los iconos se actualizan con retardo y solo cuando es necesario para mantener OpenATV fluido.", "Live TV ahora incluye Vistos recientemente; los canales sintonizados correctamente se guardan también al hacer zapping."]
    },
    "0.9.14": {
        "de": ["Playlist-Onlineprüfung deutlich beschleunigt: schneller Server-Check statt langem Xtream-/M3U-Doppeltest.", "Grüne und rote Statussymbole sind größer und deutlich sichtbar; jede Playlist aktualisiert ihren Status sofort, sobald das Ergebnis vorliegt."],
        "en": ["Playlist online checks are much faster using a lightweight server reachability test instead of a long Xtream/M3U double check.", "Green and red indicators are larger and clearer; each playlist updates as soon as its own result arrives."],
        "tr": ["Oynatma listesi çevrimiçi kontrolü uzun Xtream/M3U çift testi yerine hızlı sunucu erişim kontrolü kullanır.", "Yeşil ve kırmızı durum simgeleri daha büyük ve nettir; her liste sonucu gelir gelmez güncellenir."],
        "it": ["Il controllo online delle playlist è molto più rapido grazie a un test leggero di raggiungibilità del server.", "Gli indicatori verdi e rossi sono più grandi e chiari; ogni playlist si aggiorna appena arriva il proprio risultato."],
        "es": ["La comprobación online de las listas es mucho más rápida mediante una prueba ligera de conexión al servidor.", "Los indicadores verde y rojo son más grandes y claros; cada lista se actualiza en cuanto llega su resultado."]
    },
    "0.9.13": {
        "de": ["Playlist-Auswahl zeigt jetzt pro Liste einen Live-Status mit grünem oder rotem Symbol.", "Grün = Online; Rot = Server nicht erreichbar. Die Prüfung läuft im Hintergrund und blockiert die Bedienung nicht."],
        "en": ["The playlist selector now shows a live status for every playlist with a green or red indicator.", "Green = Online; Red = Server unreachable. Checks run in the background without blocking navigation."],
        "tr": ["Oynatma listesi seçimi artık her liste için yeşil veya kırmızı canlı durum göstergesi gösterir.", "Yeşil = Çevrimiçi; Kırmızı = Sunucuya ulaşılamıyor. Kontrol arka planda çalışır."],
        "it": ["La selezione playlist mostra ora lo stato live di ogni lista con un indicatore verde o rosso.", "Verde = Online; Rosso = Server non raggiungibile. Il controllo avviene in background."],
        "es": ["El selector de listas ahora muestra el estado en vivo de cada lista con un indicador verde o rojo.", "Verde = Online; Rojo = Servidor no accesible. La comprobación se realiza en segundo plano."]
    },
    "0.9.12": {
        "de": ["Skin-Logos auf der Startseite jetzt deutlich größer und zentral dargestellt; die Kacheltexte bleiben frei.", "Bei mehreren Xtream-Playlists werden Ablaufdaten im Playlist-Auswahlfenster automatisch im Hintergrund abgefragt und gespeichert."],
        "en": ["Skin logos are now larger and centered on the home screen while tile labels stay clear.", "With multiple Xtream playlists, expiry dates are fetched and stored automatically in the background in the playlist selector."],
        "tr": ["Tema logoları ana ekranda artık daha büyük ve ortalanmış; kutu yazıları açık kalır.", "Birden fazla Xtream listesinde bitiş tarihleri liste seçim ekranında arka planda otomatik alınır ve kaydedilir."],
        "it": ["I loghi delle skin sono ora più grandi e centrati nella Home senza coprire i testi delle tessere.", "Con più playlist Xtream, le scadenze vengono recuperate e salvate automaticamente in background nella selezione playlist."],
        "es": ["Los logotipos de las skins ahora son más grandes y están centrados en Inicio sin tapar los textos.", "Con varias listas Xtream, las fechas de caducidad se consultan y guardan automáticamente en segundo plano en el selector de listas."]
    },
    "0.9.11": {
        "de": ["Bildkompatibilität für unterschiedliche OpenATV-Receiver verbessert.", "JPEG/PNG bevorzugt; WebP/AVIF, TLS und Download-Fallbacks robuster behandelt."],
        "en": ["Improved image compatibility across OpenATV receivers.", "JPEG/PNG preferred with more robust WebP/AVIF, TLS and download fallbacks."],
        "tr": ["Farklı OpenATV alıcılarında görüntü uyumluluğu geliştirildi.", "JPEG/PNG tercih edilir; WebP/AVIF, TLS ve indirme yedekleri daha sağlamdır."],
        "it": ["Compatibilità immagini migliorata tra diversi ricevitori OpenATV.", "Preferenza JPEG/PNG con fallback WebP/AVIF, TLS e download più robusti."],
        "es": ["Mejorada la compatibilidad de imágenes entre receptores OpenATV.", "Se prioriza JPEG/PNG con alternativas WebP/AVIF, TLS y descarga más robustas."]
    },
    "0.9.10": {
        "de": ["Family-Logos auf den Startkacheln kleiner und weiter außen platziert, damit Beschriftungen frei bleiben.", "Autostart erweitert: Bei aktiviertem Autostart öffnet Epi MediaHub nun auch nach dem Aufwachen aus dem normalen Standby automatisch wieder."],
        "en": ["Family logos on home tiles are smaller and moved outward so labels stay clear.", "Autostart now also reopens Epi MediaHub after waking from normal standby when enabled."],
        "tr": ["Ana ekran Family logoları küçültüldü ve yazıları kapatmaması için dışa taşındı.", "Otomatik başlatma açıksa Epi MediaHub normal beklemeden uyanınca da yeniden açılır."],
        "it": ["I loghi Family nelle tessere Home sono più piccoli e spostati verso l'esterno per non coprire le scritte.", "Con l'avvio automatico attivo, Epi MediaHub si riapre anche dopo il risveglio dallo standby normale."],
        "es": ["Los logotipos Family de las tarjetas de inicio son más pequeños y están desplazados hacia fuera para no tapar el texto.", "Con el inicio automático activado, Epi MediaHub también se vuelve a abrir al salir del modo de espera normal."]
    },
    "0.9.9": {
        "de": ["Interne Design-Ressourcen aktualisiert.", "Bestehendes Enigma2-Layout und Bedienung bleiben unverändert."],
        "en": ["Updated internal design resources.", "Existing Enigma2 layout and controls remain unchanged."],
        "tr": ["Dahili tasarım kaynakları güncellendi.", "Mevcut Enigma2 düzeni ve kontrolleri değişmedi."],
        "it": ["Risorse grafiche interne aggiornate.", "Layout e controlli Enigma2 esistenti restano invariati."],
        "es": ["Recursos de diseño internos actualizados.", "El diseño y los controles de Enigma2 permanecen sin cambios."]
    },
    "0.9.8": {
        "de": [
            "Interne Skin-Verwaltung erweitert; das bestehende Enigma2-Layout und die Bedienung bleiben unverändert.",
            "Zusätzliche Design-Ressourcen und kleinere Stabilitätsverbesserungen integriert.",
        ],
        "en": [
            "Extended the internal skin handling while keeping the existing Enigma2 layout and controls unchanged.",
            "Added extra design resources and minor stability improvements.",
        ],
        "tr": [
            "Dahili tema yönetimi genişletildi; mevcut Enigma2 düzeni ve kullanımı değişmeden kaldı.",
            "Ek tasarım kaynakları ve küçük kararlılık iyileştirmeleri eklendi.",
        ],
        "it": [
            "Gestione interna delle skin ampliata mantenendo invariati layout e comandi Enigma2 esistenti.",
            "Aggiunte risorse grafiche extra e piccoli miglioramenti di stabilità.",
        ],
        "es": [
            "Se amplió la gestión interna de skins manteniendo sin cambios el diseño y los controles de Enigma2.",
            "Se añadieron recursos de diseño adicionales y pequeñas mejoras de estabilidad.",
        ],
    },
    "0.9.7": {
        "de": [
            "Aktiver Skin jetzt auch in Kategorien-, Sender-, Film-, Serien- und Suchlisten mit eigenem EpiMediaHub-Glass-Overlay.",
            "Die letzten halbtransparenten MenuList-Flächen wurden entfernt, damit OpenATV-Grafiken auch in Listen nicht mehr durchscheinen.",
            "1. FC Köln Theme originalnäher überarbeitet: rot-weißer Rundschild-Look mit deutlich erkennbarer stilisierter Geißbock-Silhouette.",
            "14 neue Themes: Volkswagen, Maserati, Bentley, Bugatti, Aston Martin, FC Porto, Benfica, Sporting, Celtic, Rangers sowie vier bewusst stilisierte Luxury/Fashion-Designs.",
            "Theme-Sammlung wächst auf 59 Designs; alle neuen Markenmotive sind Fan-/Inspired-Interpretationen und keine 1:1-Logo-Kopien.",
        ],
        "en": [
            "The active theme now carries into category, channel, movie, series and search lists using an EpiMediaHub-owned glass overlay.",
            "Removed the remaining translucent MenuList surfaces so receiver/OpenATV artwork can no longer bleed through list screens.",
            "Reworked the 1. FC Köln fan theme with a more recognisable red/white roundel and stylised goat silhouette.",
            "Added 14 themes: Volkswagen, Maserati, Bentley, Bugatti, Aston Martin, FC Porto, Benfica, Sporting, Celtic, Rangers and four deliberately stylised luxury/fashion designs.",
            "The collection now contains 59 themes; new brand motifs are fan/inspired interpretations rather than 1:1 logo copies.",
        ],
        "tr": [
            "Aktif tema artık kategori, kanal, film, dizi ve arama listelerinde de EpiMediaHub cam katmanıyla kullanılıyor.",
            "Kalan yarı saydam MenuList yüzeyleri kaldırıldı; OpenATV görselleri liste ekranlarından artık görünemez.",
            "1. FC Köln fan teması daha tanınabilir kırmızı/beyaz yuvarlak arma ve stilize keçi silüetiyle yenilendi.",
            "Volkswagen, Maserati, Bentley, Bugatti, Aston Martin, FC Porto, Benfica, Sporting, Celtic, Rangers ve dört stilize lüks/moda teması eklendi.",
            "Tema sayısı 59'a çıktı; yeni marka motifleri birebir logo kopyası değil, fan/esinlenilmiş yorumlardır.",
        ],
        "it": [
            "La skin attiva ora appare anche nelle liste categorie, canali, film, serie e ricerca tramite un overlay vetro EpiMediaHub.",
            "Rimosse le ultime superfici MenuList semitrasparenti per impedire allo sfondo OpenATV di trasparire nelle liste.",
            "Tema 1. FC Köln ridisegnato con medaglione rosso/bianco più riconoscibile e caprone stilizzato.",
            "Aggiunti 14 temi: Volkswagen, Maserati, Bentley, Bugatti, Aston Martin, FC Porto, Benfica, Sporting, Celtic, Rangers e quattro temi luxury/fashion stilizzati.",
            "La raccolta arriva a 59 temi; i nuovi motivi sono interpretazioni fan/inspired e non copie 1:1 dei loghi.",
        ],
        "es": [
            "El skin activo ahora también se aplica a las listas de categorías, canales, películas, series y búsqueda mediante un overlay de cristal propio de EpiMediaHub.",
            "Se eliminaron las últimas superficies MenuList semitransparentes para impedir que el fondo de OpenATV se filtre en las listas.",
            "Tema del 1. FC Köln rediseñado con un emblema circular rojo/blanco más reconocible y una cabra estilizada.",
            "Se añadieron 14 temas: Volkswagen, Maserati, Bentley, Bugatti, Aston Martin, FC Porto, Benfica, Sporting, Celtic, Rangers y cuatro diseños luxury/fashion estilizados.",
            "La colección llega a 59 temas; los nuevos motivos son interpretaciones inspiradas y no copias 1:1 de logotipos.",
        ],
    },
    "0.9.6": {
        "de": [
            "OpenATV-Hintergrund kann nicht mehr durch Kacheln oder Einstellungen durchscheinen.",
            "Glass-Effekt wird jetzt über eigene EpiMediaHub-Overlay-PNGs gerendert statt über transparente Widget-Hintergrundfarben.",
            "Kacheln bleiben optisch transparent und zeigen ausschließlich den aktiven EpiMediaHub-Skin darunter.",
            "Settings-Liste nutzt denselben sicheren Glass-Look; 1. FC Köln und alle übrigen 45 Skins bleiben enthalten.",
        ],
        "en": [
            "The OpenATV desktop artwork can no longer bleed through tiles or Settings.",
            "Glass surfaces are now rendered by EpiMediaHub-owned PNG overlays instead of translucent widget background colours.",
            "Home tiles remain visually transparent while showing only the active EpiMediaHub theme underneath.",
            "Settings uses the same safe glass treatment; 1. FC Köln and all 45 themes remain included.",
        ],
        "tr": [
            "OpenATV masaüstü görselinin kutucuklardan veya Ayarlar ekranından görünmesi engellendi.",
            "Cam efekti artık yarı saydam widget renkleri yerine EpiMediaHub'a ait PNG katmanlarıyla oluşturuluyor.",
            "Ana menü kutucukları şeffaf görünümünü korurken yalnızca aktif EpiMediaHub temasını gösteriyor.",
            "Ayarlar ekranı da aynı güvenli cam görünümünü kullanıyor; 1. FC Köln dahil 45 tema korunuyor.",
        ],
        "it": [
            "Lo sfondo desktop di OpenATV non può più trasparire nelle tessere o nelle Impostazioni.",
            "L'effetto vetro usa ora overlay PNG proprietari di EpiMediaHub invece di colori widget semitrasparenti.",
            "Le tessere restano visivamente trasparenti mostrando solo la skin EpiMediaHub attiva.",
            "Anche le Impostazioni usano lo stesso glass sicuro; restano incluse tutte le 45 skin e 1. FC Köln.",
        ],
        "es": [
            "El fondo de OpenATV ya no puede verse a través de las baldosas ni de Ajustes.",
            "El efecto cristal usa ahora overlays PNG propios de EpiMediaHub en lugar de colores de widget semitransparentes.",
            "Las baldosas mantienen el aspecto transparente mostrando únicamente el skin activo de EpiMediaHub.",
            "Ajustes usa el mismo cristal seguro; se mantienen los 45 skins, incluido 1. FC Köln.",
        ],
    },
    "0.9.5": {
        "de": [
            "Alte blau-runde Kachel-Icons vollständig durch neutrale EpiMediaHub-Glyphen ohne OpenATV-Look ersetzt.",
            "Auch Standard-Skin und Settings-Vorschau wurden von kreisförmigen Alt-Elementen bereinigt.",
            "Neuer vollständiger 1. FC Köln Fan-Skin mit Hintergrund, Kachel-Wasserzeichen und Settings-Vorschau.",
            "Deutschland-Kategorie umfasst jetzt sechs Fan-Themes; insgesamt sind 45 Skins enthalten.",
        ],
        "en": [
            "Replaced the old blue circular tile icons with neutral EpiMediaHub glyphs without an OpenATV-like appearance.",
            "Removed circular legacy styling from the standard skin and Settings preview as well.",
            "Added a complete 1. FC Köln fan skin for background, tile watermark and Settings preview.",
            "Germany now contains six fan themes; 45 skins are included in total.",
        ],
        "tr": [
            "Eski mavi yuvarlak kutucuk simgeleri OpenATV görünümü taşımayan nötr EpiMediaHub simgeleriyle değiştirildi.",
            "Standart tema ve Ayarlar önizlemesindeki eski dairesel öğeler de kaldırıldı.",
            "Arka plan, kutucuk filigranı ve Ayarlar önizlemesiyle tam 1. FC Köln taraftar teması eklendi.",
            "Almanya kategorisinde artık altı taraftar teması, toplamda 45 tema bulunuyor.",
        ],
        "it": [
            "Le vecchie icone circolari blu sono state sostituite con glifi EpiMediaHub neutri, senza look OpenATV.",
            "Rimosso lo stile circolare legacy anche dalla skin standard e dall'anteprima Impostazioni.",
            "Aggiunta una skin fan completa 1. FC Köln per sfondo, filigrane nelle tessere e anteprima Impostazioni.",
            "La categoria Germania include ora sei fan theme; in totale sono presenti 45 skin.",
        ],
        "es": [
            "Las antiguas iconos circulares azules se sustituyeron por glifos neutros de EpiMediaHub sin aspecto OpenATV.",
            "También se eliminó el estilo circular heredado del skin estándar y de la vista previa de Ajustes.",
            "Añadido un skin completo de 1. FC Köln para fondo, marca de agua de baldosas y vista previa de Ajustes.",
            "Alemania incluye ahora seis temas de aficionados; hay 45 skins en total.",
        ],
    },
    "0.9.4": {
        "de": [
            "Neue XStreamity-artige Schnellverwaltung über /etc/enigma2/EpiMediaHub/playlists.txt.",
            "Einfach pro Zeile M3U-Plus-URL # Playlistname eintragen; mehrere Zeilen werden automatisch als mehrere Playlists erkannt.",
            "Änderungen der Textdatei werden beim App-Start und beim Playlist-Scan synchronisiert.",
            "Xtream/M3U-Plus wird nach Auswahl automatisch per FAST API vorbereitet; normale M3U-URLs werden im Hintergrund geladen.",
        ],
        "en": [
            "New XStreamity-style quick setup via /etc/enigma2/EpiMediaHub/playlists.txt.",
            "Add one M3U-Plus URL # Playlist name per line; multiple lines become multiple playlists automatically.",
            "The text file is synchronized at app start and during playlist scans.",
            "Xtream/M3U-Plus is prepared automatically through FAST API; generic M3U URLs fall back to background loading.",
        ],
        "tr": [
            "/etc/enigma2/EpiMediaHub/playlists.txt üzerinden XStreamity benzeri hızlı liste yönetimi eklendi.",
            "Her satıra M3U-Plus URL # Liste adı yazın; birden fazla satır otomatik olarak birden fazla liste olur.",
            "Metin dosyasındaki değişiklikler uygulama açılışında ve liste taramasında eşitlenir.",
            "Xtream/M3U-Plus FAST API ile otomatik hazırlanır; normal M3U bağlantıları arka planda yüklenir.",
        ],
        "it": [
            "Nuova gestione rapida in stile XStreamity tramite /etc/enigma2/EpiMediaHub/playlists.txt.",
            "Inserisci una riga M3U-Plus URL # Nome playlist; più righe diventano automaticamente più playlist.",
            "Il file di testo viene sincronizzato all'avvio e durante la scansione playlist.",
            "Xtream/M3U-Plus usa automaticamente FAST API; gli URL M3U generici vengono caricati in background.",
        ],
        "es": [
            "Nueva gestión rápida tipo XStreamity mediante /etc/enigma2/EpiMediaHub/playlists.txt.",
            "Añade una línea M3U-Plus URL # Nombre de lista; varias líneas crean varias listas automáticamente.",
            "El archivo de texto se sincroniza al iniciar la app y al escanear listas.",
            "Xtream/M3U-Plus se prepara automáticamente con FAST API; las URL M3U genéricas se cargan en segundo plano.",
        ],
    },
    "0.9.3": {
        "de": [
            "Skin jetzt direkt in allen sechs Hauptmenü-Kacheln sichtbar: jede Kachel erhält ein dezentes Vereins-/Marken-Wasserzeichen.",
            "Alle 44 Themes besitzen ein eigenes optimiertes Kachel-Wasserzeichen.",
            "Einstellungen komplett in die aktive Skin-Sprache integriert: transparenter Theme-Bereich, Akzentfarbe und sichtbares Emblem.",
            "Settings-Liste transparenter abgestimmt, damit der Skin sichtbar bleibt und die Texte dennoch klar lesbar sind.",
        ],
        "en": [
            "The active skin is now visible inside all six home tiles with a subtle club/brand watermark.",
            "All 44 themes include an optimized tile watermark.",
            "Settings now inherit the active theme with a glass theme strip, accent colour and visible emblem.",
            "The settings list is more transparent while keeping text easy to read.",
        ],
        "tr": [
            "Aktif tema artık altı ana menü kutusunun içinde de ince bir kulüp/marka filigranı olarak görünüyor.",
            "44 temanın tamamı için optimize edilmiş kutucuk filigranı eklendi.",
            "Ayarlar ekranı aktif temayı cam görünümlü tema şeridi, vurgu rengi ve amblemle kullanıyor.",
            "Ayarlar listesi tema görünür kalırken yazılar okunaklı olacak şekilde daha şeffaf hale getirildi.",
        ],
        "it": [
            "La skin attiva ora appare in tutte le sei tessere Home con una filigrana discreta del club/marchio.",
            "Tutti i 44 temi includono una filigrana ottimizzata per le tessere.",
            "Le Impostazioni ereditano il tema attivo con barra glass, colore di accento ed emblema visibile.",
            "La lista impostazioni è più trasparente mantenendo un'ottima leggibilità.",
        ],
        "es": [
            "La skin activa ahora se muestra dentro de las seis baldosas principales con una marca de agua discreta del club/marca.",
            "Los 44 temas incluyen una marca de agua optimizada para las baldosas.",
            "Ajustes hereda el tema activo con una franja glass, color de acento y emblema visible.",
            "La lista de ajustes es más transparente sin perder legibilidad.",
        ],
    },
    "0.9.2": {
        "de": [
            "Hauptmenü-Kacheln überarbeitet: halbtransparenter Glass-Look, damit der gewählte Skin sichtbar durchscheint.",
            "Ausgewählte Kachel bleibt ebenfalls transparent und erhält zusätzlich einen klaren Akzentbalken in der Theme-Farbe.",
            "Textkontrast und Schatten wurden verbessert, damit die Kacheln trotz stärker sichtbarer Hintergründe gut lesbar bleiben.",
            "Alle Vereins- und Automarken-Themes wurden grafisch neu aufgebaut: Embleme orientieren sich deutlicher an den typischen Formen und Farben, bleiben aber eigenständige Fan-Interpretationen.",
        ],
        "en": [
            "Home tiles redesigned with a translucent glass look so the selected theme remains visible underneath.",
            "The selected tile is translucent too and gains a clear theme-coloured focus bar.",
            "Text contrast and shadows were improved for readability over stronger backgrounds.",
            "All club and automotive themes were redrawn with more recognisable shapes and colours while remaining custom fan interpretations.",
        ],
        "tr": [
            "Ana menü kutucukları yarı saydam cam görünümüyle yenilendi; seçili tema arka planda görünür kalıyor.",
            "Seçili kutucuk da yarı saydam ve tema renginde belirgin bir vurgu çubuğuna sahip.",
            "Daha güçlü arka planlarda okunabilirlik için metin kontrastı ve gölgeler iyileştirildi.",
            "Tüm kulüp ve otomobil temaları daha tanınabilir şekil ve renklerle yeniden çizildi; yine özgün taraftar yorumları olarak kaldı.",
        ],
        "it": [
            "Riquadri del menu principale ridisegnati con effetto vetro semitrasparente, così la skin resta visibile sullo sfondo.",
            "Anche il riquadro selezionato resta trasparente e riceve una barra di accento nel colore del tema.",
            "Contrasto e ombre del testo migliorati per mantenere una buona leggibilità.",
            "Tutti i temi di club e auto sono stati ridisegnati con forme e colori più riconoscibili, restando interpretazioni fan originali.",
        ],
        "es": [
            "Las baldosas del menú principal se rediseñaron con un efecto de cristal semitransparente para dejar ver la skin de fondo.",
            "La baldosa seleccionada también permanece transparente y añade una barra de acento del color del tema.",
            "Se mejoraron el contraste y las sombras del texto para mantener una buena legibilidad.",
            "Todos los temas de clubes y coches se redibujaron con formas y colores más reconocibles, manteniéndose como interpretaciones propias para aficionados.",
        ],
    },
    "0.9.1": {
        "de": [
            "Skin-Sichtbarkeit deutlich verbessert: Vereins- und Automarken-Wasserzeichen sind größer, heller und kontrastreicher.",
            "Farben und Hintergrundglow wurden verstärkt, bleiben aber dunkel genug für gute Lesbarkeit der Menüs.",
            "Vereins-/Markenname am unteren Rand ist jetzt klarer sichtbar.",
        ],
        "en": [
            "Skin visibility greatly improved: club and automotive watermarks are larger, brighter and higher contrast.",
            "Theme colours and background glow are stronger while menus remain easy to read.",
            "Club/brand names at the bottom are now much easier to see.",
        ],
        "tr": [
            "Tema görünürlüğü belirgin şekilde artırıldı: kulüp ve otomobil filigranları daha büyük, daha parlak ve daha kontrastlı.",
            "Renkler ve arka plan parlaması güçlendirildi, menü okunabilirliği korundu.",
            "Alt bölümdeki kulüp/marka adı artık daha net görünüyor.",
        ],
        "it": [
            "Visibilità delle skin nettamente migliorata: filigrane di club e auto più grandi, luminose e contrastate.",
            "Colori e bagliore dello sfondo sono più evidenti senza compromettere la leggibilità dei menu.",
            "Il nome del club/marchio in basso è ora molto più visibile.",
        ],
        "es": [
            "Visibilidad de skins claramente mejorada: marcas de agua de clubes y coches más grandes, brillantes y contrastadas.",
            "Los colores y el resplandor del fondo son más intensos sin perder legibilidad en los menús.",
            "El nombre del club/marca en la parte inferior ahora se ve mucho mejor.",
        ],
    },
    "0.9.0": {
        "de": [
            "Neues Skin-System: Designs lassen sich in den Einstellungen nach Kategorien auswählen.",
            "Fan-Themes für Vereine aus England, Italien, Spanien, Deutschland, Frankreich, den Niederlanden und der Türkei.",
            "Türkei-Paket mit Galatasaray, Fenerbahçe, Trabzonspor, Beşiktaş und Başakşehir.",
            "Neue Auto-Themes für Ferrari, Mercedes-Benz, BMW, Audi, Porsche und Lamborghini.",
            "Jedes Theme besitzt einen dezenten Hintergrund und eine passende Akzentfarbe für die Hauptmenü-Auswahl.",
        ],
        "en": [
            "New skin system: choose designs by category in Settings.",
            "Fan themes for clubs from England, Italy, Spain, Germany, France, the Netherlands and Türkiye.",
            "Türkiye pack with Galatasaray, Fenerbahçe, Trabzonspor, Beşiktaş and Başakşehir.",
            "New car themes for Ferrari, Mercedes-Benz, BMW, Audi, Porsche and Lamborghini.",
            "Each theme has a subtle background and matching home-menu accent colour.",
        ],
        "tr": [
            "Yeni tema sistemi: Ayarlar bölümünden kategoriye göre tasarım seçilebilir.",
            "İngiltere, İtalya, İspanya, Almanya, Fransa, Hollanda ve Türkiye kulüpleri için taraftar temaları.",
            "Türkiye paketi: Galatasaray, Fenerbahçe, Trabzonspor, Beşiktaş ve Başakşehir.",
            "Ferrari, Mercedes-Benz, BMW, Audi, Porsche ve Lamborghini için otomobil temaları.",
            "Her tema sade bir arka plan ve ana menü için uyumlu vurgu rengine sahiptir.",
        ],
        "it": [
            "Nuovo sistema skin: i design si scelgono per categoria nelle Impostazioni.",
            "Temi tifosi per club di Inghilterra, Italia, Spagna, Germania, Francia, Paesi Bassi e Turchia.",
            "Pacchetto Turchia con Galatasaray, Fenerbahçe, Trabzonspor, Beşiktaş e Başakşehir.",
            "Nuovi temi auto per Ferrari, Mercedes-Benz, BMW, Audi, Porsche e Lamborghini.",
            "Ogni tema ha uno sfondo discreto e un colore accento coordinato.",
        ],
        "es": [
            "Nuevo sistema de skins: los diseños se eligen por categoría en Ajustes.",
            "Temas de aficionados para clubes de Inglaterra, Italia, España, Alemania, Francia, Países Bajos y Turquía.",
            "Paquete de Turquía con Galatasaray, Fenerbahçe, Trabzonspor, Beşiktaş y Başakşehir.",
            "Nuevos temas de coches para Ferrari, Mercedes-Benz, BMW, Audi, Porsche y Lamborghini.",
            "Cada tema incluye un fondo discreto y un color de acento coordinado.",
        ],
    },
    "0.8.5": {
        "de": [
            "Intro-Sound repariert: Die Audiodatei ist wieder im Paket enthalten und wird über den lokalen Enigma2-Mediaplayer gestartet.",
            "Seriennavigation repariert: Links/Rechts wechselt jetzt zuverlässig zur vorherigen/nächsten Folge; zusätzliche Fernbedienungs-Keymaps werden unterstützt.",
            "Folgenwechsel bleibt innerhalb derselben Serie und Staffel und funktioniert auch aus Zuletzt angesehen besser.",
        ],
        "en": [
            "Intro sound fixed: the audio file is included again and played through Enigma2's local media service.",
            "Series navigation fixed: LEFT/RIGHT now reliably switches to the previous/next episode and supports additional remote key maps.",
            "Episode switching stays within the same series and season and works better from Recently watched.",
        ],
        "tr": [
            "Giriş sesi düzeltildi: ses dosyası tekrar pakete eklendi ve Enigma2 yerel medya servisi üzerinden oynatılıyor.",
            "Dizi gezinmesi düzeltildi: SOL/SAĞ artık önceki/sonraki bölüme güvenilir şekilde geçiyor ve ek kumanda tuş eşlemelerini destekliyor.",
            "Bölüm geçişi aynı dizi ve sezon içinde kalır ve Son izlenenlerden de daha iyi çalışır.",
        ],
        "it": [
            "Audio dell'intro corretto: il file audio è di nuovo incluso e viene riprodotto tramite il servizio multimediale locale di Enigma2.",
            "Navigazione serie corretta: SINISTRA/DESTRA passa ora in modo affidabile all'episodio precedente/successivo e supporta più mappature del telecomando.",
            "Il cambio episodio resta nella stessa serie e stagione e funziona meglio anche da Visti di recente.",
        ],
        "es": [
            "Sonido de la intro corregido: el archivo de audio vuelve a estar incluido y se reproduce mediante el servicio multimedia local de Enigma2.",
            "Navegación de series corregida: IZQUIERDA/DERECHA cambia de forma fiable al episodio anterior/siguiente y admite más mapas del mando.",
            "El cambio de episodio se mantiene dentro de la misma serie y temporada y funciona mejor desde Vistos recientemente.",
        ],
    },
    "0.8.4": {
        "de": [
            "Update-Hinweise zeigen jetzt automatisch alle Neuerungen seit der zuletzt gesehenen Version – auch bei größeren Versionssprüngen.",
            "Während einer Serienfolge wechselt PFEIL RECHTS direkt zur nächsten Folge und PFEIL LINKS zur vorherigen Folge.",
        ],
        "en": [
            "Update notes now automatically include every change since the last version you saw, even across larger version jumps.",
            "While watching a series, RIGHT jumps to the next episode and LEFT to the previous episode.",
        ],
        "tr": [
            "Güncelleme notları artık büyük sürüm atlamalarında bile son gördüğünüz sürümden sonraki tüm yenilikleri gösterir.",
            "Dizi izlerken SAĞ OK bir sonraki bölüme, SOL OK önceki bölüme geçer.",
        ],
        "it": [
            "Le note di aggiornamento mostrano ora tutte le novità dalla versione vista l'ultima volta, anche con salti di più versioni.",
            "Durante una serie, FRECCIA DESTRA passa all'episodio successivo e FRECCIA SINISTRA a quello precedente.",
        ],
        "es": [
            "Las notas de actualización muestran ahora todas las novedades desde la última versión vista, incluso al saltar varias versiones.",
            "Durante una serie, FLECHA DERECHA pasa al episodio siguiente y FLECHA IZQUIERDA al anterior.",
        ],
    },
    "0.8.2": {
        "de": [
            "Neue hochwertige Premium-Icons auf der Hauptseite.",
            "Neues animiertes Epi-MediaHub-Intro bei jedem App-Start; mit OK oder EXIT überspringbar.",
            "Serien spielen nach dem Ende einer Folge automatisch die nächste Folge ab.",
            "Zuletzt angesehen wird bei Serienfolgen beim Folgenwechsel und am Folgenende zuverlässig aktualisiert.",
        ],
        "en": [
            "New premium-quality icons on the home screen.",
            "New animated Epi MediaHub intro on every app start; press OK or EXIT to skip.",
            "Series automatically continue with the next episode when an episode ends.",
            "Recently watched is now reliably updated when episodes end or advance.",
        ],
        "tr": [
            "Ana ekranda yeni yüksek kaliteli premium simgeler.",
            "Her uygulama açılışında yeni animasyonlu Epi MediaHub girişi; OK veya EXIT ile atlanabilir.",
            "Dizi bölümü bittiğinde bir sonraki bölüm otomatik oynatılır.",
            "Son izlenenler, bölüm bittiğinde veya sonraki bölüme geçildiğinde güvenilir biçimde güncellenir.",
        ],
        "it": [
            "Nuove icone premium di alta qualità nella schermata principale.",
            "Nuova intro animata Epi MediaHub a ogni avvio; si può saltare con OK o EXIT.",
            "Le serie avviano automaticamente l'episodio successivo al termine di una puntata.",
            "Visti di recente viene aggiornato correttamente a fine episodio e al passaggio alla puntata successiva.",
        ],
        "es": [
            "Nuevos iconos premium de alta calidad en la pantalla principal.",
            "Nueva intro animada de Epi MediaHub en cada inicio; se puede omitir con OK o EXIT.",
            "Las series reproducen automáticamente el siguiente episodio al terminar uno.",
            "Vistos recientemente se actualiza correctamente al finalizar o avanzar de episodio.",
        ],
    },
    "0.8.1": {
        "de": [
            "Große Bildschirmmeldung bei nicht verfügbaren oder defekten Live-Streams.",
            "Die Stream-Meldung weist jetzt ausdrücklich darauf hin, es später erneut zu versuchen.",
            "Nach jedem App-Update erscheint einmalig ein Fenster mit den Neuerungen der installierten Version.",
        ],
        "en": [
            "Large on-screen warning for unavailable or broken live streams.",
            "The stream warning now explicitly asks you to try again later.",
            "After every app update, a one-time window shows what is new in the installed version.",
        ],
        "tr": [
            "Kullanılamayan veya bozuk canlı yayınlar için büyük ekran uyarısı.",
            "Yayın uyarısı artık daha sonra tekrar denemenizi açıkça belirtir.",
            "Her uygulama güncellemesinden sonra yeni özellikleri gösteren pencere bir kez açılır.",
        ],
        "it": [
            "Avviso grande sullo schermo per stream live non disponibili o difettosi.",
            "L'avviso dello stream invita ora esplicitamente a riprovare più tardi.",
            "Dopo ogni aggiornamento dell'app compare una sola volta una finestra con le novità della versione installata.",
        ],
        "es": [
            "Aviso grande en pantalla para streams en directo no disponibles o defectuosos.",
            "El aviso del stream indica ahora expresamente que se vuelva a intentar más tarde.",
            "Después de cada actualización de la app aparece una sola vez una ventana con las novedades de la versión instalada.",
        ],
    },
}


def release_notes_text(version, last_seen_version=""):
    current = clean_text(version)
    previous = clean_text(last_seen_version)
    lang = current_app_language()

    # Fresh installs should only see the current release. On upgrades, collect
    # every embedded release newer than the last version the user has seen.
    versions = []
    if previous:
        for item in _RELEASE_NOTES.keys():
            try:
                if version_tuple(item) > version_tuple(previous) and version_tuple(item) <= version_tuple(current):
                    versions.append(item)
            except Exception:
                pass
        versions.sort(key=version_tuple)
    elif current in _RELEASE_NOTES:
        versions = [current]

    if not versions:
        return ""

    titles = {
        "de": "NEU IN EPI MEDIAHUB",
        "en": "WHAT'S NEW IN EPI MEDIAHUB",
        "tr": "EPI MEDIAHUB YENİLİKLER",
        "it": "NOVITÀ IN EPI MEDIAHUB",
        "es": "NOVEDADES DE EPI MEDIAHUB",
    }
    title = (titles.get(lang) or titles["de"]) + " v%s" % current
    sections = []
    for item in versions:
        notes_by_lang = _RELEASE_NOTES.get(item, {})
        notes = notes_by_lang.get(lang) or notes_by_lang.get("de") or []
        if not notes:
            continue
        # Showing the version heading makes larger jumps easy to understand.
        lines = ["v%s" % item]
        lines.extend("- %s" % note for note in notes)
        sections.append("\n".join(lines))
    if not sections:
        return ""
    return title + "\n\n" + "\n\n".join(sections)


def language_display_name(code):
    code = clean_text(code).lower()
    mapping = {"de": "german", "en": "english", "tr": "turkish", "it": "italian", "es": "spanish"}
    return tr(mapping.get(code, "german"))


def localized_help_topics():
    lang = current_app_language()
    topics = {
        "de": [
            ("Einfach per playlists.txt", "SCHNELLSTE PLAYLIST-EINRICHTUNG\n\n1. Per FTP/SFTP öffnen:\n/etc/enigma2/EpiMediaHub/playlists.txt\n2. Pro Playlist genau eine Zeile eintragen:\nM3U-PLUS-URL # Playlistname\n\nBeispiel:\nhttp://server:port/get.php?username=USER&password=PASS&type=m3u_plus&output=ts # Wohnzimmer\n\n3. Datei speichern und Epi MediaHub öffnen. Mehrere Zeilen werden automatisch als mehrere Playlists erkannt. Xtream/M3U-Plus wird automatisch als FAST API erkannt."),
            ("Playlist direkt per URL", "PLAYLIST DIREKT PER URL\n\n1. Öffne PLAYLIST WECHSELN.\n2. Drücke GRÜN = URL hinzufügen.\n3. Gib einen Playlist-Namen ein.\n4. Gib die vollständige M3U-/M3U8-URL ein.\n5. Danach kann die Playlist geladen werden.\n\nTipp: Zugangsdaten in URLs werden in der Anzeige maskiert."),
            ("Komplette M3U-Datei hochladen", "PLAYLIST ALS DATEI ÜBER FTP / SFTP\n\nAlternativ zur playlists.txt kannst du weiterhin komplette .m3u/.m3u8-Dateien nach\n/etc/enigma2/EpiMediaHub/playlists/\nkopieren. Danach Playlist-Auswahl neu öffnen oder GRÜN = FTP/SFTP Scan."),
            ("Per SSH hinzufügen", "PLAYLIST ÜBER SSH HINZUFÜGEN\n\nepimediahub-playlist --add 'Meine Playlist' 'DEINE_M3U_URL'\n\nWeitere Befehle:\nepimediahub-playlist --list\nepimediahub-playlist --select 'Meine Playlist'\nepimediahub-playlist --remove 'Meine Playlist'"),
            ("M3U-Dateien & Ordner", "LOKALE PLAYLIST-DATEIEN\n\nUnterstützt: .m3u und .m3u8\n\nOrdner:\n/etc/enigma2/EpiMediaHub/playlists/\n\nDie Originaldatei bleibt dort erhalten, auch wenn die Playlist aus Epi MediaHub entfernt wird."),
            ("Häufige Probleme", "HÄUFIGE PROBLEME\n\nPlaylist fehlt: Endung und Ordner prüfen und FTP/SFTP Scan ausführen.\n\nSFTP: IP, Receiver-Passwort und SSH-Dienst prüfen.\n\nURL: auf Tippfehler prüfen und in den Einstellungen Playlist laden."),
        ],
        "en": [
            ("Add playlist by URL", "PLAYLIST BY URL\n\n1. Open SWITCH PLAYLIST.\n2. Press GREEN = Add URL.\n3. Enter a playlist name.\n4. Enter the full M3U/M3U8 URL.\n5. Load the playlist afterwards.\n\nCredentials inside URLs are masked on screen."),
            ("Upload via FTP / SFTP", "PLAYLIST VIA FTP / SFTP\n\n1. Connect to the receiver IP.\n   SFTP normally uses port 22; FTP normally uses port 21.\n2. Open:\n/etc/enigma2/EpiMediaHub/playlists/\n3. Copy a .m3u or .m3u8 file there.\n4. Reopen playlist selection or press GREEN = FTP/SFTP scan."),
            ("Name with FTP / SFTP", "PLAYLIST NAME FOR FILE UPLOAD\n\nOn first import, the filename becomes the visible playlist name.\n\nFamily.m3u -> Family\nSport IPTV.m3u8 -> Sport IPTV\n\nYou can later rename the visible playlist with YELLOW in SWITCH PLAYLIST."),
            ("Add via SSH", "ADD PLAYLIST VIA SSH\n\nepimediahub-playlist --add 'My Playlist' 'YOUR_M3U_URL'\n\nCommands:\nepimediahub-playlist --list\nepimediahub-playlist --select 'My Playlist'\nepimediahub-playlist --remove 'My Playlist'"),
            ("M3U files & folder", "LOCAL PLAYLIST FILES\n\nSupported: .m3u and .m3u8\n\nFolder:\n/etc/enigma2/EpiMediaHub/playlists/\n\nThe original file stays there even if you remove the playlist from Epi MediaHub."),
            ("Common problems", "COMMON PROBLEMS\n\nPlaylist missing: check extension/folder and run FTP/SFTP scan.\n\nSFTP: check IP, receiver password and SSH service.\n\nURL: check for typos and use Load playlist in Settings."),
        ],
        "tr": [
            ("URL ile liste ekle", "URL İLE OYNATMA LİSTESİ\n\n1. OYNATMA LİSTESİ DEĞİŞTİR'i açın.\n2. YEŞİL = URL ekle.\n3. Liste adını girin.\n4. Tam M3U/M3U8 adresini girin.\n5. Ardından listeyi yükleyin."),
            ("FTP / SFTP ile yükle", "FTP / SFTP İLE OYNATMA LİSTESİ\n\n1. Alıcının IP adresine bağlanın.\n   SFTP genelde 22, FTP genelde 21 portunu kullanır.\n2. Şu klasörü açın:\n/etc/enigma2/EpiMediaHub/playlists/\n3. .m3u veya .m3u8 dosyasını kopyalayın.\n4. Liste ekranını yeniden açın veya YEŞİL ile tarayın."),
            ("FTP / SFTP liste adı", "DOSYA YÜKLEMEDE LİSTE ADI\n\nİlk içe aktarmada dosya adı görünen liste adı olur.\n\nAile.m3u -> Aile\nSport IPTV.m3u8 -> Sport IPTV\n\nDaha sonra OYNATMA LİSTESİ DEĞİŞTİR ekranında SARI ile adı değiştirebilirsiniz."),
            ("SSH ile ekle", "SSH İLE EKLE\n\nepimediahub-playlist --add 'Listem' 'M3U_URL'\n\nepimediahub-playlist --list\nepimediahub-playlist --select 'Listem'\nepimediahub-playlist --remove 'Listem'"),
            ("M3U dosyaları ve klasör", "YEREL DOSYALAR\n\nDesteklenen: .m3u ve .m3u8\n\n/etc/enigma2/EpiMediaHub/playlists/"),
            ("Sık sorunlar", "SIK SORUNLAR\n\nListe görünmüyorsa uzantıyı ve klasörü kontrol edin, FTP/SFTP taraması yapın.\nSFTP için IP, parola ve SSH hizmetini kontrol edin.\nURL için yazım hatalarını kontrol edin."),
        ],
        "it": [
            ("Aggiungi playlist via URL", "PLAYLIST VIA URL\n\n1. Apri CAMBIA PLAYLIST.\n2. Premi VERDE = Aggiungi URL.\n3. Inserisci un nome.\n4. Inserisci l'URL M3U/M3U8 completo.\n5. Carica la playlist."),
            ("Carica via FTP / SFTP", "PLAYLIST VIA FTP / SFTP\n\n1. Collegati all'IP del ricevitore.\n   SFTP usa normalmente la porta 22; FTP la 21.\n2. Apri:\n/etc/enigma2/EpiMediaHub/playlists/\n3. Copia un file .m3u o .m3u8.\n4. Riapri la selezione playlist o premi VERDE per la scansione."),
            ("Nome con FTP / SFTP", "NOME PLAYLIST DA FILE\n\nAl primo import il nome del file diventa il nome visibile della playlist.\n\nFamiglia.m3u -> Famiglia\nSport IPTV.m3u8 -> Sport IPTV\n\nPuoi rinominarla in CAMBIA PLAYLIST con GIALLO."),
            ("Aggiungi via SSH", "AGGIUNGI VIA SSH\n\nepimediahub-playlist --add 'La mia playlist' 'URL_M3U'\n\nepimediahub-playlist --list\nepimediahub-playlist --select 'La mia playlist'\nepimediahub-playlist --remove 'La mia playlist'"),
            ("File M3U e cartella", "FILE PLAYLIST LOCALI\n\nSupportati: .m3u e .m3u8\n\n/etc/enigma2/EpiMediaHub/playlists/"),
            ("Problemi comuni", "PROBLEMI COMUNI\n\nSe manca la playlist controlla estensione/cartella ed esegui la scansione FTP/SFTP.\nPer SFTP controlla IP, password e servizio SSH.\nPer URL controlla eventuali errori."),
        ],
        "es": [
            ("Añadir lista por URL", "LISTA POR URL\n\n1. Abre CAMBIAR LISTA.\n2. Pulsa VERDE = Añadir URL.\n3. Escribe un nombre.\n4. Escribe la URL M3U/M3U8 completa.\n5. Carga la lista."),
            ("Subir por FTP / SFTP", "LISTA POR FTP / SFTP\n\n1. Conéctate a la IP del receptor.\n   SFTP suele usar el puerto 22; FTP el 21.\n2. Abre:\n/etc/enigma2/EpiMediaHub/playlists/\n3. Copia un archivo .m3u o .m3u8.\n4. Vuelve a abrir la selección o pulsa VERDE para escanear."),
            ("Nombre con FTP / SFTP", "NOMBRE DE LISTA AL SUBIR ARCHIVO\n\nEn la primera importación el nombre del archivo será el nombre visible.\n\nFamilia.m3u -> Familia\nSport IPTV.m3u8 -> Sport IPTV\n\nDespués puedes cambiar el nombre con AMARILLO en CAMBIAR LISTA."),
            ("Añadir por SSH", "AÑADIR POR SSH\n\nepimediahub-playlist --add 'Mi lista' 'URL_M3U'\n\nepimediahub-playlist --list\nepimediahub-playlist --select 'Mi lista'\nepimediahub-playlist --remove 'Mi lista'"),
            ("Archivos M3U y carpeta", "ARCHIVOS LOCALES\n\nCompatibles: .m3u y .m3u8\n\n/etc/enigma2/EpiMediaHub/playlists/"),
            ("Problemas frecuentes", "PROBLEMAS FRECUENTES\n\nSi no aparece la lista, revisa extensión/carpeta y ejecuta el escaneo FTP/SFTP.\nPara SFTP revisa IP, contraseña y servicio SSH.\nPara URL revisa errores de escritura."),
        ],
    }
    return topics.get(lang, topics["de"])


def new_profile_id():
    return uuid.uuid4().hex[:12]


def playlist_path(profile_id):
    return os.path.join(DATA_DIR, "playlist_%s.m3u" % profile_id)


def playlist_index_path(profile_id):
    return os.path.join(DATA_DIR, "playlist_%s.index.json" % profile_id)


def playlist_db_path(profile_id):
    return os.path.join(DATA_DIR, "playlist_%s.sqlite" % profile_id)


def xtream_meta_path(profile_id):
    return os.path.join(DATA_DIR, "xtream_%s.json" % profile_id)


def xtream_category_cache_path(profile_id, kind, group_name):
    key = hashlib.sha1((clean_text(kind) + "\0" + clean_text(group_name)).encode("utf-8", "ignore")).hexdigest()[:20]
    return os.path.join(DATA_DIR, "xtreamcache_%s_%s_%s.json" % (profile_id, clean_text(kind) or "all", key))


def favorites_path(profile_id):
    return os.path.join(DATA_DIR, "favorites_%s.json" % profile_id)


def resume_path(profile_id):
    return os.path.join(DATA_DIR, "resume_%s.json" % profile_id)


def recent_path(profile_id):
    return os.path.join(DATA_DIR, "recent_%s.json" % profile_id)


def epg_xml_path(profile_id):
    return os.path.join(DATA_DIR, "epg_%s.xml" % profile_id)


def epg_cache_path(profile_id):
    return os.path.join(DATA_DIR, "epg_%s.json" % profile_id)


def epg_quick_cache_path(profile_id):
    return os.path.join(DATA_DIR, "epg_quick_%s.json" % profile_id)



def default_profile(name="Meine Playlist", url=""):
    return {
        "id": new_profile_id(),
        "name": clean_text(name) or "Meine Playlist",
        "m3u_url": clean_text(url),
        "managed_file": "",
        "managed_text_file": "",
        "expiry": "",
        "expiry_checked_at": 0,
        "online_status": "",
        "online_checked_at": 0,
        "online_error": "",
        "last_update": "",
        "preferred_audio": ["deu", "ita", "tur", "eng"],
        "epg_url": "",
        "epg_url_auto": "",
        "epg_last_update": "",
        "hidden_categories": {"live": [], "movies": [], "series": []},
        "locked_categories": {"live": [], "movies": [], "series": []},
        "source_mode": "m3u",
        "fast_api_error": "",
    }

def migrate_legacy_if_needed():
    ensure_data_dir()
    current = read_json(PROFILES_FILE, None)
    if isinstance(current, dict) and isinstance(current.get("profiles"), list):
        return
    legacy = read_json(LEGACY_CONFIG_FILE, {})
    legacy_url = clean_text(legacy.get("m3u_url", "")) if isinstance(legacy, dict) else ""
    if not legacy_url and os.path.exists(LEGACY_SSH_URL_FILE):
        try:
            with open(LEGACY_SSH_URL_FILE, "r") as handle:
                legacy_url = clean_text(handle.readline())
        except Exception:
            pass
    profiles = []
    active_id = ""
    if legacy_url or os.path.exists(LEGACY_PLAYLIST_FILE):
        profile = default_profile("Meine Playlist", legacy_url)
        if isinstance(legacy, dict):
            profile["expiry"] = clean_text(legacy.get("expiry", ""))
            profile["last_update"] = clean_text(legacy.get("last_update", ""))
            prefs = legacy.get("preferred_audio")
            if isinstance(prefs, list) and prefs:
                profile["preferred_audio"] = prefs
        profiles.append(profile)
        active_id = profile["id"]
        try:
            if os.path.exists(LEGACY_PLAYLIST_FILE):
                shutil.copyfile(LEGACY_PLAYLIST_FILE, playlist_path(profile["id"]))
        except Exception:
            pass
        try:
            if os.path.exists(LEGACY_FAVORITES_FILE):
                shutil.copyfile(LEGACY_FAVORITES_FILE, favorites_path(profile["id"]))
        except Exception:
            pass
    write_json(PROFILES_FILE, {"active_id": active_id, "profiles": profiles})


def load_profiles():
    migrate_legacy_if_needed()
    data = read_json(PROFILES_FILE, {"active_id": "", "profiles": []})
    if not isinstance(data, dict):
        data = {"active_id": "", "profiles": []}
    profiles = data.get("profiles", [])
    if not isinstance(profiles, list):
        profiles = []
    cleaned = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        profile.setdefault("id", new_profile_id())
        profile.setdefault("name", "Meine Playlist")
        profile.setdefault("m3u_url", "")
        profile.setdefault("managed_file", "")
        profile.setdefault("managed_text_file", "")
        profile.setdefault("expiry", "")
        profile.setdefault("expiry_checked_at", 0)
        profile.setdefault("online_status", "")
        profile.setdefault("online_checked_at", 0)
        profile.setdefault("online_error", "")
        profile.setdefault("last_update", "")
        profile.setdefault("preferred_audio", ["deu", "ita", "tur", "eng"])
        prefs = profile.get("preferred_audio")
        if isinstance(prefs, list) and prefs and "tur" not in prefs:
            try:
                eng_index = prefs.index("eng")
                prefs.insert(eng_index, "tur")
            except ValueError:
                prefs.append("tur")
            profile["preferred_audio"] = prefs
        profile.setdefault("epg_url", "")
        profile.setdefault("epg_url_auto", "")
        profile.setdefault("epg_last_update", "")
        profile.setdefault("hidden_categories", {"live": [], "movies": [], "series": []})
        profile.setdefault("locked_categories", {"live": [], "movies": [], "series": []})
        profile.setdefault("source_mode", "m3u")
        profile.setdefault("fast_api_error", "")
        if not isinstance(profile.get("hidden_categories"), dict):
            profile["hidden_categories"] = {"live": [], "movies": [], "series": []}
        if not isinstance(profile.get("locked_categories"), dict):
            profile["locked_categories"] = {"live": [], "movies": [], "series": []}
        for _kind in ("live", "movies", "series"):
            profile["hidden_categories"].setdefault(_kind, [])
            profile["locked_categories"].setdefault(_kind, [])
        cleaned.append(profile)
    data["profiles"] = cleaned
    if data.get("active_id") and not any(p.get("id") == data.get("active_id") for p in cleaned):
        data["active_id"] = cleaned[0].get("id") if cleaned else ""
    return data


def save_profiles(data):
    return write_json(PROFILES_FILE, data)


def get_profile(profile_id):
    data = load_profiles()
    for profile in data.get("profiles", []):
        if profile.get("id") == profile_id:
            return profile
    return None


def update_profile(profile):
    data = load_profiles()
    for index, existing in enumerate(data.get("profiles", [])):
        if existing.get("id") == profile.get("id"):
            data["profiles"][index] = profile
            return save_profiles(data)
    data["profiles"].append(profile)
    return save_profiles(data)


def set_active_profile(profile_id):
    data = load_profiles()
    if any(p.get("id") == profile_id for p in data.get("profiles", [])):
        data["active_id"] = profile_id
        return save_profiles(data)
    return False


def attr_from_extinf(line, attr):
    match = re.search(r'%s=["\']([^"\']*)["\']' % re.escape(attr), line, re.I)
    return clean_text(match.group(1)) if match else ""


def display_title_from_extinf(line):
    if "," in line:
        return clean_text(line.split(",", 1)[1])
    return "Unbenannter Eintrag"


def detect_epg_url(text):
    for raw in text.splitlines()[:8]:
        line = clean_text(raw)
        if not line.upper().startswith("#EXTM3U"):
            continue
        for key in ("x-tvg-url", "url-tvg"):
            value = attr_from_extinf(line, key)
            if value:
                return value.split(",")[0].strip()
    return ""


def classify_entry(title, group, url, tvg_id=""):
    """Classify generic M3U entries conservatively.

    Explicit Xtream URL paths win. A real tvg-id is a strong live-TV signal and
    is deliberately checked before fuzzy group-name heuristics. This prevents
    live channels in groups such as "Film & Serien" from leaking into VOD.
    """
    haystack = (title + " " + group).lower()
    path = url.lower().split("?", 1)[0]
    if "/series/" in path:
        return "series"
    if "/movie/" in path:
        return "movies"
    if "/live/" in path:
        return "live"
    if clean_text(tvg_id):
        return "live"
    for pattern in (r"\bs\d{1,2}\s*e\d{1,3}\b", r"\b\d{1,2}x\d{1,3}\b", r"\bepisode\s*\d+\b", r"\bfolge\s*\d+\b"):
        if re.search(pattern, haystack, re.I):
            return "series"
    if path.endswith((".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".iso")):
        return "movies"
    if any(word in haystack for word in ("series", "serien", "serie ", "tv shows", "tv-show", "episodes", "staffel", "season ", "boxset")):
        return "series"
    if any(word in haystack for word in ("movies", "movie ", "filme", "film ", "vod", "cinema", "kino", "peliculas", "película", "films")):
        return "movies"
    return "live"


def _entry_from_extinf(line):
    return {
        "title": display_title_from_extinf(line),
        "group": attr_from_extinf(line, "group-title") or "Ohne Kategorie",
        "logo": attr_from_extinf(line, "tvg-logo"),
        "tvg_id": attr_from_extinf(line, "tvg-id"),
        "tvg_name": attr_from_extinf(line, "tvg-name"),
    }


def parse_m3u(text):
    entries = []
    pending = None
    for raw in text.splitlines():
        line = clean_text(raw)
        if not line:
            continue
        if line.startswith("#EXTINF"):
            pending = _entry_from_extinf(line)
            continue
        if line.startswith("#"):
            continue
        if pending is not None:
            pending["url"] = line
            pending["type"] = classify_entry(pending.get("title", ""), pending.get("group", ""), line, pending.get("tvg_id", ""))
            entries.append(pending)
            pending = None
    return entries


def parse_m3u_file(path):
    entries = []
    pending = None
    with open(path, "rb") as handle:
        for raw in handle:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "ignore")
            line = clean_text(raw)
            if not line:
                continue
            if line.startswith("#EXTINF"):
                pending = _entry_from_extinf(line)
                continue
            if line.startswith("#"):
                continue
            if pending is not None:
                pending["url"] = line
                pending["type"] = classify_entry(pending.get("title", ""), pending.get("group", ""), line, pending.get("tvg_id", ""))
                entries.append(pending)
                pending = None
    return entries


def read_playlist_text(path, limit=None):
    try:
        with open(path, "rb") as handle:
            raw = handle.read(limit) if limit else handle.read()
        return raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw
    except Exception:
        return ""


def _save_playlist_index(profile_id, entries):
    path = playlist_index_path(profile_id)
    tmp = path + ".tmp"
    ensure_data_dir()
    with open(tmp, "w") as handle:
        json.dump(entries, handle, separators=(",", ":"))
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    os.rename(tmp, path)




def _append_xtream_candidate(result, seen, base, username, password, output="ts"):
    base = clean_text(base).rstrip("/")
    username = clean_text(username)
    password = clean_text(password)
    output = clean_text(output) or "ts"
    if not base or not username or not password:
        return
    key = (base, username, password)
    if key in seen:
        return
    seen.add(key)
    result.append({"base": base, "username": username, "password": password, "output": output})


def xtream_configs_from_url(url):
    """Return plausible Xtream Player-API configurations from an M3U URL.

    Supports standard get.php links as well as common aliases such as user/pass.
    Short/redirect URLs are handled separately by xtream_configs_from_remote_probe().
    """
    result = []
    seen = set()
    try:
        parsed = urlparse(clean_text(url))
        query = parse_qs(parsed.query)
        username = clean_text((query.get("username") or query.get("user") or [""])[0])
        password = clean_text((query.get("password") or query.get("pass") or [""])[0])
        if not parsed.scheme or not parsed.netloc or not username or not password:
            return []
        output = clean_text(query.get("output", ["ts"])[0]) or "ts"
        path = (parsed.path or "").rstrip("/")
        dirname = path.rsplit("/", 1)[0] if "/" in path else ""
        basename = path.rsplit("/", 1)[-1].lower() if path else ""
        base_paths = []
        if basename in ("get.php", "player_api.php", "panel_api.php", "xmltv.php"):
            base_paths.append(dirname)
        elif path:
            base_paths.append(dirname)
        base_paths.append("")
        for base_path in base_paths:
            base = "%s://%s%s" % (parsed.scheme, parsed.netloc, base_path)
            _append_xtream_candidate(result, seen, base, username, password, output)
    except Exception:
        pass
    return result


def xtream_configs_from_stream_url(stream_url, output="ts"):
    """Derive Xtream credentials from common stream URL path formats.

    Typical Xtream M3U entries look like /live/user/pass/123.ts,
    /movie/user/pass/456.mkv or /series/user/pass/789.mp4. Some panels use
    the older /user/pass/123 form; candidates are harmless because every one
    is authenticated against player_api.php before use.
    """
    result = []
    seen = set()
    try:
        parsed = urlparse(clean_text(stream_url))
        if not parsed.scheme or not parsed.netloc:
            return []
        raw_parts = [unquote(x) for x in (parsed.path or "").split("/") if x]
        if len(raw_parts) < 3:
            return []

        lower = [x.lower() for x in raw_parts]
        for marker in ("live", "movie", "series"):
            if marker in lower:
                i = lower.index(marker)
                if len(raw_parts) >= i + 4:
                    prefix = "/" + "/".join(raw_parts[:i]) if i > 0 else ""
                    base = "%s://%s%s" % (parsed.scheme, parsed.netloc, prefix)
                    _append_xtream_candidate(result, seen, base, raw_parts[i + 1], raw_parts[i + 2], output)

        # Older MPEG-TS format: http://host/user/pass/stream_id
        if len(raw_parts) >= 3:
            last = raw_parts[-1].split(".", 1)[0]
            if last.isdigit() or len(last) >= 3:
                prefix_parts = raw_parts[:-3]
                prefix = "/" + "/".join(prefix_parts) if prefix_parts else ""
                base = "%s://%s%s" % (parsed.scheme, parsed.netloc, prefix)
                _append_xtream_candidate(result, seen, base, raw_parts[-3], raw_parts[-2], output)
    except Exception:
        pass
    return result


def _xtream_candidates_from_m3u_file(path, max_bytes=8 * 1024 * 1024):
    result = []
    seen = set()
    if not path or not os.path.isfile(path):
        return result
    read_bytes = 0
    try:
        with open(path, "rb") as handle:
            for raw in handle:
                read_bytes += len(raw)
                if read_bytes > max_bytes:
                    break
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", "ignore")
                line = clean_text(raw)
                if not line or line.startswith("#") or not line.startswith(("http://", "https://")):
                    continue
                for cfg in xtream_configs_from_stream_url(line):
                    _append_xtream_candidate(result, seen, cfg.get("base"), cfg.get("username"), cfg.get("password"), cfg.get("output", "ts"))
                if len(result) >= 8:
                    break
    except Exception:
        pass
    return result


def xtream_configs_from_remote_probe(url, max_bytes=1024 * 1024):
    """Follow redirects and inspect only the beginning of an M3U response.

    This lets short/rewrite playlist URLs switch to Xtream mode without first
    downloading and parsing a 100k+ entry playlist.
    """
    result = []
    seen = set()
    url = clean_text(url)
    if not url:
        return result
    try:
        if requests is not None:
            response = requests.get(
                url,
                headers={"User-Agent": "EpiMediaHub/%s" % PLUGIN_VERSION, "Accept-Encoding": "gzip, deflate"},
                timeout=(5, 10),
                stream=True,
                allow_redirects=True,
                verify=False,
            )
            try:
                final_url = clean_text(getattr(response, "url", ""))
                for cfg in xtream_configs_from_url(final_url):
                    _append_xtream_candidate(result, seen, cfg.get("base"), cfg.get("username"), cfg.get("password"), cfg.get("output", "ts"))
                buf = b""
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    buf += chunk
                    if len(buf) >= max_bytes:
                        break
                text = buf.decode("utf-8", "ignore") if isinstance(buf, bytes) else clean_text(buf)
            finally:
                response.close()
        else:
            response = urlopen(Request(url, headers={"User-Agent": "EpiMediaHub/%s" % PLUGIN_VERSION}), timeout=10)
            try:
                final_url = clean_text(getattr(response, "geturl", lambda: url)())
                for cfg in xtream_configs_from_url(final_url):
                    _append_xtream_candidate(result, seen, cfg.get("base"), cfg.get("username"), cfg.get("password"), cfg.get("output", "ts"))
                raw = response.read(max_bytes)
                text = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else clean_text(raw)
            finally:
                response.close()

        for line in text.splitlines():
            line = clean_text(line)
            if not line or line.startswith("#") or not line.startswith(("http://", "https://")):
                continue
            for cfg in xtream_configs_from_stream_url(line):
                _append_xtream_candidate(result, seen, cfg.get("base"), cfg.get("username"), cfg.get("password"), cfg.get("output", "ts"))
            if len(result) >= 8:
                break
    except Exception:
        pass
    return result


def xtream_configs_for_profile(profile, include_remote=False):
    result = []
    seen = set()
    url = clean_text(profile.get("m3u_url", "")) if profile else ""
    output = "ts"
    for cfg in xtream_configs_from_url(url):
        output = cfg.get("output", output)
        _append_xtream_candidate(result, seen, cfg.get("base"), cfg.get("username"), cfg.get("password"), cfg.get("output", output))

    # Existing local M3U cache is the cheapest and fastest recovery source.
    if profile and profile.get("id"):
        for path in (playlist_path(profile.get("id")), clean_text(profile.get("managed_file", ""))):
            for cfg in _xtream_candidates_from_m3u_file(path):
                _append_xtream_candidate(result, seen, cfg.get("base"), cfg.get("username"), cfg.get("password"), cfg.get("output", output))

    # Only touch the remote M3U when direct/cached discovery was insufficient.
    if include_remote and url:
        for cfg in xtream_configs_from_remote_probe(url):
            _append_xtream_candidate(result, seen, cfg.get("base"), cfg.get("username"), cfg.get("password"), cfg.get("output", output))
    return result

def xtream_config_from_url(url):
    configs = xtream_configs_from_url(url)
    return configs[0] if configs else None


def load_xtream_meta(profile_id):
    data = read_json(xtream_meta_path(profile_id), {})
    if not isinstance(data, dict):
        return {}
    if data.get("source") == "xtream" and int(data.get("catchup_schema", 0) or 0) < 1:
        data.setdefault("loaded_categories", {})["live"] = []
        data.setdefault("full_loaded", {})["live"] = False
        data["catchup_schema"] = 1
        try:
            write_json(xtream_meta_path(profile_id), data)
        except Exception:
            pass
    return data


def save_xtream_meta(profile_id, data):
    return write_json(xtream_meta_path(profile_id), data)


def is_xtream_profile(profile):
    if not profile:
        return False
    if clean_text(profile.get("source_mode", "")) == "xtream":
        return bool(load_xtream_meta(profile.get("id", "")))
    return False


def db_source_mode(profile_id):
    meta = load_xtream_meta(profile_id)
    return "xtream" if meta.get("source") == "xtream" else "m3u"


def _xtream_api_url(meta, action="", extra=None):
    params = {"username": meta.get("username", ""), "password": meta.get("password", "")}
    if action:
        params["action"] = action
    if extra:
        params.update(extra)
    return "%s/player_api.php?%s" % (meta.get("base", "").rstrip("/"), urlencode(params))



def _xtream_fetch(meta, action="", extra=None, timeout=20):
    """Fetch one Xtream JSON endpoint with compression, retry and short connect timeout."""
    url = _xtream_api_url(meta, action, extra)
    headers = {
        "User-Agent": "EpiMediaHub/%s" % PLUGIN_VERSION,
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }

    if requests is not None:
        session = requests.Session()
        try:
            if HTTPAdapter is not None:
                try:
                    retry = RequestsRetry(total=1, connect=1, read=1, backoff_factor=0.15,
                                          status_forcelist=(429, 500, 502, 503, 504)) if RequestsRetry is not None else None
                    if retry is not None:
                        adapter = HTTPAdapter(max_retries=retry)
                        session.mount("http://", adapter)
                        session.mount("https://", adapter)
                except Exception:
                    pass
            # Many IPTV panels use incomplete certificate chains.  The credentials
            # are still transported over TLS; compatibility here mirrors common
            # Enigma2 IPTV clients.  Update downloads remain SHA256 verified.
            response = session.get(url, headers=headers, timeout=(6, max(8, int(timeout))), verify=False)
            response.raise_for_status()
            return response.json()
        finally:
            try:
                session.close()
            except Exception:
                pass

    request = Request(url, headers=headers)
    response = urlopen(request, timeout=timeout)
    try:
        raw = response.read()
        encoding = clean_text(response.headers.get("Content-Encoding", "")).lower()
        if encoding == "gzip":
            raw = gzip.decompress(raw)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "ignore")
        return json.loads(raw or "null")
    finally:
        try:
            response.close()
        except Exception:
            pass


def _xtream_list_payload(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("data", "results", "items"):
            if isinstance(value.get(key), list):
                return value.get(key)
    return []


def _create_empty_db_with_categories(profile_id, category_sets):
    # FAST API must work even on Enigma2 images whose Python build has no
    # sqlite3 module. SQLite is only an optional cache accelerator.
    if sqlite3 is None:
        return False
    final_path = playlist_db_path(profile_id)
    tmp_path = final_path + ".tmp"
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except Exception:
        pass
    connection = sqlite3.connect(tmp_path)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("CREATE TABLE entries (ord INTEGER PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, group_name TEXT NOT NULL, logo TEXT, tvg_id TEXT, tvg_name TEXT, url TEXT NOT NULL, source_id TEXT, tv_archive INTEGER DEFAULT 0, tv_archive_duration INTEGER DEFAULT 0)")
        connection.execute("CREATE TABLE categories (kind TEXT NOT NULL, name TEXT NOT NULL, ord INTEGER NOT NULL, item_count INTEGER NOT NULL, PRIMARY KEY(kind, name))")
        rows = []
        for kind in ("live", "movies", "series"):
            for idx, cat in enumerate(category_sets.get(kind, [])):
                rows.append((kind, clean_text(cat.get("name", "Ohne Kategorie")) or "Ohne Kategorie", idx + 1, -1))
        connection.executemany("INSERT OR REPLACE INTO categories(kind,name,ord,item_count) VALUES(?,?,?,?)", rows)
        connection.execute("CREATE INDEX idx_entries_kind_ord ON entries(kind, ord)")
        connection.execute("CREATE INDEX idx_entries_kind_group_ord ON entries(kind, group_name, ord)")
        connection.execute("CREATE INDEX idx_entries_kind_title ON entries(kind, title COLLATE NOCASE)")
        connection.commit()
    finally:
        connection.close()
    os.replace(tmp_path, final_path)
    return True



def xtream_bootstrap(profile):
    """Authenticate and build only the lightweight category index.

    Category requests are done concurrently.  Stream/VOD/series payloads are
    deliberately *not* downloaded here; they are fetched only when opened.
    """
    candidates = xtream_configs_for_profile(profile, include_remote=False)

    cfg = None
    user = None
    last_error = ""

    def try_candidates(items):
        local_cfg = None
        local_user = None
        local_error = ""
        for candidate in items:
            try:
                probe = _xtream_fetch(candidate, "", timeout=12)
                user_info = probe.get("user_info", {}) if isinstance(probe, dict) else {}
                if str(user_info.get("auth", "1")) not in ("1", "True", "true"):
                    raise Exception("Xtream-Zugang wurde vom Server abgelehnt.")
                local_cfg = candidate
                local_user = probe
                break
            except Exception as error:
                local_error = str(error)
        return local_cfg, local_user, local_error

    if candidates:
        cfg, user, last_error = try_candidates(candidates)

    # Second chance for short/rewrite URLs: follow redirect/read <=1 MB only
    # after the cheap direct/cached candidates did not authenticate.
    if cfg is None:
        remote_candidates = xtream_configs_for_profile(profile, include_remote=True)
        known = set((c.get("base"), c.get("username"), c.get("password")) for c in candidates)
        remote_candidates = [c for c in remote_candidates if (c.get("base"), c.get("username"), c.get("password")) not in known]
        if remote_candidates:
            cfg, user, remote_error = try_candidates(remote_candidates)
            if remote_error:
                last_error = remote_error

    if cfg is None:
        if not candidates and not clean_text(profile.get("m3u_url", "")) and not clean_text(profile.get("managed_file", "")):
            return None
        profile["fast_api_error"] = last_error or "Keine Xtream-Zugangsdaten erkannt oder Player API nicht erreichbar"
        raise Exception(profile["fast_api_error"])

    action_map = [
        ("live", "get_live_categories"),
        ("movies", "get_vod_categories"),
        ("series", "get_series_categories"),
    ]
    category_sets = {"live": [], "movies": [], "series": []}

    def fetch_categories(pair):
        kind, action = pair
        raw = _xtream_fetch(cfg, action, timeout=18)
        return kind, _xtream_list_payload(raw)

    results = []
    if ThreadPoolExecutor is not None:
        try:
            with ThreadPoolExecutor(max_workers=3) as executor:
                results = list(executor.map(fetch_categories, action_map))
        except Exception:
            results = []
    if not results:
        for pair in action_map:
            try:
                results.append(fetch_categories(pair))
            except Exception:
                results.append((pair[0], []))

    for kind, raw in results:
        seen = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            cid = clean_text(item.get("category_id", ""))
            name = clean_text(item.get("category_name", "")) or "Ohne Kategorie"
            key = (cid, name)
            if key in seen:
                continue
            seen.add(key)
            category_sets[kind].append({"id": cid, "name": name})

    # A provider that authenticated but returned no categories at all is not a
    # useful fast-mode endpoint.  Fall back to M3U only in that case.
    if not any(category_sets.values()):
        profile["fast_api_error"] = "Player API lieferte keine Kategorien"
        raise Exception(profile["fast_api_error"])

    meta = dict(cfg)
    meta["profile_id"] = profile.get("id", "")
    meta.update({
        "source": "xtream",
        "categories": category_sets,
        "loaded_categories": {"live": [], "movies": [], "series": []},
        "full_loaded": {"live": False, "movies": False, "series": False},
        "catchup_schema": 1,
        "created": int(time.time()),
    })
    if sqlite3 is not None:
        _create_empty_db_with_categories(profile["id"], category_sets)
    save_xtream_meta(profile["id"], meta)
    profile["source_mode"] = "xtream"
    profile["fast_api_error"] = ""
    user_info = user.get("user_info", {}) if isinstance(user, dict) else {}
    profile["expiry_checked_at"] = int(time.time())
    exp = user_info.get("exp_date")
    if exp:
        try:
            profile["expiry"] = time.strftime("%d.%m.%Y", time.localtime(int(exp)))
        except Exception:
            pass
    elif clean_text(user_info.get("status", "")).lower() in ("active", "enabled"):
        profile["expiry"] = "Unbegrenzt"
    # The authenticated Xtream credentials are also the most reliable source
    # for XMLTV. This is especially important when the original M3U URL is a
    # short/rewrite URL and does not itself expose username/password.
    try:
        profile["epg_url_auto"] = "%s/xmltv.php?%s" % (
            cfg.get("base", "").rstrip("/"),
            urlencode({"username": cfg.get("username", ""), "password": cfg.get("password", "")})
        )
    except Exception:
        pass
    return sum(len(value) for value in category_sets.values())


def _xtream_category_id(meta, kind, name):
    for item in meta.get("categories", {}).get(kind, []):
        if clean_text(item.get("name")) == clean_text(name):
            return clean_text(item.get("id"))
    return ""


def _xtream_stream_url(meta, kind, source_id, extension=""):
    base = meta.get("base", "").rstrip("/")
    user = quote(str(meta.get("username", "")), safe="")
    password = quote(str(meta.get("password", "")), safe="")
    sid = quote(str(source_id), safe="")
    if kind == "live":
        ext = "m3u8" if str(meta.get("output", "ts")).lower() == "m3u8" else "ts"
        return "%s/live/%s/%s/%s.%s" % (base, user, password, sid, ext)
    if kind == "movies":
        ext = clean_text(extension) or "mp4"
        return "%s/movie/%s/%s/%s.%s" % (base, user, password, sid, ext)
    ext = clean_text(extension) or "mp4"
    return "%s/series/%s/%s/%s.%s" % (base, user, password, sid, ext)


def _xtream_items_to_entries(meta, kind, group_name, items):
    result = []
    for index, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue
        common = {
            "title": clean_text(item.get("name", "")) or ("Serie" if kind == "series" else ("Sender" if kind == "live" else "Film")),
            "group": group_name,
            "logo": first_text(item, "cover", "cover_big", "movie_image", "stream_icon", "poster"),
            "tvg_id": clean_text(item.get("epg_channel_id", item.get("tvg_id", ""))),
            "tvg_name": clean_text(item.get("name", "")),
            "type": kind,
            # Preserve lightweight provider metadata so details can appear
            # instantly without a second lookup whenever the panel supplies it.
            "plot": clean_text(item.get("plot", item.get("description", ""))),
            "rating": item.get("rating", item.get("rating_5based", 0)),
            "genre": clean_text(item.get("genre", "")),
            "release": clean_text(item.get("releaseDate", item.get("releasedate", item.get("release_date", "")))),
            "year": clean_text(item.get("year", "")),
            "duration": clean_text(item.get("duration", "")),
            "director": clean_text(item.get("director", "")),
            "cast": clean_text(item.get("cast", "")),
        }
        if kind == "live":
            try:
                common["tv_archive"] = int(item.get("tv_archive", 0) or 0)
            except Exception:
                common["tv_archive"] = 0
            try:
                common["tv_archive_duration"] = max(0, int(item.get("tv_archive_duration", 0) or 0))
            except Exception:
                common["tv_archive_duration"] = 0
        if kind == "series":
            sid = item.get("series_id", item.get("stream_id", ""))
            if sid in (None, ""):
                continue
            common["source_id"] = clean_text(sid)
            common["url"] = "xtream-series://%s" % sid
        else:
            sid = item.get("stream_id", "")
            if sid in (None, ""):
                continue
            common["source_id"] = clean_text(sid)
            common["url"] = _xtream_stream_url(meta, kind, sid, item.get("container_extension", ""))
        result.append(common)
    return result


def _replace_group_entries(profile_id, kind, group_name, entries, category_order=0):
    connection = _db_connect(profile_id)
    try:
        connection.execute("DELETE FROM entries WHERE kind=? AND group_name=?", (kind, group_name))
        kind_base = {"live": 1000000000, "movies": 2000000000, "series": 3000000000}.get(kind, 4000000000)
        base_ord = kind_base + max(0, int(category_order)) * 1000000
        rows = []
        for idx, entry in enumerate(entries):
            rows.append((base_ord + idx + 1, kind, entry.get("title", ""), group_name, entry.get("logo", ""), entry.get("tvg_id", ""), entry.get("tvg_name", ""), entry.get("url", ""), entry.get("source_id", ""), int(entry.get("tv_archive", 0) or 0), int(entry.get("tv_archive_duration", 0) or 0)))
        if rows:
            connection.executemany("INSERT OR REPLACE INTO entries(ord,kind,title,group_name,logo,tvg_id,tvg_name,url) VALUES(?,?,?,?,?,?,?,?)", rows)
        connection.execute("UPDATE categories SET item_count=? WHERE kind=? AND name=?", (len(rows), kind, group_name))
        connection.commit()
    finally:
        connection.close()


def xtream_category_loaded(profile_id, kind, group_name):
    meta = load_xtream_meta(profile_id)
    return clean_text(group_name) in set(meta.get("loaded_categories", {}).get(kind, []))



def xtream_fetch_category_entries(profile_id, kind, group_name):
    """Fetch one category only and return display-ready entries without waiting for disk caching."""
    meta = load_xtream_meta(profile_id)
    if meta.get("source") != "xtream":
        return [], 0
    category_id = _xtream_category_id(meta, kind, group_name)
    action = {"live": "get_live_streams", "movies": "get_vod_streams", "series": "get_series"}.get(kind)
    if not action:
        return [], 0
    extra = {"category_id": category_id} if category_id else None
    raw = _xtream_list_payload(_xtream_fetch(meta, action, extra=extra, timeout=30))
    entries = _xtream_items_to_entries(meta, kind, group_name, raw)
    cat_order = 0
    for idx, cat in enumerate(meta.get("categories", {}).get(kind, [])):
        if clean_text(cat.get("name")) == clean_text(group_name):
            cat_order = idx + 1
            break
    return entries, cat_order


def xtream_cache_category_entries(profile_id, kind, group_name, entries, cat_order=0):
    # SQLite is optional. On minimal OpenATV/Python images cache each Xtream
    # category as a compact JSON file instead of blocking FAST API entirely.
    if sqlite3 is not None:
        _replace_group_entries(profile_id, kind, group_name, entries, cat_order)
    else:
        write_json(xtream_category_cache_path(profile_id, kind, group_name), list(entries or []))

    meta = load_xtream_meta(profile_id)
    loaded = meta.setdefault("loaded_categories", {}).setdefault(kind, [])
    if group_name not in loaded:
        loaded.append(group_name)
    for cat in meta.setdefault("categories", {}).setdefault(kind, []):
        if clean_text(cat.get("name")) == clean_text(group_name):
            cat["count"] = len(entries or [])
            break
    save_xtream_meta(profile_id, meta)
    return len(entries or [])


def xtream_load_category(profile_id, kind, group_name):
    meta = load_xtream_meta(profile_id)
    if meta.get("source") != "xtream":
        return 0
    if xtream_category_loaded(profile_id, kind, group_name):
        return len(playlist_entries(profile_id, kind=kind, group=group_name))
    entries, cat_order = xtream_fetch_category_entries(profile_id, kind, group_name)
    return xtream_cache_category_entries(profile_id, kind, group_name, entries, cat_order)


def xtream_load_kind(profile_id, kind):
    meta = load_xtream_meta(profile_id)
    if meta.get("source") != "xtream":
        return 0
    if meta.get("full_loaded", {}).get(kind, False):
        return len(playlist_entries(profile_id, kind=kind))
    action = {"live": "get_live_streams", "movies": "get_vod_streams", "series": "get_series"}.get(kind)
    raw = _xtream_fetch(meta, action, timeout=60)
    raw = _xtream_list_payload(raw)
    cat_by_id = {clean_text(c.get("id")): clean_text(c.get("name")) or "Ohne Kategorie" for c in meta.get("categories", {}).get(kind, [])}
    grouped = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        cid = clean_text(item.get("category_id", ""))
        name = cat_by_id.get(cid, "Ohne Kategorie")
        grouped.setdefault(name, []).append(item)
    for name, items in grouped.items():
        entries = _xtream_items_to_entries(meta, kind, name, items)
        cat_order = 0
        for idx, cat in enumerate(meta.get("categories", {}).get(kind, [])):
            if clean_text(cat.get("name")) == name:
                cat_order = idx + 1
                cat["count"] = len(entries)
                break
        if sqlite3 is not None:
            _replace_group_entries(profile_id, kind, name, entries, cat_order)
        else:
            write_json(xtream_category_cache_path(profile_id, kind, name), entries)
    meta.setdefault("full_loaded", {})[kind] = True
    meta.setdefault("loaded_categories", {})[kind] = [clean_text(c.get("name")) for c in meta.get("categories", {}).get(kind, [])]
    save_xtream_meta(profile_id, meta)
    return len(playlist_entries(profile_id, kind=kind))


def _series_number(value, default=None):
    """Return an integer season/episode number when providers use mixed formats."""
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except Exception:
        pass
    value = clean_text(value)
    if not value:
        return default
    lowered = value.lower()
    if "special" in lowered:
        return 0
    match = re.search(r"\d+", value)
    if match:
        try:
            return int(match.group(0))
        except Exception:
            pass
    return default


def _episode_numbers_from_title(title):
    title = clean_text(title)
    for pattern in (r"(?i)\bS(\d{1,3})\s*E(\d{1,4})\b", r"(?i)\b(\d{1,3})x(\d{1,4})\b"):
        match = re.search(pattern, title)
        if match:
            try:
                return int(match.group(1)), int(match.group(2))
            except Exception:
                pass
    return None, None


def _normalise_series_episode(meta, series_entry, series_id, ep, season_hint=None, index=0):
    if not isinstance(ep, dict):
        return None
    eid = ep.get("id", ep.get("stream_id", ""))
    if eid in (None, ""):
        return None

    raw_title = clean_text(ep.get("title", ""))
    title_season, title_episode = _episode_numbers_from_title(raw_title)
    season = _series_number(ep.get("season"), _series_number(season_hint, title_season))
    number = _series_number(ep.get("episode_num", ep.get("episode")), title_episode)
    display_title = raw_title or ("Episode %s" % (number if number is not None else index + 1))

    # Within a selected season the shorter "Folge" prefix is easier to scan.
    # Do not duplicate it when the provider already starts the title that way.
    if number is not None and not re.match(r"(?i)^\s*(folge|episode|ep\.?|s\d+\s*e\d+|\d+x\d+)", display_title):
        display_title = "Folge %02d - %s" % (number, display_title)

    info = ep.get("info", {}) if isinstance(ep.get("info"), dict) else {}
    return {
        "title": display_title,
        "group": series_entry.get("title", "Serie"),
        "parent_group": series_entry.get("group", ""),
        "logo": first_text(info, "movie_image", "cover_big", "cover", "stream_icon") or series_entry.get("logo", ""),
        "tvg_id": "",
        "tvg_name": "",
        "url": _xtream_stream_url(meta, "series", eid, ep.get("container_extension", "")),
        "type": "series",
        "is_episode": True,
        "series_id": series_id,
        "series_title": series_entry.get("title", "Serie"),
        "season": season,
        "episode": number,
        "plot": first_text(info, "plot", "description") or first_text(ep, "plot", "description"),
        "rating": info.get("rating", ep.get("rating", 0)),
        "duration": first_text(info, "duration") or first_text(ep, "duration"),
        "release": first_text(info, "releaseDate", "releasedate", "release_date") or first_text(ep, "releaseDate", "releasedate", "release_date"),
        "_provider_order": index,
    }


def xtream_series_seasons(profile_id, entry):
    """Load one series and return season records with only their own episodes."""
    meta = load_xtream_meta(profile_id)
    match = re.match(r"^xtream-series://(.+)$", clean_text(entry.get("url", "")))
    if not match or meta.get("source") != "xtream":
        return []
    series_id = match.group(1)
    data = _xtream_fetch(meta, "get_series_info", {"series_id": series_id}, timeout=30)
    episodes = data.get("episodes", {}) if isinstance(data, dict) else {}

    grouped = {}
    order_counter = 0

    def append_episode(raw_ep, season_hint=None):
        nonlocal order_counter
        normalised = _normalise_series_episode(meta, entry, series_id, raw_ep, season_hint, order_counter)
        order_counter += 1
        if not normalised:
            return
        season = normalised.get("season")
        grouped.setdefault(season, []).append(normalised)

    if isinstance(episodes, dict):
        # Xtream commonly returns {"1": [...], "2": [...]}. The key is the
        # most reliable season number when individual episode rows omit it.
        for season_key, values in episodes.items():
            if isinstance(values, list):
                for ep in values:
                    append_episode(ep, season_key)
            elif isinstance(values, dict):
                append_episode(values, season_key)
    elif isinstance(episodes, list):
        for ep in episodes:
            append_episode(ep, None)

    def season_sort_key(value):
        if value is None:
            return (2, 999999)
        if value == 0:
            return (0, 0)
        return (1, int(value))

    result = []
    for season in sorted(grouped.keys(), key=season_sort_key):
        season_episodes = grouped.get(season, [])
        season_episodes.sort(key=lambda ep: (
            ep.get("episode") is None,
            ep.get("episode") if ep.get("episode") is not None else 999999,
            ep.get("_provider_order", 0),
        ))
        for ep in season_episodes:
            ep.pop("_provider_order", None)
        if season == 0:
            label = "Specials"
        elif season is None:
            label = "Weitere Folgen"
        else:
            label = "Staffel %d" % season
        result.append({"season": season, "label": label, "episodes": season_episodes})
    return result


def xtream_series_episodes(profile_id, entry):
    """Compatibility helper: flatten the season-aware representation."""
    result = []
    for season in xtream_series_seasons(profile_id, entry):
        result.extend(season.get("episodes", []))
    return result


def version_tuple(value):
    nums = re.findall(r"\d+", clean_text(value))
    return tuple(int(x) for x in nums[:4]) or (0,)


def fetch_update_manifest(url):
    response = urlopen(Request(url, headers={"User-Agent": "EpiMediaHub/%s" % PLUGIN_VERSION}), timeout=15)
    raw = response.read()
    response.close()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "ignore")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise Exception("Ungültiges Update-Manifest.")
    return data


def auto_update_check_due(settings):
    if not settings.get("auto_update_check", True):
        return False
    if not clean_text(settings.get("update_manifest_url", "")):
        return False
    try:
        last = int(settings.get("last_update_check", 0) or 0)
    except Exception:
        last = 0
    return (int(time.time()) - last) >= 24 * 60 * 60


def mark_auto_update_check():
    settings = load_global_settings()
    settings["last_update_check"] = int(time.time())
    save_global_settings(settings)


def download_and_install_update(manifest):
    url = clean_text(manifest.get("url", ""))
    expected = clean_text(manifest.get("sha256", "")).lower()
    if not url or len(expected) != 64:
        raise Exception("Manifest benötigt URL und SHA256-Prüfsumme.")
    target = "/tmp/EpiMediaHub_update.ipk"
    response = urlopen(Request(url, headers={"User-Agent": "EpiMediaHub/%s" % PLUGIN_VERSION}), timeout=30)
    h = hashlib.sha256()
    total = 0
    with open(target, "wb") as handle:
        while True:
            chunk = response.read(1024 * 512)
            if not chunk:
                break
            total += len(chunk)
            if total > 25 * 1024 * 1024:
                response.close()
                raise Exception("Update-Datei ist unerwartet groß.")
            h.update(chunk)
            handle.write(chunk)
    response.close()
    if h.hexdigest().lower() != expected:
        try: os.remove(target)
        except Exception: pass
        raise Exception("SHA256-Prüfung fehlgeschlagen.")
    # Persistent settings/playlists are not package-owned. Do not duplicate the
    # complete data/cache tree into RAM-backed /tmp before every package update.
    log_path = "/tmp/epimediahub_update.log"
    for stale in ("/tmp/epimediahub-update-backup", "/tmp/epimediahub-package-backup"):
        try:
            if os.path.isdir(stale):
                shutil.rmtree(stale)
        except Exception:
            pass

    output = ""
    rc = 255
    try:
        process = subprocess.Popen(
            ["opkg", "install", target],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        raw = process.communicate()[0]
        rc = int(process.returncode or 0)
        if isinstance(raw, bytes):
            output = raw.decode("utf-8", "ignore")
        else:
            output = str(raw or "")
    except Exception as error:
        output = "%s: %s" % (error.__class__.__name__, str(error))
        rc = 255

    try:
        with open(log_path, "w") as handle:
            handle.write(output)
    except Exception:
        pass
    try:
        os.remove(target)
    except Exception:
        pass

    if rc != 0:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        detail = "\n".join(lines[-5:]) if lines else "Keine opkg-Ausgabe verfügbar."
        raise Exception("opkg-Fehler %d:\n%s\nLog: %s" % (rc, detail, log_path))
    return True


def read_cached_playlist(profile_id):
    """Compatibility fallback for images without sqlite3."""
    if not profile_id:
        return []
    index = playlist_index_path(profile_id)
    try:
        if os.path.isfile(index):
            data = read_json(index, [])
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def playlist_index_needs_rebuild(profile_id):
    if not profile_id:
        return False
    if db_source_mode(profile_id) == "xtream":
        return False
    m3u = playlist_path(profile_id)
    if not os.path.isfile(m3u):
        return False
    index = playlist_db_path(profile_id) if sqlite3 is not None else playlist_index_path(profile_id)
    try:
        if not os.path.isfile(index):
            return True
        return os.path.getmtime(index) < os.path.getmtime(m3u)
    except Exception:
        return True


def rebuild_playlist_index(profile_id):
    path = playlist_path(profile_id)
    if not os.path.isfile(path):
        raise Exception("Lokale Playlist-Datei wurde nicht gefunden.")
    return build_playlist_db(profile_id, path)

def _detect_epg_from_file(path):
    return detect_epg_url(read_playlist_text(path, 262144))



def copy_local_playlist(profile):
    source = clean_text(profile.get("managed_file", ""))
    if not source or not os.path.isfile(source):
        raise Exception("FTP/SFTP-Datei nicht gefunden: %s" % source)
    target = playlist_path(profile["id"])
    shutil.copyfile(source, target)
    profile["epg_url_auto"] = _detect_epg_from_file(target)
    profile["last_update"] = time.strftime("%d.%m.%Y %H:%M")
    return build_playlist_db(profile["id"], target)


def download_playlist(profile):
    ensure_data_dir()
    url = clean_text(profile.get("m3u_url", ""))
    if not url:
        if clean_text(profile.get("managed_file", "")):
            try:
                count = xtream_bootstrap(profile)
                if count is not None:
                    profile["last_update"] = time.strftime("%d.%m.%Y %H:%M")
                    return count
            except Exception as error:
                profile["fast_api_error"] = str(error)
            profile["source_mode"] = "m3u"
            return copy_local_playlist(profile)
        raise Exception("Keine M3U-URL gespeichert.")

    # Fast path: standard URLs, redirected/short URLs and credentials recovered
    # from an existing M3U are all probed before downloading the huge playlist.
    try:
        count = xtream_bootstrap(profile)
        if count is not None:
            profile["last_update"] = time.strftime("%d.%m.%Y %H:%M")
            return count
    except Exception as error:
        profile["fast_api_error"] = str(error)
        # Provider may expose an M3U but no compatible Player API. Fall back.
        pass

    profile["source_mode"] = "m3u"
    try:
        meta = xtream_meta_path(profile.get("id", ""))
        if os.path.exists(meta):
            os.remove(meta)
    except Exception:
        pass
    request = Request(url, headers={"User-Agent": "EpiMediaHub/%s" % PLUGIN_VERSION})
    response = urlopen(request, timeout=30)
    final_path = playlist_path(profile["id"])
    tmp_path = final_path + ".download"
    total = 0
    max_bytes = 350 * 1024 * 1024

    try:
        with open(tmp_path, "wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise Exception("Playlist ist größer als 350 MB und wurde abgebrochen.")
                handle.write(chunk)
    finally:
        try:
            response.close()
        except Exception:
            pass

    if total <= 0:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise Exception("Die Playlist ist leer.")

    os.replace(tmp_path, final_path)
    try:
        os.chmod(final_path, 0o600)
    except Exception:
        pass

    profile["epg_url_auto"] = _detect_epg_from_file(final_path)
    return build_playlist_db(profile["id"], final_path)

def _parse_playlist_text_file(path=PLAYLIST_TEXT_FILE):
    """Parse XStreamity-style URL lines: URL # optional visible name."""
    result = []
    try:
        with open(path, "r") as handle:
            lines = handle.readlines()
    except Exception:
        return result

    for number, raw in enumerate(lines, 1):
        line = clean_text(raw)
        if not line or line.startswith("#"):
            continue
        url = line
        name = ""
        if "#" in line:
            before, after = line.rsplit("#", 1)
            if clean_text(before).lower().startswith(("http://", "https://")):
                url = clean_text(before)
                name = clean_text(after)
        if not url.lower().startswith(("http://", "https://")):
            continue
        if not name:
            try:
                host = clean_text(urlparse(url).hostname or "")
            except Exception:
                host = ""
            name = host or ("Playlist %d" % number)
        result.append({"name": name, "url": url})
    return result


def _clear_profile_source_cache(profile_id):
    """Drop source-specific caches after a text-file URL changes."""
    for path in (playlist_path(profile_id), playlist_index_path(profile_id), playlist_db_path(profile_id), xtream_meta_path(profile_id)):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


def _sync_text_playlists(data, profiles):
    """Synchronise /etc/enigma2/EpiMediaHub/playlists.txt with URL profiles.

    Profiles created by this file are treated as file-managed. Removing a line
    removes that managed profile from the selector, while user-created URL and
    uploaded .m3u profiles are never deleted by this sync.
    """
    entries = _parse_playlist_text_file()
    managed_path = os.path.abspath(PLAYLIST_TEXT_FILE)
    managed = [p for p in profiles if os.path.abspath(clean_text(p.get("managed_text_file", "")) or "/") == managed_path]
    by_url = {clean_text(p.get("m3u_url", "")): p for p in managed if clean_text(p.get("m3u_url", ""))}
    by_name = {clean_text(p.get("name", "")).lower(): p for p in managed if clean_text(p.get("name", ""))}
    all_by_url = {clean_text(p.get("m3u_url", "")): p for p in profiles if clean_text(p.get("m3u_url", ""))}

    added = 0
    updated = 0
    seen_ids = set()
    for entry in entries:
        url = clean_text(entry.get("url", ""))
        name = clean_text(entry.get("name", "")) or "Playlist"
        profile = by_url.get(url) or by_name.get(name.lower())

        # Avoid duplicating an already existing manually-created URL profile.
        # It stays manually managed; the text file simply points to it.
        if profile is None and url in all_by_url:
            profile = all_by_url[url]
            seen_ids.add(profile.get("id", ""))
            continue

        if profile is None:
            profile = default_profile(name, url)
            profile["managed_text_file"] = PLAYLIST_TEXT_FILE
            profiles.append(profile)
            managed.append(profile)
            by_url[url] = profile
            by_name[name.lower()] = profile
            all_by_url[url] = profile
            added += 1
        else:
            changed = False
            if clean_text(profile.get("name", "")) != name:
                profile["name"] = name
                changed = True
            if clean_text(profile.get("m3u_url", "")) != url:
                profile["m3u_url"] = url
                profile["expiry"] = ""
                profile["expiry_checked_at"] = 0
                profile["epg_url_auto"] = ""
                profile["source_mode"] = "m3u"
                profile["fast_api_error"] = ""
                _clear_profile_source_cache(profile.get("id", ""))
                changed = True
            profile["managed_text_file"] = PLAYLIST_TEXT_FILE
            if changed:
                updated += 1
        seen_ids.add(profile.get("id", ""))

    # playlists.txt is the source of truth only for profiles originally created
    # from it. Manual URL profiles and uploaded .m3u files are untouched.
    removed = [p for p in managed if p.get("id", "") not in seen_ids]
    if removed:
        remove_ids = {p.get("id", "") for p in removed}
        profiles[:] = [p for p in profiles if p.get("id", "") not in remove_ids]
        if data.get("active_id") in remove_ids:
            data["active_id"] = profiles[0].get("id") if profiles else ""
        updated += len(removed)

    return added, updated


def scan_local_playlists():
    ensure_data_dir()
    data = load_profiles()
    profiles = data.get("profiles", [])
    text_added, text_updated = _sync_text_playlists(data, profiles)
    by_file = {}
    for profile in profiles:
        source = clean_text(profile.get("managed_file", ""))
        if source:
            by_file[os.path.abspath(source)] = profile
    added = text_added
    updated = text_updated
    try:
        names = sorted(os.listdir(FTP_PLAYLIST_DIR))
    except Exception:
        names = []
    for filename in names:
        if not filename.lower().endswith((".m3u", ".m3u8")):
            continue
        source = os.path.abspath(os.path.join(FTP_PLAYLIST_DIR, filename))
        if not os.path.isfile(source):
            continue
        profile = by_file.get(source)
        if profile is None:
            name = os.path.splitext(filename)[0].strip() or "Playlist"
            profile = default_profile(name, "")
            profile["managed_file"] = source
            profiles.append(profile)
            by_file[source] = profile
            added += 1
        try:
            src_stat = os.stat(source)
            dst = playlist_path(profile["id"])
            needs_copy = True
            if os.path.exists(dst):
                dst_stat = os.stat(dst)
                needs_copy = src_stat.st_size != dst_stat.st_size or int(src_stat.st_mtime) > int(dst_stat.st_mtime)
            if needs_copy:
                dst = playlist_path(profile["id"])
                shutil.copyfile(source, dst)
                profile["source_mode"] = "m3u"
                try:
                    meta = xtream_meta_path(profile.get("id", ""))
                    if os.path.exists(meta):
                        os.remove(meta)
                except Exception:
                    pass
                profile["epg_url_auto"] = _detect_epg_from_file(dst)
                # Keep the previous valid index in place. The home screen
                # notices that the M3U is newer and rebuilds the index in a
                # background thread, so the UI never suddenly becomes empty.
                updated += 1
        except Exception:
            pass
    if profiles and not data.get("active_id"):
        data["active_id"] = profiles[0].get("id")
    data["profiles"] = profiles
    save_profiles(data)
    return added, updated


def try_fetch_expiry(m3u_url):
    """Read Xtream account expiry without downloading the full playlist.

    This reuses the same requests/urllib compatibility path as the normal
    Xtream API so older OpenATV receivers get the same TLS/retry behaviour.
    """
    for cfg in xtream_configs_from_url(m3u_url):
        try:
            meta = {
                "base": cfg.get("base", ""),
                "username": cfg.get("username", ""),
                "password": cfg.get("password", ""),
            }
            data = _xtream_fetch(meta, timeout=7)
            user_info = data.get("user_info", {}) if isinstance(data, dict) else {}
            if not isinstance(user_info, dict):
                continue
            exp_date = user_info.get("exp_date")
            if exp_date not in (None, "", 0, "0"):
                return time.strftime("%d.%m.%Y", time.localtime(int(exp_date)))
            status = clean_text(user_info.get("status", "")).lower()
            if status in ("active", "enabled"):
                return "Unbegrenzt"
        except Exception:
            continue
    return ""


def probe_playlist_online(profile):
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


def expiry_summary(value):
    if not value:
        return "nicht verfügbar"
    try:
        expiry_time = time.mktime(time.strptime(value, "%d.%m.%Y"))
        now = time.time()
        days = int((expiry_time - now) / 86400.0)
        if days < 0:
            return "%s (abgelaufen)" % value
        if days == 0:
            return "%s (heute)" % value
        return "%s (%d Tage)" % (value, days)
    except Exception:
        return value


def type_label(kind):
    return {"live": tr("live"), "movies": tr("movies"), "series": tr("series")}.get(kind, clean_text(kind).upper())


def audio_label(preferences):
    labels = {"deu": tr("german"), "ita": tr("italian"), "tur": tr("turkish"), "eng": tr("english")}
    return " > ".join(labels.get(item, item) for item in preferences)


def audio_match_score(language, preferences):
    value = clean_text(language).lower()
    aliases = {
        "deu": ("deu", "ger", "de", "deutsch", "german"),
        "ita": ("ita", "it", "italiano", "italian"),
        "tur": ("tur", "tr", "türkçe", "turkce", "turkish", "türkisch"),
        "eng": ("eng", "en", "english"),
    }
    for rank, preferred in enumerate(preferences):
        for alias in aliases.get(preferred, (preferred,)):
            if value == alias or re.search(r"(^|[^a-z])%s([^a-z]|$)" % re.escape(alias), value):
                return rank
    return 999


def pin_hash(pin):
    value = clean_text(pin)
    if not value:
        return ""
    return hashlib.sha256(("EpiMediaHub|" + value).encode("utf-8", "ignore")).hexdigest()


def pin_matches(pin):
    settings = load_global_settings()
    saved = clean_text(settings.get("parental_pin_hash", ""))
    return bool(saved and pin_hash(pin) == saved)



def is_adult_category(name):
    value = clean_text(name).lower()
    patterns = (
        r"(^|[^a-z0-9])18\s*\+([^a-z0-9]|$)",
        r"(^|[^a-z0-9])18\s*plus([^a-z0-9]|$)",
        r"(^|[^a-z0-9])adult(s)?([^a-z0-9]|$)",
        r"(^|[^a-z0-9])xxx([^a-z0-9]|$)",
        r"(^|[^a-z0-9])porn(o)?([^a-z0-9]|$)",
        r"(^|[^a-z0-9])erotik([^a-z0-9]|$)",
        r"(^|[^a-z0-9])erotic([^a-z0-9]|$)",
        r"(^|[^a-z0-9])sex([^a-z0-9]|$)",
        r"(^|[^a-z0-9])playboy([^a-z0-9]|$)",
        r"(^|[^a-z0-9])redlight([^a-z0-9]|$)",
    )
    return any(re.search(pattern, value, re.I) for pattern in patterns)


def _profile_category_list(profile, key, kind):
    container = profile.get(key, {}) if isinstance(profile, dict) else {}
    if not isinstance(container, dict):
        return []
    values = container.get(kind, [])
    return list(values) if isinstance(values, list) else []


def hidden_category_set(profile, kind):
    return set(clean_text(value) for value in _profile_category_list(profile, "hidden_categories", kind) if clean_text(value))


def manual_locked_category_set(profile, kind):
    return set(clean_text(value) for value in _profile_category_list(profile, "locked_categories", kind) if clean_text(value))


def effective_locked_category_set(profile, kind):
    settings = load_global_settings()
    if not settings.get("parental_enabled", False):
        return set()
    locked = manual_locked_category_set(profile, kind)
    if settings.get("parental_auto_adult", True):
        for name, _count in playlist_categories(profile.get("id", ""), kind):
            if is_adult_category(name):
                locked.add(name)
    return locked


def ensure_profile_category_maps(profile):
    if not isinstance(profile.get("hidden_categories"), dict):
        profile["hidden_categories"] = {"live": [], "movies": [], "series": []}
    if not isinstance(profile.get("locked_categories"), dict):
        profile["locked_categories"] = {"live": [], "movies": [], "series": []}
    for kind in ("live", "movies", "series"):
        profile["hidden_categories"].setdefault(kind, [])
        profile["locked_categories"].setdefault(kind, [])
    return profile


def _db_connect(profile_id):
    if sqlite3 is None:
        return None
    connection = sqlite3.connect(playlist_db_path(profile_id))
    connection.row_factory = sqlite3.Row
    if profile_id not in _DB_SCHEMA_READY:
        try:
            columns = set(row[1] for row in connection.execute("PRAGMA table_info(entries)").fetchall())
            for name, definition in (("source_id", "TEXT"), ("tv_archive", "INTEGER DEFAULT 0"), ("tv_archive_duration", "INTEGER DEFAULT 0")):
                if name not in columns:
                    connection.execute("ALTER TABLE entries ADD COLUMN %s %s" % (name, definition))
            connection.commit()
            _DB_SCHEMA_READY.add(profile_id)
        except Exception:
            pass
    return connection


def playlist_db_ready(profile_id):
    if sqlite3 is None or not profile_id:
        return False
    path = playlist_db_path(profile_id)
    if not os.path.isfile(path) or os.path.getsize(path) < 1024:
        return False
    try:
        connection = _db_connect(profile_id)
        # Do not COUNT 190k+ rows just to decide whether the DB is usable.
        row = connection.execute("SELECT 1 FROM categories LIMIT 1").fetchone()
        if row is None and db_source_mode(profile_id) != "xtream":
            row = connection.execute("SELECT 1 FROM entries LIMIT 1").fetchone()
        connection.close()
        return row is not None
    except Exception:
        return False

def build_playlist_db(profile_id, m3u_path):
    if sqlite3 is None:
        entries = parse_m3u_file(m3u_path)
        if not entries:
            raise Exception("Keine M3U-Einträge gefunden.")
        _save_playlist_index(profile_id, entries)
        return len(entries)

    final_path = playlist_db_path(profile_id)
    tmp_path = final_path + ".tmp"
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except Exception:
        pass

    connection = sqlite3.connect(tmp_path)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute("""
            CREATE TABLE entries (
                ord INTEGER PRIMARY KEY,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                group_name TEXT NOT NULL,
                logo TEXT,
                tvg_id TEXT,
                tvg_name TEXT,
                url TEXT NOT NULL,
                source_id TEXT,
                tv_archive INTEGER DEFAULT 0,
                tv_archive_duration INTEGER DEFAULT 0
            )
        """)
        connection.execute("""
            CREATE TABLE categories (
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                ord INTEGER NOT NULL,
                item_count INTEGER NOT NULL,
                PRIMARY KEY(kind, name)
            )
        """)
        categories = {}
        batch = []
        pending = None
        order_no = 0

        with open(m3u_path, "rb") as handle:
            for raw in handle:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", "ignore")
                line = clean_text(raw)
                if not line:
                    continue
                if line.startswith("#EXTINF"):
                    pending = _entry_from_extinf(line)
                    continue
                if line.startswith("#"):
                    continue
                if pending is None:
                    continue

                order_no += 1
                title = pending.get("title", "Unbenannt")
                group = pending.get("group", "") or "Ohne Kategorie"
                kind = classify_entry(title, group, line, pending.get("tvg_id", ""))
                batch.append((
                    order_no, kind, title, group,
                    pending.get("logo", ""), pending.get("tvg_id", ""),
                    pending.get("tvg_name", ""), line, "", 0, 0
                ))

                key = (kind, group)
                if key not in categories:
                    categories[key] = [order_no, 1]
                else:
                    categories[key][1] += 1

                pending = None

                if len(batch) >= 2500:
                    connection.executemany(
                        "INSERT INTO entries(ord,kind,title,group_name,logo,tvg_id,tvg_name,url,source_id,tv_archive,tv_archive_duration) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        batch
                    )
                    batch = []

        if batch:
            connection.executemany(
                "INSERT INTO entries(ord,kind,title,group_name,logo,tvg_id,tvg_name,url,source_id,tv_archive,tv_archive_duration) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                batch
            )

        if order_no <= 0:
            raise Exception("Keine M3U-Einträge gefunden.")

        cat_rows = []
        for (kind, name), values in categories.items():
            cat_rows.append((kind, name, int(values[0]), int(values[1])))
        connection.executemany(
            "INSERT INTO categories(kind,name,ord,item_count) VALUES(?,?,?,?)",
            cat_rows
        )

        # Building indexes after the bulk insert is significantly faster on
        # large playlists than maintaining the indexes for every inserted row.
        connection.execute("CREATE INDEX idx_entries_kind_ord ON entries(kind, ord)")
        connection.execute("CREATE INDEX idx_entries_kind_group_ord ON entries(kind, group_name, ord)")
        connection.execute("CREATE INDEX idx_entries_kind_title ON entries(kind, title COLLATE NOCASE)")
        connection.commit()
    finally:
        connection.close()

    try:
        os.chmod(tmp_path, 0o600)
    except Exception:
        pass
    os.replace(tmp_path, final_path)

    # The old JSON index can be very large and slow to load. Once SQLite is
    # available it is no longer needed.
    try:
        old_index = playlist_index_path(profile_id)
        if os.path.exists(old_index):
            os.remove(old_index)
    except Exception:
        pass

    return order_no


def playlist_counts(profile_id):
    counts = {"live": 0, "movies": 0, "series": 0}
    if db_source_mode(profile_id) == "xtream":
        meta = load_xtream_meta(profile_id)
        for kind in counts:
            total = 0
            for cat in meta.get("categories", {}).get(kind, []):
                try:
                    value = int(cat.get("count", 0))
                except Exception:
                    value = 0
                if value > 0:
                    total += value
            counts[kind] = total
        return counts
    if playlist_db_ready(profile_id):
        try:
            connection = _db_connect(profile_id)
            # categories.item_count is maintained during indexing/caching. Summing
            # a few hundred category rows is far faster than GROUP BY over 190k entries.
            rows = connection.execute(
                "SELECT kind, SUM(CASE WHEN item_count > 0 THEN item_count ELSE 0 END) AS c FROM categories GROUP BY kind"
            ).fetchall()
            connection.close()
            for row in rows:
                if row["kind"] in counts:
                    counts[row["kind"]] = int(row["c"] or 0)
            return counts
        except Exception:
            pass

    if sqlite3 is None:
        for entry in read_cached_playlist(profile_id):
            kind = entry.get("type")
            if kind in counts:
                counts[kind] += 1
    return counts

def playlist_total_count(profile_id):
    counts = playlist_counts(profile_id)
    return sum(counts.values())


def playlist_categories(profile_id, kind):
    if db_source_mode(profile_id) == "xtream":
        meta = load_xtream_meta(profile_id)
        result = []
        for cat in meta.get("categories", {}).get(kind, []):
            name = clean_text(cat.get("name")) or "Ohne Kategorie"
            try:
                count = int(cat.get("count", -1))
            except Exception:
                count = -1
            result.append((name, count))
        return result
    if playlist_db_ready(profile_id):
        try:
            connection = _db_connect(profile_id)
            rows = connection.execute(
                "SELECT name,item_count FROM categories WHERE kind=? ORDER BY ord",
                (kind,)
            ).fetchall()
            connection.close()
            return [(row["name"], int(row["item_count"])) for row in rows]
        except Exception:
            pass

    categories = {}
    if sqlite3 is None:
        for entry in read_cached_playlist(profile_id):
            if entry.get("type") != kind:
                continue
            group = clean_text(entry.get("group")) or "Ohne Kategorie"
            categories[group] = categories.get(group, 0) + 1
    return list(categories.items())


def _row_to_entry(row):
    try:
        keys = set(row.keys())
    except Exception:
        keys = set()
    return {
        "title": row["title"],
        "group": row["group_name"],
        "logo": row["logo"] or "",
        "tvg_id": row["tvg_id"] or "",
        "tvg_name": row["tvg_name"] or "",
        "url": row["url"],
        "type": row["kind"],
        "source_id": (row["source_id"] or "") if "source_id" in keys else "",
        "tv_archive": int(row["tv_archive"] or 0) if "tv_archive" in keys else 0,
        "tv_archive_duration": int(row["tv_archive_duration"] or 0) if "tv_archive_duration" in keys else 0,
    }


def playlist_entries(profile_id, kind=None, group=None, query=None, allowed_groups=None):
    if db_source_mode(profile_id) == "xtream" and sqlite3 is None:
        result = []
        meta = load_xtream_meta(profile_id)
        kinds = [kind] if kind else ["live", "movies", "series"]
        q = clean_text(query).lower()
        for current_kind in kinds:
            names = [group] if group is not None else list(meta.get("loaded_categories", {}).get(current_kind, []))
            for name in names:
                cached = read_json(xtream_category_cache_path(profile_id, current_kind, name), [])
                if not isinstance(cached, list):
                    continue
                for entry in cached:
                    if not isinstance(entry, dict):
                        continue
                    if q and q not in clean_text(entry.get("title", "")).lower():
                        continue
                    result.append(entry)
    elif playlist_db_ready(profile_id):
        where = []
        params = []
        if kind:
            where.append("kind=?")
            params.append(kind)
        if group is not None:
            where.append("group_name=?")
            params.append(group)
        if query:
            where.append("title LIKE ?")
            params.append("%%%s%%" % query)
        sql = "SELECT ord,kind,title,group_name,logo,tvg_id,tvg_name,url,source_id,tv_archive,tv_archive_duration FROM entries"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ord"
        try:
            connection = _db_connect(profile_id)
            rows = connection.execute(sql, tuple(params)).fetchall()
            connection.close()
            result = [_row_to_entry(row) for row in rows]
        except Exception:
            result = []
    else:
        result = []
        if sqlite3 is None:
            q = clean_text(query).lower()
            for entry in read_cached_playlist(profile_id):
                if kind and entry.get("type") != kind:
                    continue
                if group is not None and (clean_text(entry.get("group")) or "Ohne Kategorie") != group:
                    continue
                if q and q not in entry.get("title", "").lower():
                    continue
                result.append(entry)

    if allowed_groups is not None:
        allowed = set(allowed_groups)
        result = [entry for entry in result if (clean_text(entry.get("group")) or "Ohne Kategorie") in allowed]
    return result


def allowed_category_names(profile, kind, include_locked=False):
    profile = ensure_profile_category_maps(profile or {})
    hidden = hidden_category_set(profile, kind)
    locked = effective_locked_category_set(profile, kind)
    names = []
    for name, _count in playlist_categories(profile.get("id", ""), kind):
        if name in hidden:
            continue
        if not include_locked and name in locked:
            continue
        names.append(name)
    return names

def connect_timer(timer, callback):
    try:
        timer.callback.append(callback)
        return
    except Exception:
        pass
    try:
        timer.timeout.connect(callback)
    except Exception:
        pass


def favorite_entries(profile_id):
    data = read_json(favorites_path(profile_id), [])
    return data if isinstance(data, list) else []


def favorite_keys(profile_id):
    return set(item.get("url", "") for item in favorite_entries(profile_id) if isinstance(item, dict))


def recent_entries(profile_id, kind=None, limit=50):
    data = read_json(recent_path(profile_id), [])
    if not isinstance(data, list):
        return []
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if kind and item.get("type") != kind:
            continue
        if not clean_text(item.get("url", "")):
            continue
        result.append(item)
        if len(result) >= int(limit or 50):
            break
    return result


def _recent_identity(entry):
    entry = entry or {}
    if entry.get("type") == "series" and entry.get("is_episode"):
        sid = clean_text(entry.get("series_id", ""))
        if sid:
            return "series:%s" % sid
        title = clean_text(entry.get("series_title", ""))
        if title:
            return "series-title:%s" % title.lower()
    return "%s:%s" % (clean_text(entry.get("type", "")), clean_text(entry.get("url", "")))


def save_recent_entry(profile_id, entry):
    if not profile_id or not isinstance(entry, dict):
        return
    if entry.get("type") not in ("live", "movies", "series") or not clean_text(entry.get("url", "")):
        return
    item = dict(entry)
    item["recent_at"] = int(time.time())
    if item.get("type") == "series" and item.get("is_episode"):
        series_title = clean_text(item.get("series_title", "")) or clean_text(item.get("group", "")) or tr("series")
        season = item.get("season")
        episode = item.get("episode")
        suffix = ""
        if season is not None and episode is not None:
            suffix = "S%02dE%02d" % (int(season), int(episode))
        elif episode is not None:
            suffix = "%s %d" % (tr("episode"), int(episode))
        ep_title = clean_text(item.get("title", ""))
        parts = [series_title]
        if suffix:
            parts.append(suffix)
        if ep_title and ep_title.lower() != series_title.lower():
            parts.append(ep_title)
        item["recent_title"] = "  ·  ".join(parts)
    else:
        item["recent_title"] = clean_text(item.get("title", ""))
    identity = _recent_identity(item)
    old = recent_entries(profile_id, None, 200)
    kept = [row for row in old if _recent_identity(row) != identity]
    write_json(recent_path(profile_id), [item] + kept[:99])


def visible_recent_entries(profile_id, kind, profile=None, limit=40):
    profile = profile or get_profile(profile_id) or {}
    allowed = set(allowed_category_names(profile, kind, include_locked=False))
    result = []
    for item in recent_entries(profile_id, kind, 100):
        group = clean_text(item.get("parent_group", "")) or clean_text(item.get("group", ""))
        # Old history rows may predate parent_group. Keep them unless they
        # explicitly point to a currently locked/hidden provider category.
        if group and group in set(name for name, _count in playlist_categories(profile_id, kind)) and group not in allowed:
            continue
        result.append(item)
        if len(result) >= int(limit or 40):
            break
    return result


def load_resume(profile_id):
    data = read_json(resume_path(profile_id), {})
    return data if isinstance(data, dict) else {}


def get_resume_position(profile_id, url):
    item = load_resume(profile_id).get(hashlib.sha1(url.encode("utf-8", "ignore")).hexdigest(), {})
    try:
        return int(item.get("position", 0))
    except Exception:
        return 0


def save_resume_position(profile_id, url, position, length=0):
    if not profile_id or not url:
        return
    data = load_resume(profile_id)
    key = hashlib.sha1(url.encode("utf-8", "ignore")).hexdigest()
    try:
        position = int(position)
        length = int(length)
    except Exception:
        return
    if position < 30 * 90000 or (length > 0 and float(position) / float(length) > 0.95):
        data.pop(key, None)
    else:
        data[key] = {"position": position, "length": length, "updated": int(time.time())}
    write_json(resume_path(profile_id), data)



# -------------------- Xtream details / short EPG --------------------

def xtream_entry_source_id(entry):
    sid = clean_text((entry or {}).get("source_id", ""))
    if sid:
        return sid
    url = clean_text((entry or {}).get("url", ""))
    if url.startswith("xtream-series://"):
        return clean_text(url.split("//", 1)[-1])
    try:
        parsed = urlparse(url)
        last = (parsed.path or "").rstrip("/").rsplit("/", 1)[-1]
        return clean_text(last.split(".", 1)[0])
    except Exception:
        return ""


def _safe_float(value):
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return 0.0


def _runtime_minutes(value, seconds=0):
    try:
        if seconds:
            return max(0, int(float(seconds)) // 60)
    except Exception:
        pass
    value = clean_text(value)
    if not value:
        return 0
    try:
        if ":" in value:
            parts = [int(x or 0) for x in value.split(":")]
            if len(parts) == 3:
                return parts[0] * 60 + parts[1] + (1 if parts[2] >= 30 else 0)
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
        return int(float(value))
    except Exception:
        return 0


def entry_basic_metadata(entry):
    entry = entry or {}
    release = clean_text(entry.get("release", ""))
    if not release and clean_text(entry.get("year", "")):
        release = clean_text(entry.get("year", ""))
    genre = clean_text(entry.get("genre", ""))
    return {
        "title": clean_text(entry.get("title", "")),
        "rating": _safe_float(entry.get("rating", 0)),
        "votes": 0,
        "overview": clean_text(entry.get("plot", "")),
        "release": release,
        "runtime": _runtime_minutes(entry.get("duration", "")),
        "genres": [x.strip() for x in genre.split(",") if x.strip()],
        "poster_url": clean_text(entry.get("logo", "")),
        "source": "Anbieter / Xtream" if clean_text(entry.get("source_id", "")) or clean_text(entry.get("url", "")).startswith("xtream-") else "Playlist",
        "director": clean_text(entry.get("director", "")),
        "cast": clean_text(entry.get("cast", "")),
    }


def _merge_metadata(primary, fallback):
    result = dict(primary or {})
    fallback = fallback or {}
    for key in ("title", "overview", "release", "poster_url", "poster_path", "source", "director", "cast"):
        if not result.get(key) and fallback.get(key):
            result[key] = fallback.get(key)
    if not result.get("rating") and fallback.get("rating"):
        result["rating"] = fallback.get("rating")
    if not result.get("votes") and fallback.get("votes"):
        result["votes"] = fallback.get("votes")
    if not result.get("runtime") and fallback.get("runtime"):
        result["runtime"] = fallback.get("runtime")
    if not result.get("genres") and fallback.get("genres"):
        result["genres"] = fallback.get("genres")
    return result


def xtream_metadata_lookup(profile_id, entry, kind):
    basic = entry_basic_metadata(entry)
    meta = load_xtream_meta(profile_id)
    if meta.get("source") != "xtream" or kind not in ("movies", "series"):
        return basic
    sid = xtream_entry_source_id(entry)
    if not sid:
        return basic

    cache = read_json(METADATA_CACHE_FILE, {})
    if not isinstance(cache, dict):
        cache = {}
    key_raw = "xtream|%s|%s|%s" % (profile_id, kind, sid)
    key = hashlib.sha1(key_raw.encode("utf-8", "ignore")).hexdigest()
    cached = cache.get(key)
    if isinstance(cached, dict) and int(time.time()) - int(cached.get("cached_at", 0) or 0) < 7 * 86400:
        return _merge_metadata(cached, basic)

    action = "get_series_info" if kind == "series" else "get_vod_info"
    id_key = "series_id" if kind == "series" else "vod_id"
    raw = _xtream_fetch(meta, action, extra={id_key: sid}, timeout=18)
    info = raw.get("info", {}) if isinstance(raw, dict) and isinstance(raw.get("info"), dict) else {}
    movie_data = raw.get("movie_data", {}) if isinstance(raw, dict) and isinstance(raw.get("movie_data"), dict) else {}
    source = dict(movie_data)
    source.update(info)

    genre = clean_text(source.get("genre", ""))
    poster = first_text(source, "movie_image", "cover_big", "cover", "stream_icon", "poster", "image")
    if poster.startswith("//"):
        poster = (urlparse(clean_text(meta.get("base", ""))).scheme or "http") + ":" + poster
    elif poster.startswith("/"):
        poster = clean_text(meta.get("base", "")).rstrip("/") + poster
    release = clean_text(source.get("releasedate", source.get("releaseDate", source.get("release_date", source.get("year", "")))))
    result = {
        "cached_at": int(time.time()),
        "title": clean_text(source.get("name", source.get("o_name", basic.get("title", "")))) or basic.get("title", ""),
        "rating": _safe_float(source.get("rating", source.get("rating_5based", basic.get("rating", 0)))),
        "votes": 0,
        "overview": clean_text(source.get("plot", source.get("description", basic.get("overview", "")))),
        "release": release or basic.get("release", ""),
        "runtime": _runtime_minutes(source.get("duration", ""), source.get("duration_secs", 0)) or basic.get("runtime", 0),
        "genres": [x.strip() for x in genre.split(",") if x.strip()] or basic.get("genres", []),
        "poster_url": poster or basic.get("poster_url", ""),
        "source": "Anbieter / Xtream",
        "director": clean_text(source.get("director", basic.get("director", ""))),
        "cast": clean_text(source.get("cast", basic.get("cast", ""))),
    }
    cache[key] = result
    write_json(METADATA_CACHE_FILE, cache)
    return result


def best_metadata_lookup(profile_id, entry, kind):
    metadata = entry_basic_metadata(entry)
    provider_error = None
    if db_source_mode(profile_id) == "xtream":
        try:
            metadata = _merge_metadata(xtream_metadata_lookup(profile_id, entry, kind), metadata)
        except Exception as error:
            provider_error = error

    settings = load_global_settings()
    # TMDb is optional enrichment/fallback now, not a requirement for basic
    # posters and descriptions from an Xtream provider.
    needs_tmdb = not metadata.get("overview") or not (metadata.get("poster_url") or metadata.get("poster_path"))
    if clean_text(settings.get("tmdb_api_key", "")) and needs_tmdb:
        try:
            tmdb = tmdb_lookup(entry, kind)
            tmdb["source"] = "TMDb"
            metadata = _merge_metadata(metadata, tmdb)
            if metadata.get("source") == "Playlist":
                metadata["source"] = "TMDb"
        except Exception:
            pass
    if provider_error and not metadata.get("overview") and not metadata.get("poster_url"):
        metadata["provider_error"] = str(provider_error)
    return metadata


def _image_log(message):
    """Tiny rolling log for receiver-specific poster failures."""
    try:
        ensure_data_dir()
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = "%s %s\n" % (stamp, clean_text(message))
        try:
            if os.path.isfile(IMAGE_DEBUG_FILE) and os.path.getsize(IMAGE_DEBUG_FILE) > 128 * 1024:
                with open(IMAGE_DEBUG_FILE, "rb") as src:
                    tail = src.read()[-64 * 1024:]
                with open(IMAGE_DEBUG_FILE, "wb") as dst:
                    dst.write(tail)
        except Exception:
            pass
        with open(IMAGE_DEBUG_FILE, "a") as handle:
            handle.write(line)
    except Exception:
        pass


def _cached_image_path(folder, key):
    # Deliberately do not reuse old WebP/AVIF poster caches.  ePicLoad support
    # for those formats differs between OpenATV receiver generations.
    for ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp"):
        path = os.path.join(folder, key + ext)
        try:
            if os.path.isfile(path) and os.path.getsize(path) > 128:
                return path
        except Exception:
            pass
    return ""


def _image_format(raw, content_type=""):
    if not raw:
        return ""
    if raw.startswith(b"\x89PNG"):
        return "png"
    if raw.startswith(b"\xff\xd8"):
        return "jpg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if raw.startswith(b"BM"):
        return "bmp"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "webp"
    # ISO-BMFF AVIF/AVIS files normally expose ftyp in the first bytes.
    if len(raw) >= 16 and raw[4:8] == b"ftyp" and raw[8:12] in (b"avif", b"avis"):
        return "avif"
    ctype = clean_text(content_type).lower()
    if "jpeg" in ctype or "jpg" in ctype:
        return "jpg"
    if "png" in ctype:
        return "png"
    if "gif" in ctype:
        return "gif"
    if "bmp" in ctype:
        return "bmp"
    if "webp" in ctype:
        return "webp"
    if "avif" in ctype:
        return "avif"
    return ""


def _image_ext(raw, url="", content_type=""):
    fmt = _image_format(raw, content_type)
    if fmt in ("png", "gif", "bmp"):
        return "." + fmt
    if fmt == "jpg":
        return ".jpg"
    if fmt == "webp":
        return ".webp"
    if fmt == "avif":
        return ".avif"
    path = (urlparse(clean_text(url)).path or "").lower()
    for ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp"):
        if path.endswith(ext):
            return ext
    return ".jpg"


def _urlopen_compat(request, timeout):
    # Some older OpenATV Python builds have an outdated CA bundle while the
    # provider itself is still reachable.  Mirror the requests verify=False
    # behaviour as a compatibility fallback.
    if ssl is not None:
        try:
            context = ssl._create_unverified_context()
            return urlopen(request, timeout=timeout, context=context)
        except TypeError:
            pass
        except Exception:
            # Retry below without an explicit context for older Python APIs.
            pass
    return urlopen(request, timeout=timeout)


def _read_response_limited(response, max_bytes):
    chunks = []
    total = 0
    while True:
        chunk = response.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > int(max_bytes):
            return b""
        chunks.append(chunk)
    return b"".join(chunks)


def _download_image_external(url, headers, max_bytes):
    """Last-resort BusyBox wget/curl fallback used on minimal OpenATV images."""
    tmp = os.path.join(DATA_DIR, ".image_%s.part" % uuid.uuid4().hex)
    try:
        wget = shutil.which("wget") if hasattr(shutil, "which") else None
        curl = shutil.which("curl") if hasattr(shutil, "which") else None
        if wget:
            cmd = [wget, "-q", "--no-check-certificate", "--timeout=12", "--tries=1",
                   "--header=User-Agent: %s" % headers.get("User-Agent", "EpiMediaHub"),
                   "--header=Accept: %s" % headers.get("Accept", "image/jpeg,image/png"),
                   "-O", tmp, url]
        elif curl:
            cmd = [curl, "-k", "-L", "--max-time", "15", "--connect-timeout", "6", "-sS",
                   "-A", headers.get("User-Agent", "EpiMediaHub"),
                   "-H", "Accept: %s" % headers.get("Accept", "image/jpeg,image/png"),
                   "-o", tmp, url]
        else:
            return b""
        subprocess.check_call(cmd, stdout=open(os.devnull, "wb"), stderr=open(os.devnull, "wb"))
        if not os.path.isfile(tmp):
            return b""
        size = os.path.getsize(tmp)
        if size <= 0 or size > int(max_bytes):
            return b""
        with open(tmp, "rb") as handle:
            return handle.read()
    except Exception:
        return b""
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def _convert_unsupported_image(raw, fmt):
    """Best-effort WebP/AVIF -> baseline JPEG without adding a hard dependency."""
    if fmt not in ("webp", "avif"):
        return raw, fmt
    try:
        from PIL import Image
        try:
            from io import BytesIO
        except ImportError:
            from cStringIO import StringIO as BytesIO
        src = BytesIO(raw)
        image = Image.open(src)
        if image.mode not in ("RGB", "L"):
            background = Image.new("RGB", image.size, (0, 0, 0))
            if image.mode == "RGBA":
                background.paste(image, mask=image.split()[-1])
            else:
                background.paste(image.convert("RGB"))
            image = background
        elif image.mode == "L":
            image = image.convert("RGB")
        out = BytesIO()
        image.save(out, format="JPEG", quality=90, optimize=False, progressive=False)
        return out.getvalue(), "jpg"
    except Exception as error:
        _image_log("unsupported %s; conversion unavailable: %s" % (fmt, error))
        return b"", fmt


def download_image_cached(url, folder, key=None, timeout=12, max_bytes=6 * 1024 * 1024):
    url = clean_text(url)
    if not url.startswith(("http://", "https://")):
        return ""
    ensure_data_dir()
    key = key or hashlib.sha1(url.encode("utf-8", "ignore")).hexdigest()
    cached = _cached_image_path(folder, key)
    if cached:
        return cached

    # IMPORTANT: Do not advertise AVIF/WebP. Several OpenATV/ePicLoad builds
    # cannot decode them. Most CDNs will then send JPEG/PNG instead.
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Enigma2) EpiMediaHub/%s" % PLUGIN_VERSION,
        "Accept": "image/jpeg,image/png,image/gif,image/bmp,image/*;q=0.7,*/*;q=0.2",
        "Accept-Encoding": "identity",
        "Connection": "close",
    }
    raw = b""
    content_type = ""
    backend = ""

    if requests is not None:
        try:
            response = requests.get(url, headers=headers, timeout=(6, max(8, int(timeout))),
                                    verify=False, allow_redirects=True, stream=True)
            response.raise_for_status()
            content_type = clean_text(response.headers.get("Content-Type", ""))
            chunks = []
            total = 0
            for chunk in response.iter_content(65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > int(max_bytes):
                    chunks = []
                    break
                chunks.append(chunk)
            try:
                response.close()
            except Exception:
                pass
            raw = b"".join(chunks)
            backend = "requests"
        except Exception as error:
            _image_log("requests failed %s: %s" % (url[:180], error))
            raw = b""

    if not raw:
        try:
            response = _urlopen_compat(Request(url, headers=headers), timeout)
            try:
                content_type = clean_text(response.headers.get("Content-Type", ""))
                raw = _read_response_limited(response, max_bytes)
            finally:
                try:
                    response.close()
                except Exception:
                    pass
            backend = "urllib"
        except Exception as error:
            _image_log("urllib failed %s: %s" % (url[:180], error))
            raw = b""

    if not raw:
        raw = _download_image_external(url, headers, max_bytes)
        if raw:
            backend = "external"

    if not raw:
        _image_log("download failed %s" % url[:200])
        return ""

    fmt = _image_format(raw, content_type)
    if fmt in ("webp", "avif"):
        raw, fmt = _convert_unsupported_image(raw, fmt)
    if not raw or fmt not in ("jpg", "png", "gif", "bmp"):
        _image_log("unsupported/invalid image backend=%s type=%s ctype=%s url=%s" %
                   (backend, fmt or "unknown", content_type, url[:180]))
        return ""

    ext = ".jpg" if fmt == "jpg" else "." + fmt
    target = os.path.join(folder, key + ext)
    tmp_target = target + ".part"
    try:
        with open(tmp_target, "wb") as handle:
            handle.write(raw)
        os.replace(tmp_target, target) if hasattr(os, "replace") else os.rename(tmp_target, target)
        _image_log("ok backend=%s type=%s bytes=%d file=%s" % (backend, fmt, len(raw), os.path.basename(target)))
        return target
    except Exception as error:
        _image_log("cache write failed %s: %s" % (target, error))
        try:
            if os.path.exists(tmp_target):
                os.remove(tmp_target)
        except Exception:
            pass
        return ""


def cached_metadata_poster_file(metadata):
    metadata = metadata or {}
    direct = clean_text(metadata.get("poster_url", ""))
    if direct.startswith(("http://", "https://")):
        key = hashlib.sha1(direct.encode("utf-8", "ignore")).hexdigest()
        cached = _cached_image_path(POSTER_CACHE_DIR, key)
        if cached:
            return cached
    poster_path = clean_text(metadata.get("poster_path", ""))
    if poster_path:
        key = hashlib.sha1(poster_path.encode("utf-8", "ignore")).hexdigest()
        cached = _cached_image_path(POSTER_CACHE_DIR, key)
        if cached:
            return cached
    return ""


def metadata_poster_file(metadata):
    metadata = metadata or {}
    cached = cached_metadata_poster_file(metadata)
    if cached:
        return cached
    direct = clean_text(metadata.get("poster_url", ""))
    if direct.startswith(("http://", "https://")):
        key = hashlib.sha1(direct.encode("utf-8", "ignore")).hexdigest()
        path = download_image_cached(direct, POSTER_CACHE_DIR, key=key, timeout=12)
        if path:
            return path
    return tmdb_poster_file(metadata)


def _picon_cache_key(entry):
    direct = clean_text((entry or {}).get("logo", ""))
    if not direct:
        return ""
    return hashlib.sha1(direct.encode("utf-8", "ignore")).hexdigest()


def picon_local_file(entry):
    key = _picon_cache_key(entry)
    if not key:
        return ""
    for ext in (".png", ".jpg"):
        path = os.path.join(PICON_CACHE_DIR, key + ext)
        try:
            if os.path.isfile(path) and os.path.getsize(path) > 64:
                return path
        except Exception:
            pass
    return ""


def ensure_picon_file(entry):
    cached = picon_local_file(entry)
    if cached:
        return cached
    direct = clean_text((entry or {}).get("logo", ""))
    if not direct.startswith(("http://", "https://")):
        return ""
    ensure_data_dir()
    try:
        response = urlopen(Request(direct, headers={"User-Agent": "EpiMediaHub/%s" % PLUGIN_VERSION}), timeout=8)
        try:
            raw = response.read(1024 * 1024 + 1)
        finally:
            response.close()
        if not raw or len(raw) > 1024 * 1024:
            return ""
        if raw.startswith(b"\x89PNG"):
            ext = ".png"
        elif raw.startswith(b"\xff\xd8"):
            ext = ".jpg"
        else:
            return ""
        target = os.path.join(PICON_CACHE_DIR, _picon_cache_key(entry) + ext)
        with open(target, "wb") as handle:
            handle.write(raw)
        return target
    except Exception:
        return ""


def picon_pixmap(entry):
    path = picon_local_file(entry)
    if not path or LoadPixmap is None:
        return None
    cached = _PICON_PIXMAP_CACHE.get(path)
    if cached is not None:
        return cached
    try:
        pix = LoadPixmap(path)
        if pix is not None:
            if len(_PICON_PIXMAP_CACHE) > 160:
                _PICON_PIXMAP_CACHE.clear()
            _PICON_PIXMAP_CACHE[path] = pix
        return pix
    except Exception:
        return None


def first_cached_live_entry(profile_id, group_name=None):
    """Return one cached live entry without forcing a provider/API download."""
    if sqlite3 is not None and playlist_db_ready(profile_id):
        try:
            connection = _db_connect(profile_id)
            params = ["live"]
            where = "kind=? AND COALESCE(logo,'')<>''"
            if group_name and group_name != "__all__":
                where += " AND group_name=?"
                params.append(group_name)
            row = connection.execute(
                "SELECT ord,kind,title,group_name,logo,tvg_id,tvg_name,url,source_id,tv_archive,tv_archive_duration FROM entries WHERE %s ORDER BY ord LIMIT 1" % where,
                tuple(params)
            ).fetchone()
            connection.close()
            if row:
                return _row_to_entry(row)
        except Exception:
            pass
    if db_source_mode(profile_id) == "xtream" and sqlite3 is None:
        meta = load_xtream_meta(profile_id)
        names = []
        if group_name and group_name != "__all__":
            names = [group_name]
        else:
            names = list(meta.get("loaded_categories", {}).get("live", []))
        for name in names:
            cached = read_json(xtream_category_cache_path(profile_id, "live", name), [])
            if not isinstance(cached, list):
                continue
            for entry in cached:
                if isinstance(entry, dict) and clean_text(entry.get("logo", "")):
                    return entry
    return None


def _decode_xtream_epg_text(value):
    value = clean_text(value)
    if not value:
        return ""
    # Many Xtream panels base64-encode EPG title/description; others return
    # plain UTF-8. Decode only when the result looks like printable text.
    try:
        if len(value) >= 8 and re.match(r"^[A-Za-z0-9+/=]+$", value):
            padded = value + ("=" * ((4 - len(value) % 4) % 4))
            decoded = base64.b64decode(padded).decode("utf-8", "ignore").strip()
            if decoded:
                printable = sum(1 for ch in decoded if ch.isprintable() or ch in "\r\n\t")
                if float(printable) / float(max(1, len(decoded))) > 0.9:
                    return decoded
    except Exception:
        pass
    return value


def _xtream_epg_time(item, timestamp_key, text_key):
    try:
        value = item.get(timestamp_key)
        if value not in (None, ""):
            return int(float(value))
    except Exception:
        pass
    value = clean_text(item.get(text_key, ""))
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return int(time.mktime(time.strptime(value[:19], fmt)))
        except Exception:
            pass
    return 0


def _xtream_epg_cache_key(profile_id, entry):
    return "%s|%s" % (profile_id, xtream_entry_source_id(entry) or clean_text(entry.get("url", "")))


def xtream_epg_cache_fresh(profile_id, entry, max_age=180):
    cached = _XTREAM_EPG_MEMORY_CACHE.get(_xtream_epg_cache_key(profile_id, entry))
    return bool(cached and (int(time.time()) - int(cached[0])) < max_age)


def xtream_short_epg(profile_id, entry, limit=20, force=False):
    key = _xtream_epg_cache_key(profile_id, entry)
    cached = _XTREAM_EPG_MEMORY_CACHE.get(key)
    if not force and cached and int(time.time()) - int(cached[0]) < 180:
        return list(cached[1])
    meta = load_xtream_meta(profile_id)
    sid = xtream_entry_source_id(entry)
    if meta.get("source") != "xtream" or not sid:
        return []
    raw = _xtream_fetch(meta, "get_short_epg", extra={"stream_id": sid, "limit": int(limit)}, timeout=12)
    listings = []
    if isinstance(raw, dict):
        listings = raw.get("epg_listings", raw.get("listings", []))
    if not isinstance(listings, list):
        listings = []
    result = []
    for item in listings:
        if not isinstance(item, dict):
            continue
        start = _xtream_epg_time(item, "start_timestamp", "start")
        stop = _xtream_epg_time(item, "stop_timestamp", "end")
        if not stop:
            stop = _xtream_epg_time(item, "end_timestamp", "end")
        if not start:
            continue
        if not stop:
            stop = start + 3600
        result.append({
            "start": start,
            "stop": stop,
            "title": _decode_xtream_epg_text(item.get("title", "")) or "Ohne Titel",
            "desc": _decode_xtream_epg_text(item.get("description", item.get("desc", ""))),
        })
    result.sort(key=lambda x: int(x.get("start", 0)))
    _XTREAM_EPG_MEMORY_CACHE[key] = (int(time.time()), result)
    return result


def _xtream_parse_epg_payload(raw):
    listings = []
    if isinstance(raw, dict):
        listings = raw.get("epg_listings", raw.get("listings", []))
    if not isinstance(listings, list):
        listings = []
    result = []
    for item in listings:
        if not isinstance(item, dict):
            continue
        start = _xtream_epg_time(item, "start_timestamp", "start")
        stop = _xtream_epg_time(item, "stop_timestamp", "end")
        if not stop:
            stop = _xtream_epg_time(item, "end_timestamp", "end")
        if not start:
            continue
        if not stop:
            stop = start + 3600
        archive_value = item.get("has_archive", None)
        try:
            archive_value = int(archive_value) if archive_value not in (None, "") else None
        except Exception:
            archive_value = None
        result.append({
            "start": start,
            "stop": stop,
            "title": _decode_xtream_epg_text(item.get("title", "")) or "Ohne Titel",
            "desc": _decode_xtream_epg_text(item.get("description", item.get("desc", ""))),
            "has_archive": archive_value,
        })
    result.sort(key=lambda x: int(x.get("start", 0)))
    return result


def xtream_full_epg(profile_id, entry, force=False):
    key = _xtream_epg_cache_key(profile_id, entry)
    cached = _XTREAM_FULL_EPG_MEMORY_CACHE.get(key)
    if not force and cached and int(time.time()) - int(cached[0]) < 300:
        return list(cached[1])
    meta = load_xtream_meta(profile_id)
    sid = xtream_entry_source_id(entry)
    if meta.get("source") != "xtream" or not sid:
        return []
    raw = _xtream_fetch(meta, "get_simple_data_table", extra={"stream_id": sid}, timeout=15)
    result = _xtream_parse_epg_payload(raw)
    if not result:
        try:
            result = xtream_short_epg(profile_id, entry, limit=40, force=force)
        except Exception:
            result = []
    _XTREAM_FULL_EPG_MEMORY_CACHE[key] = (int(time.time()), result)
    return list(result)


def epg_grid_items_for_entry(profile_id, entry):
    key = _xtream_epg_cache_key(profile_id, entry)
    cached = _XTREAM_FULL_EPG_MEMORY_CACHE.get(key)
    if cached:
        return list(cached[1])
    return epg_programmes_for_entry(profile_id, entry)


def entry_catchup_days(entry):
    try:
        enabled = int((entry or {}).get("tv_archive", 0) or 0) == 1
    except Exception:
        enabled = False
    if not enabled:
        return 0
    try:
        days = int((entry or {}).get("tv_archive_duration", 0) or 0)
    except Exception:
        days = 0
    return max(1, days)


def xtream_catchup_available(profile_id, entry, event):
    if db_source_mode(profile_id) != "xtream" or entry_catchup_days(entry) <= 0:
        return False
    if not xtream_entry_source_id(entry):
        return False
    now = int(time.time())
    try:
        start = int(event.get("start", 0) or 0)
        stop = int(event.get("stop", 0) or 0)
    except Exception:
        return False
    if start <= 0 or start >= now or stop <= start:
        return False
    archive_flag = event.get("has_archive", None)
    if archive_flag not in (None, ""):
        try:
            if int(archive_flag) != 1:
                return False
        except Exception:
            pass
    oldest = now - (entry_catchup_days(entry) * 86400) - 7200
    return start >= oldest


def _xtream_server_offset(meta):
    try:
        if "server_utc_offset" in meta:
            return int(meta.get("server_utc_offset", 0) or 0)
    except Exception:
        pass
    try:
        data = _xtream_fetch(meta, "", timeout=8)
        server = data.get("server_info", {}) if isinstance(data, dict) else {}
        timestamp = int(server.get("timestamp_now", 0) or 0)
        time_now = clean_text(server.get("time_now", ""))
        if timestamp and time_now:
            shown = calendar.timegm(time.strptime(time_now[:19], "%Y-%m-%d %H:%M:%S"))
            offset = int(shown - timestamp)
            if abs(offset) <= 15 * 3600:
                meta["server_utc_offset"] = offset
                save_xtream_meta(meta.get("profile_id", ""), meta) if meta.get("profile_id") else None
                return offset
    except Exception:
        pass
    return None


def xtream_catchup_url(profile_id, entry, event):
    if not xtream_catchup_available(profile_id, entry, event):
        return ""
    meta = load_xtream_meta(profile_id)
    sid = xtream_entry_source_id(entry)
    if meta.get("source") != "xtream" or not sid:
        return ""
    try:
        start = int(event.get("start", 0))
        stop = int(event.get("stop", 0))
    except Exception:
        return ""
    duration = max(1, int((max(start + 60, stop) - start + 59) // 60))
    offset = _xtream_server_offset(meta)
    if offset is None:
        stamp = time.localtime(start)
    else:
        stamp = time.gmtime(start + offset)
    start_text = time.strftime("%Y-%m-%d:%H-%M", stamp)
    base = clean_text(meta.get("base", "")).rstrip("/")
    user = quote(str(meta.get("username", "")), safe="")
    password = quote(str(meta.get("password", "")), safe="")
    ext = "m3u8" if clean_text(meta.get("output", "ts")).lower() == "m3u8" else "ts"
    return "%s/timeshift/%s/%s/%d/%s/%s.%s" % (base, user, password, duration, start_text, quote(str(sid), safe=""), ext)

# -------------------- EPG --------------------

def derive_xtream_epg_url(m3u_url):
    try:
        parsed = urlparse(m3u_url)
        query = parse_qs(parsed.query)
        username = query.get("username", [""])[0]
        password = query.get("password", [""])[0]
        if not parsed.scheme or not parsed.netloc or not username or not password:
            return ""
        return "%s://%s/xmltv.php?%s" % (
            parsed.scheme, parsed.netloc, urlencode({"username": username, "password": password})
        )
    except Exception:
        return ""


def profile_epg_url(profile):
    configured = clean_text(profile.get("epg_url", "")) or clean_text(profile.get("epg_url_auto", ""))
    if configured:
        return configured
    derived = derive_xtream_epg_url(profile.get("m3u_url", ""))
    if derived:
        return derived
    try:
        meta = load_xtream_meta(profile.get("id", ""))
        if meta.get("source") == "xtream" and meta.get("base") and meta.get("username") and meta.get("password"):
            return "%s/xmltv.php?%s" % (
                meta.get("base", "").rstrip("/"),
                urlencode({"username": meta.get("username", ""), "password": meta.get("password", "")})
            )
    except Exception:
        pass
    return ""


def parse_xmltv_time(value):
    value = clean_text(value)
    match = re.match(r"^(\d{14})(?:\s*([+-])(\d{2})(\d{2}))?", value)
    if not match:
        return 0
    try:
        base = time.strptime(match.group(1), "%Y%m%d%H%M%S")
        stamp = calendar.timegm(base)
        if match.group(2):
            offset = (int(match.group(3)) * 60 + int(match.group(4))) * 60
            if match.group(2) == "+":
                stamp -= offset
            else:
                stamp += offset
        return int(stamp)
    except Exception:
        return 0


def child_text(elem, tag):
    for child in list(elem):
        if child.tag.split("}")[-1] == tag:
            return clean_text(child.text)
    return ""


def normalize_channel(value):
    value = clean_text(value).lower()
    value = re.sub(r"\s+", " ", value)
    return value


def build_epg_cache(profile_id):
    path = epg_xml_path(profile_id)
    if not os.path.isfile(path):
        empty = {"updated": int(time.time()), "aliases": {}, "programmes": {}}
        write_json(epg_quick_cache_path(profile_id), empty)
        return empty
    now = int(time.time())
    min_time = now - 6 * 3600
    max_time = now + 48 * 3600
    quick_min = now - 2 * 3600
    quick_max = now + 12 * 3600
    aliases = {}
    programmes = {}
    try:
        for event, elem in ET.iterparse(path, events=("end",)):
            tag = elem.tag.split("}")[-1]
            if tag == "channel":
                channel_id = clean_text(elem.attrib.get("id", ""))
                for child in list(elem):
                    if child.tag.split("}")[-1] == "display-name" and clean_text(child.text):
                        aliases[normalize_channel(child.text)] = channel_id
                elem.clear()
            elif tag == "programme":
                start = parse_xmltv_time(elem.attrib.get("start", ""))
                stop = parse_xmltv_time(elem.attrib.get("stop", ""))
                if stop >= min_time and start <= max_time:
                    channel = clean_text(elem.attrib.get("channel", ""))
                    if channel:
                        programmes.setdefault(channel, []).append({
                            "start": start,
                            "stop": stop,
                            "title": child_text(elem, "title") or "Ohne Titel",
                            "desc": child_text(elem, "desc"),
                        })
                elem.clear()
        for channel in programmes:
            programmes[channel].sort(key=lambda item: item.get("start", 0))
    except Exception:
        empty = {"updated": int(time.time()), "aliases": {}, "programmes": {}}
        write_json(epg_quick_cache_path(profile_id), empty)
        return empty

    cache = {"updated": int(time.time()), "aliases": aliases, "programmes": programmes}
    write_json(epg_cache_path(profile_id), cache)

    # Lightweight cache for the channel list.  Keeping only the nearby window
    # avoids loading the much larger 48h EPG JSON merely to paint Now/Next rows.
    quick_programmes = {}
    for channel, items in programmes.items():
        nearby = [item for item in items if int(item.get("stop", 0)) >= quick_min and int(item.get("start", 0)) <= quick_max]
        if nearby:
            quick_programmes[channel] = nearby[:24]
    quick_cache = {"updated": int(time.time()), "aliases": aliases, "programmes": quick_programmes}
    write_json(epg_quick_cache_path(profile_id), quick_cache)
    _EPG_MEMORY_CACHE.pop(profile_id, None)
    _EPG_QUICK_MEMORY_CACHE.pop(profile_id, None)
    return cache


def download_epg(profile):
    url = profile_epg_url(profile)
    if not url:
        raise Exception("Keine EPG/XMLTV-Quelle gefunden.")
    ensure_data_dir()
    target = epg_xml_path(profile["id"])
    temp = target + ".download"
    try:
        request = Request(url, headers={"User-Agent": "EpiMediaHub/%s" % PLUGIN_VERSION, "Accept-Encoding": "gzip"})
        response = urlopen(request, timeout=40)
        try:
            with open(temp, "wb") as handle:
                while True:
                    chunk = response.read(512 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
        finally:
            response.close()
        if not os.path.isfile(temp) or os.path.getsize(temp) <= 0:
            raise Exception("EPG-Datei ist leer.")
        with open(temp, "rb") as handle:
            magic = handle.read(2)
        if magic == b"\x1f\x8b" or url.lower().endswith(".gz"):
            with gzip.open(temp, "rb") as source, open(target, "wb") as dest:
                shutil.copyfileobj(source, dest, 1024 * 1024)
            os.remove(temp)
        else:
            os.replace(temp, target)
    finally:
        try:
            if os.path.exists(temp):
                os.remove(temp)
        except Exception:
            pass

    cache = build_epg_cache(profile["id"])
    profile["epg_last_update"] = time.strftime("%d.%m.%Y %H:%M")
    update_profile(profile)
    return sum(len(items) for items in cache.get("programmes", {}).values())


def auto_epg_due(profile_id, max_age=6 * 3600):
    if not profile_id:
        return False
    path = epg_quick_cache_path(profile_id)
    if not os.path.isfile(path):
        path = epg_cache_path(profile_id)
    try:
        return (not os.path.isfile(path)) or (time.time() - os.path.getmtime(path) >= max_age)
    except Exception:
        return True


def epg_cache_available(profile_id):
    """Cheap readiness check used on home screen; never parse the full EPG JSON."""
    if not profile_id:
        return False
    for path in (epg_quick_cache_path(profile_id), epg_cache_path(profile_id)):
        try:
            if os.path.isfile(path) and os.path.getsize(path) > 32:
                return True
        except Exception:
            pass
    return False


def load_epg_cache(profile_id):
    if not profile_id:
        return {}
    path = epg_cache_path(profile_id)
    try:
        mtime = os.path.getmtime(path)
    except Exception:
        mtime = 0
    cached = _EPG_MEMORY_CACHE.get(profile_id)
    if cached and cached[0] == mtime:
        return cached[1]
    data = read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    _EPG_MEMORY_CACHE[profile_id] = (mtime, data)
    return data


def load_epg_quick_cache(profile_id):
    if not profile_id:
        return {}
    path = epg_quick_cache_path(profile_id)
    try:
        mtime = os.path.getmtime(path)
    except Exception:
        return {}
    cached = _EPG_QUICK_MEMORY_CACHE.get(profile_id)
    if cached and cached[0] == mtime:
        return cached[1]
    data = read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    _EPG_QUICK_MEMORY_CACHE[profile_id] = (mtime, data)
    return data


def _epg_items_from_cache(cache, entry):
    programmes = cache.get("programmes", {}) if isinstance(cache, dict) else {}
    aliases = cache.get("aliases", {}) if isinstance(cache, dict) else {}
    channel_id = clean_text(entry.get("tvg_id", ""))
    if channel_id and channel_id in programmes:
        return programmes.get(channel_id, [])
    for candidate in (entry.get("tvg_name", ""), entry.get("title", "")):
        normalized = normalize_channel(candidate)
        mapped = aliases.get(normalized)
        if mapped and mapped in programmes:
            return programmes.get(mapped, [])
    return []


def epg_programmes_for_entry(profile_id, entry):
    xtream_cached = _XTREAM_EPG_MEMORY_CACHE.get(_xtream_epg_cache_key(profile_id, entry))
    if xtream_cached:
        return list(xtream_cached[1])
    return _epg_items_from_cache(load_epg_cache(profile_id), entry)


def now_next_from_items(items):
    now = int(time.time())
    current = None
    next_item = None
    for item in items or []:
        start = int(item.get("start", 0))
        stop = int(item.get("stop", 0))
        if start <= now < stop:
            current = item
        elif start > now:
            next_item = item
            break
    return current, next_item


def epg_now_next_quick(profile_id, entry):
    xtream_cached = _XTREAM_EPG_MEMORY_CACHE.get(_xtream_epg_cache_key(profile_id, entry))
    if xtream_cached:
        return now_next_from_items(xtream_cached[1])
    quick = load_epg_quick_cache(profile_id)
    if quick:
        return now_next_from_items(_epg_items_from_cache(quick, entry))
    return None, None


def epg_now_next(profile_id, entry):
    current, next_item = epg_now_next_quick(profile_id, entry)
    if current or next_item or epg_cache_available(profile_id):
        return current, next_item
    return now_next_from_items(epg_programmes_for_entry(profile_id, entry))


def format_clock(stamp):
    try:
        return time.strftime("%H:%M", time.localtime(int(stamp)))
    except Exception:
        return "--:--"



def _record_margin_seconds(name):
    try:
        section = getattr(config, "recording", None)
        value = getattr(section, name, None)
        return max(0, int(getattr(value, "value", 0) or 0)) * 60
    except Exception:
        return 0


def epimedia_schedule_timer(session, entry, event, justplay=False):
    if RecordTimerEntry is None or ServiceReference is None or not hasattr(session.nav, "RecordTimer"):
        return False, "Timer-Funktion ist auf diesem Image nicht verfügbar."
    try:
        start = int(event.get("start", 0) or 0)
        stop = int(event.get("stop", 0) or 0)
    except Exception:
        return False, "Ungültige EPG-Zeit."
    now = int(time.time())
    if stop <= now:
        return False, "Diese Sendung ist bereits beendet. Für vergangene Sendungen Replay verwenden."
    if justplay and start <= now + 10:
        return False, "Eine Erinnerung kann nur für eine zukünftige Sendung gesetzt werden."
    before = 0 if justplay else _record_margin_seconds("margin_before")
    after = 0 if justplay else _record_margin_seconds("margin_after")
    begin = max(now + 5, start - before)
    end = max(begin + 60, stop + after)
    url = clean_text((entry or {}).get("url", ""))
    if not url:
        return False, "Sender-URL fehlt."
    try:
        ref = eServiceReference(4097, 0, url)
        ref.setName(clean_text(entry.get("title", "Epi MediaHub")))
        service_ref = ServiceReference(ref)
        title = clean_text(event.get("title", "")) or clean_text(entry.get("title", "Sendung"))
        desc = clean_text(event.get("desc", ""))
        kwargs = {"justplay": bool(justplay)}
        if AFTEREVENT is not None:
            try:
                kwargs["afterEvent"] = AFTEREVENT.AUTO
            except Exception:
                pass
        try:
            timer = RecordTimerEntry(service_ref, begin, end, title, desc, 0, **kwargs)
        except TypeError:
            timer = RecordTimerEntry(service_ref, begin, end, title, desc, 0)
            timer.justplay = bool(justplay)
        conflicts = session.nav.RecordTimer.record(timer)
        if conflicts:
            return False, "Timer-Konflikt: Die Sendung überschneidet sich mit einer bestehenden Aufnahme."
        return True, ("Erinnerung gesetzt." if justplay else "Aufnahme programmiert.")
    except Exception as error:
        return False, "Timer konnte nicht angelegt werden: %s" % clean_text(error)

# -------------------- TMDb metadata --------------------

def clean_media_title(title, kind):
    text = clean_text(title)
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"\([^)]*(?:4k|uhd|fhd|hd|multi|german|deutsch|ita|eng)[^)]*\)", " ", text, flags=re.I)
    if kind == "series":
        text = re.sub(r"\bS\d{1,2}\s*E\d{1,3}\b.*$", "", text, flags=re.I)
        text = re.sub(r"\b\d{1,2}x\d{1,3}\b.*$", "", text, flags=re.I)
    text = re.sub(r"\b(?:2160p|1080p|720p|4K|UHD|FHD|HD|HEVC|H265|H264|MULTI)\b", " ", text, flags=re.I)
    text = re.sub(r"[_\.]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -|:")
    return text


def extract_year(title):
    match = re.search(r"\b((?:19|20)\d{2})\b", title or "")
    return match.group(1) if match else ""


def tmdb_request(path, params, settings):
    key = clean_text(settings.get("tmdb_api_key", ""))
    if not key:
        raise Exception("Noch kein TMDb API-Key eingerichtet.")
    params = dict(params or {})
    headers = {"User-Agent": "EpiMediaHub/%s" % PLUGIN_VERSION, "Accept": "application/json"}
    if key.startswith("eyJ"):
        headers["Authorization"] = "Bearer %s" % key
    else:
        params["api_key"] = key
    query = urlencode(params)
    url = "https://api.themoviedb.org/3%s%s%s" % (path, "?" if query else "", query)
    response = urlopen(Request(url, headers=headers), timeout=15)
    raw = response.read()
    response.close()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "ignore")
    return json.loads(raw)



def _saga_category_clean_name(value):
    """Extract a franchise/search term from Saga/Collection category names."""
    text = clean_text(value)
    if not text or text == "__all__":
        return ""
    text = text.replace("_", " ")
    # Typical provider variants: "Saga Harry Potter", "SAGA | Rocky",
    # "[SAGA] Fast & Furious", "Collection - Mission Impossible".
    text = re.sub(
        r"^[\s\[\(\{]*(?:saga|collection|collections|kollektion|sammlung|franchise|filmreihe|reihe)[\s\]\)\}]*[:\-|>]*\s*",
        "", text, flags=re.I
    )
    for _i in range(3):
        text = re.sub(r"^\s*(?:DE|GER|GERMAN|EN|ENG|IT|ITA|TR|TUR|VIP|VOD|4K|UHD|FHD|HD|MOVIES?|FILME?)\s*[|:\->]+\s*", "", text, flags=re.I)
        text = re.sub(r"\s*[|:\->]+\s*(?:DE|GER|GERMAN|EN|ENG|IT|ITA|TR|TUR|VIP|VOD|4K|UHD|FHD|HD|MOVIES?|FILME?)\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+\((?:saga|collection|filmreihe|franchise)\)\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -|:[](){}")
    return text


def _looks_like_saga_category(value):
    raw = clean_text(value)
    if not raw or raw == "__all__":
        return False
    # "Saga" is the primary convention used by providers, but accepting a few
    # common synonyms makes the same feature useful across different lists.
    return bool(re.search(
        r"^[\s\[\(\{]*(?:saga|collection|collections|kollektion|sammlung|franchise|filmreihe|reihe)(?:[\s\]\)\}]+|\s*[:\-|>])",
        raw,
        flags=re.I
    )) and bool(_saga_category_clean_name(raw))


def _saga_name_norm(value):
    text = clean_text(value).lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    # Normalise a few provider-friendly spellings without destroying unicode.
    text = text.replace("&", " and ")
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def _saga_name_match_score(wanted, candidate):
    wanted_norm = _saga_name_norm(wanted)
    candidate_norm = _saga_name_norm(candidate)
    if not wanted_norm or not candidate_norm:
        return 0
    if wanted_norm == candidate_norm:
        return 100
    if wanted_norm in candidate_norm or candidate_norm in wanted_norm:
        return 88
    w = set(wanted_norm.split())
    c = set(candidate_norm.split())
    if not w or not c:
        return 0
    common = len(w & c)
    if common == len(w) and common >= 2:
        return 84
    if common >= 2:
        return 55 + min(20, common * 5)
    return 0


def _saga_cache_key(value):
    name = _saga_category_clean_name(value)
    return hashlib.sha1(_saga_name_norm(name).encode("utf-8", "ignore")).hexdigest()


SAGA_CACHE_VERSION = 1


def saga_category_cache_record(value):
    if not _looks_like_saga_category(value):
        return True, ""
    cache = read_json(SAGA_CACHE_FILE, {})
    if not isinstance(cache, dict):
        return False, ""
    record = cache.get(_saga_cache_key(value))
    if not isinstance(record, dict):
        return False, ""
    if int(record.get("cache_version", 0) or 0) != SAGA_CACHE_VERSION:
        return False, ""
    age = int(time.time()) - int(record.get("cached_at", 0) or 0)
    positive = bool(record.get("image_key") or record.get("image_url") or record.get("file_path"))
    max_age = 45 * 86400 if positive else 2 * 86400
    if age < 0 or age >= max_age:
        return False, ""
    image_key = clean_text(record.get("image_key", ""))
    if not image_key:
        seed = clean_text(record.get("file_path", "")) or clean_text(record.get("image_url", ""))
        if seed:
            image_key = hashlib.sha1(seed.encode("utf-8", "ignore")).hexdigest()
    if not image_key:
        return True, ""
    return True, _cached_image_path(SAGA_CACHE_DIR, image_key)


def _save_saga_cache_record(value, record):
    cache = read_json(SAGA_CACHE_FILE, {})
    if not isinstance(cache, dict):
        cache = {}
    record = dict(record or {})
    record["cached_at"] = int(time.time())
    record["cache_version"] = SAGA_CACHE_VERSION
    cache[_saga_cache_key(value)] = record
    write_json(SAGA_CACHE_FILE, cache)


def _tmdb_saga_category_image(value, settings):
    """Prefer TMDb collection artwork. A configured TMDb key enables this path."""
    if not clean_text(settings.get("tmdb_api_key", "")):
        return ""
    query_name = _saga_category_clean_name(value)
    if not query_name:
        return ""
    try:
        result = tmdb_request(
            "/search/collection",
            {"query": query_name, "language": settings.get("metadata_language", "de-DE")},
            settings
        )
        hits = result.get("results", []) if isinstance(result, dict) else []
        ranked = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            title = clean_text(hit.get("name", "")) or clean_text(hit.get("title", ""))
            score = _saga_name_match_score(query_name, title)
            if hit.get("poster_path") or hit.get("backdrop_path"):
                score += 5
            ranked.append((score, hit))
        ranked.sort(key=lambda item: item[0], reverse=True)
        hit = ranked[0][1] if ranked and ranked[0][0] >= 72 else None
        if not isinstance(hit, dict):
            return ""

        collection_id = hit.get("id")
        # Some TMDb responses expose collection logos through the images
        # endpoint. Prefer a transparent logo when available, then artwork.
        file_path = ""
        image_kind = ""
        if collection_id:
            try:
                images = tmdb_request("/collection/%s/images" % collection_id, {}, settings)
                logos = images.get("logos", []) if isinstance(images, dict) else []
                language = clean_text(settings.get("metadata_language", "de-DE")).split("-")[0].lower()
                preferred = []
                for logo in logos:
                    if not isinstance(logo, dict) or not logo.get("file_path"):
                        continue
                    lang = clean_text(logo.get("iso_639_1", "")).lower()
                    rank = 3 if lang == language else (2 if lang == "en" else (1 if not lang else 0))
                    preferred.append((rank, float(logo.get("vote_average", 0) or 0), logo))
                preferred.sort(key=lambda item: (item[0], item[1]), reverse=True)
                if preferred:
                    file_path = clean_text(preferred[0][2].get("file_path", ""))
                    image_kind = "logo"
            except Exception:
                pass

        if not file_path:
            file_path = clean_text(hit.get("backdrop_path", "")) or clean_text(hit.get("poster_path", ""))
            image_kind = "artwork"
        if not file_path:
            return ""
        image_key = hashlib.sha1(file_path.encode("utf-8", "ignore")).hexdigest()
        image_url = "https://image.tmdb.org/t/p/w500%s" % file_path
        image_path = download_image_cached(image_url, SAGA_CACHE_DIR, key=image_key, timeout=12, max_bytes=5 * 1024 * 1024)
        if image_path:
            _save_saga_cache_record(value, {
                "query": query_name,
                "name": clean_text(hit.get("name", query_name)),
                "file_path": file_path,
                "image_url": image_url,
                "image_key": image_key,
                "tmdb_id": collection_id,
                "image_kind": image_kind,
                "source": "tmdb-collection",
            })
            return image_path
    except Exception:
        pass
    return ""


def _wikipedia_saga_category_image(value, settings):
    """Key-free fallback for franchise/category artwork via Wikipedia thumbnails."""
    query_name = _saga_category_clean_name(value)
    wanted = _saga_name_norm(query_name)
    if not wanted:
        return ""
    metadata_lang = clean_text(settings.get("metadata_language", "de-DE")).lower()
    preferred = metadata_lang.split("-")[0] if metadata_lang else "de"
    langs = []
    for lang in (preferred, "de", "en"):
        if lang in ("de", "en", "it", "tr") and lang not in langs:
            langs.append(lang)
    series_words = (
        "filmreihe", "filmserie", "franchise", "film series", "media franchise",
        "film franchise", "series of films", "films", "film saga", "saga"
    )
    headers = {"User-Agent": "EpiMediaHub/%s (saga-category-image)" % PLUGIN_VERSION, "Accept": "application/json"}
    for lang in langs:
        try:
            params = {
                "action": "query",
                "generator": "search",
                "gsrsearch": "%s film series" % query_name,
                "gsrnamespace": "0",
                "gsrlimit": "8",
                "prop": "pageimages|pageterms",
                "piprop": "thumbnail",
                "pithumbsize": "500",
                "pilimit": "8",
                "wbptterms": "description",
                "format": "json",
                "formatversion": "2",
                "origin": "*",
            }
            url = "https://%s.wikipedia.org/w/api.php?%s" % (lang, urlencode(params))
            response = urlopen(Request(url, headers=headers), timeout=10)
            raw = response.read()
            response.close()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "ignore")
            data = json.loads(raw)
            pages = ((data.get("query") or {}).get("pages") or []) if isinstance(data, dict) else []
            ranked = []
            for page in pages:
                if not isinstance(page, dict):
                    continue
                thumb = page.get("thumbnail", {}) if isinstance(page.get("thumbnail", {}), dict) else {}
                image_url = clean_text(thumb.get("source", ""))
                if not image_url:
                    continue
                title = clean_text(page.get("title", ""))
                terms = page.get("terms", {}) if isinstance(page.get("terms", {}), dict) else {}
                descriptions = terms.get("description", [])
                if isinstance(descriptions, str):
                    descriptions = [descriptions]
                desc = " ".join(clean_text(x) for x in descriptions).lower()
                score = _saga_name_match_score(query_name, title)
                if any(word in desc for word in series_words):
                    score += 22
                ranked.append((score, title, image_url, desc))
            ranked.sort(key=lambda item: item[0], reverse=True)
            if ranked and ranked[0][0] >= 72:
                score, title, image_url, desc = ranked[0]
                image_key = hashlib.sha1(image_url.encode("utf-8", "ignore")).hexdigest()
                image_path = download_image_cached(image_url, SAGA_CACHE_DIR, key=image_key, timeout=12, max_bytes=5 * 1024 * 1024)
                if image_path:
                    _save_saga_cache_record(value, {
                        "query": query_name,
                        "name": title,
                        "image_url": image_url,
                        "image_key": image_key,
                        "source": "wikipedia-%s" % lang,
                    })
                    return image_path
        except Exception:
            continue
    return ""


def resolve_saga_category_image(value):
    if not _looks_like_saga_category(value):
        return ""
    resolved, cached_path = saga_category_cache_record(value)
    if resolved:
        return cached_path
    settings = load_global_settings()
    path = _tmdb_saga_category_image(value, settings)
    if path:
        return path
    path = _wikipedia_saga_category_image(value, settings)
    if path:
        return path
    _save_saga_cache_record(value, {"query": _saga_category_clean_name(value), "source": "none"})
    return ""

def _actor_category_clean_name(value):
    """Return a useful person-search term from a provider VOD category."""
    text = clean_text(value)
    if not text or text == "__all__":
        return ""
    text = text.replace("_", " ")

    # Providers use many variants such as "[SCHAUSPIELER] Jason Statham",
    # "Filme mit Jason Statham" or "DE | Actor: Jason Statham".
    text = re.sub(r"^[\s\[\(\{]*(?:schauspieler(?:in)?|schauspielerinnen|darsteller(?:in)?|darstellerinnen|actors?|actresses|cast|stars?)[\s\]\)\}]*[:\-|>]*\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*(?:filme?|movies?|serien|series|tv)[\s\-|:]+(?:mit|with|von|by)\s+", "", text, flags=re.I)
    text = re.sub(r"^\s*(?:mit|with)\s+", "", text, flags=re.I)
    text = re.sub(r"\s*[:\-|>]\s*(?:filme?|movies?|serien|series|tv|collection|kollektion)\s*$", "", text, flags=re.I)

    # Remove harmless quality/language/provider decorations around a name.
    # Many IPTV providers use folders such as "VOD | MOVIES | Jason Statham"
    # or "FILME - Jason Statham". Strip those generic wrappers repeatedly so
    # TMDb receives the actual person's name instead of the whole folder title.
    for _i in range(3):
        text = re.sub(r"^\s*(?:DE|GER|GERMAN|EN|ENG|IT|ITA|TR|TUR|VIP|VOD|4K|UHD|FHD|HD)\s*[|:\->]+\s*", "", text, flags=re.I)
        text = re.sub(r"^\s*(?:filme?|movies?|movie|serien|series|tv|kino|cinema|vod)\s*[|:\->]+\s*", "", text, flags=re.I)
        text = re.sub(r"\s*[|:\->]+\s*(?:filme?|movies?|movie|serien|series|tv|kino|cinema|vod|4K|UHD|FHD|HD)\s*$", "", text, flags=re.I)
    # A locale/provider prefix can expose the actor label only after the first
    # cleanup pass, e.g. "DE | Actor: Jason Statham". Strip it once more.
    text = re.sub(r"^[\s\[\(\{]*(?:schauspieler(?:in)?|schauspielerinnen|darsteller(?:in)?|darstellerinnen|actors?|actresses|cast|stars?)[\s\]\)\}]*[:\-|>]*\s*", "", text, flags=re.I)
    text = re.sub(r"\s*[|:\-]\s*(?:DE|GER|GERMAN|EN|ENG|IT|ITA|TR|TUR|4K|UHD|FHD|HD|VOD)\s*$", "", text, flags=re.I)
    text = re.sub(r"^\s*\d{1,3}\s*[.\-)]\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -|:[](){}")
    return text


def _actor_name_norm(value):
    text = clean_text(value).lower()
    # Parenthetical disambiguators from Wikipedia such as "(actor)" should not
    # prevent an otherwise exact name match.
    text = re.sub(r"\([^)]*\)", " ", text)
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def _actor_explicit_label(value):
    raw = clean_text(value)
    return bool(re.search(
        r"(?:^|[\[\(\{\s|:\->])(?:schauspieler(?:in)?|schauspielerinnen|darsteller(?:in)?|darstellerinnen|actors?|actresses|cast|stars?)(?:$|[\]\)\}\s|:\->])|(?:filme?|movies?|serien|series)\s+(?:mit|with)\s+",
        raw,
        flags=re.I
    ))


def _looks_like_actor_category(value):
    raw = clean_text(value)
    name = _actor_category_clean_name(raw)
    if not name:
        return False
    explicit = _actor_explicit_label(raw)
    norm = _actor_name_norm(name)
    blocked = {
        "action", "abenteuer", "adventure", "animation", "anime", "komodie", "comedy",
        "drama", "familie", "family", "fantasy", "horror", "krimi", "crime", "thriller",
        "romantik", "romance", "science fiction", "sci fi", "western", "doku", "dokumentation",
        "documentary", "kinder", "kids", "filme", "movies", "movie", "serien", "series",
        "deutsch", "german", "italienisch", "italian", "turkisch", "turkish", "english",
        "neu", "new", "aktuell", "top", "kino", "cinema", "klassiker", "classics",
        "netflix", "prime", "prime video", "amazon", "disney", "disney plus", "sky", "dazn",
        "paramount", "paramount plus", "apple tv", "hbo", "max", "marvel", "dc",
        "4k", "uhd", "fhd", "hd", "adult", "erotik", "xxx", "alle filme", "alle serien",
        "neuheiten", "empfehlungen", "oscar gewinner", "top filme", "top serien"
    }
    if norm in blocked or any(part in norm for part in (
        "netflix", "prime video", "disney", "paramount", "apple tv", "dazn", "staffel", "season"
    )):
        return False

    tokens = [t for t in name.split() if t]
    if explicit:
        return 1 <= len(tokens) <= 7 and len(name) <= 90
    # Plain folders are accepted when they resemble a personal name. This is
    # intentionally a little more permissive than v0.7.20; final validation is
    # done by TMDb/Wikipedia before an image is shown.
    if not (2 <= len(tokens) <= 6) or len(name) > 80:
        return False
    for token in tokens:
        if any(ch.isdigit() for ch in token):
            return False
        if not re.search(r"[^\W_]", token, flags=re.UNICODE):
            return False
    return True


def _actor_cache_key(value):
    return hashlib.sha1(_actor_name_norm(_actor_category_clean_name(value)).encode("utf-8", "ignore")).hexdigest()


ACTOR_CACHE_VERSION = 3


def actor_category_cache_record(value):
    if not _looks_like_actor_category(value):
        return True, ""
    cache = read_json(ACTOR_CACHE_FILE, {})
    if not isinstance(cache, dict):
        return False, ""
    record = cache.get(_actor_cache_key(value))
    if not isinstance(record, dict):
        return False, ""
    # Retry all v0.7.20 records once so old negative TMDb-only results do not
    # suppress the new Wikipedia fallback.
    if int(record.get("cache_version", 0) or 0) != ACTOR_CACHE_VERSION:
        return False, ""
    age = int(time.time()) - int(record.get("cached_at", 0) or 0)
    positive = bool(record.get("image_key") or record.get("profile_path") or record.get("image_url"))
    max_age = 30 * 86400 if positive else 2 * 86400
    if age < 0 or age >= max_age:
        return False, ""
    image_key = clean_text(record.get("image_key", ""))
    if not image_key:
        seed = clean_text(record.get("profile_path", "")) or clean_text(record.get("image_url", ""))
        if seed:
            image_key = hashlib.sha1(seed.encode("utf-8", "ignore")).hexdigest()
    if not image_key:
        return True, ""
    return True, _cached_image_path(ACTOR_CACHE_DIR, image_key)


def _save_actor_cache_record(value, record):
    cache = read_json(ACTOR_CACHE_FILE, {})
    if not isinstance(cache, dict):
        cache = {}
    record = dict(record or {})
    record["cached_at"] = int(time.time())
    record["cache_version"] = ACTOR_CACHE_VERSION
    cache[_actor_cache_key(value)] = record
    write_json(ACTOR_CACHE_FILE, cache)


def _actor_name_match_score(wanted, candidate):
    wanted_norm = _actor_name_norm(wanted)
    candidate_norm = _actor_name_norm(candidate)
    if not wanted_norm or not candidate_norm:
        return 0
    if wanted_norm == candidate_norm:
        return 100
    w = set(wanted_norm.split())
    c = set(candidate_norm.split())
    if not w or not c:
        return 0
    common = len(w & c)
    if common == len(w) and common >= 2:
        return 85
    if common >= 2:
        return 60 + common
    return 0


def _tmdb_actor_category_image(value, settings):
    if not clean_text(settings.get("tmdb_api_key", "")):
        return ""
    query_name = _actor_category_clean_name(value)
    try:
        result = tmdb_request(
            "/search/person",
            {"query": query_name, "language": settings.get("metadata_language", "de-DE"), "include_adult": "false"},
            settings
        )
        hits = result.get("results", []) if isinstance(result, dict) else []
        ranked = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            department = clean_text(hit.get("known_for_department", "")).lower()
            score = _actor_name_match_score(query_name, hit.get("name", ""))
            if department in ("acting", "schauspiel"):
                score += 15
            if hit.get("profile_path"):
                score += 5
            ranked.append((score, hit))
        ranked.sort(key=lambda item: item[0], reverse=True)
        hit = ranked[0][1] if ranked and ranked[0][0] >= (80 if not _actor_explicit_label(value) else 25) else None
        if isinstance(hit, dict):
            profile_path = clean_text(hit.get("profile_path", ""))
            if profile_path:
                image_key = hashlib.sha1(profile_path.encode("utf-8", "ignore")).hexdigest()
                image_url = "https://image.tmdb.org/t/p/w185%s" % profile_path
                image_path = download_image_cached(image_url, ACTOR_CACHE_DIR, key=image_key, timeout=12, max_bytes=3 * 1024 * 1024)
                if image_path:
                    _save_actor_cache_record(value, {
                        "query": query_name,
                        "profile_path": profile_path,
                        "image_url": image_url,
                        "image_key": image_key,
                        "tmdb_id": hit.get("id"),
                        "name": clean_text(hit.get("name", query_name)),
                        "source": "tmdb",
                    })
                    return image_path
    except Exception:
        pass
    return ""


def _wikipedia_actor_category_image(value, settings):
    """Key-free actor portrait fallback using Wikipedia page thumbnails."""
    query_name = _actor_category_clean_name(value)
    wanted = _actor_name_norm(query_name)
    if not wanted:
        return ""
    metadata_lang = clean_text(settings.get("metadata_language", "de-DE")).lower()
    preferred = metadata_lang.split("-")[0] if metadata_lang else "de"
    langs = []
    for lang in (preferred, "de", "en"):
        if lang in ("de", "en", "it", "tr") and lang not in langs:
            langs.append(lang)
    actor_words = (
        "actor", "actress", "schauspieler", "schauspielerin", "darsteller", "darstellerin",
        "attore", "attrice", "oyuncu", "film actor", "television actor"
    )
    headers = {"User-Agent": "EpiMediaHub/%s (actor-category-image)" % PLUGIN_VERSION, "Accept": "application/json"}
    for lang in langs:
        try:
            params = {
                "action": "query",
                "generator": "search",
                "gsrsearch": query_name,
                "gsrnamespace": "0",
                "gsrlimit": "6",
                "prop": "pageimages|pageterms",
                "piprop": "thumbnail",
                "pithumbsize": "240",
                "wbptterms": "description",
                "format": "json",
                "formatversion": "2",
            }
            url = "https://%s.wikipedia.org/w/api.php?%s" % (lang, urlencode(params))
            response = urlopen(Request(url, headers=headers), timeout=12)
            raw = response.read()
            response.close()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", "ignore")
            data = json.loads(raw)
            pages = data.get("query", {}).get("pages", []) if isinstance(data, dict) else []
            ranked = []
            for page in pages:
                if not isinstance(page, dict):
                    continue
                thumb = page.get("thumbnail", {}) if isinstance(page.get("thumbnail", {}), dict) else {}
                image_url = clean_text(thumb.get("source", ""))
                if not image_url:
                    continue
                title = clean_text(page.get("title", ""))
                terms = page.get("terms", {}) if isinstance(page.get("terms", {}), dict) else {}
                descriptions = terms.get("description", [])
                if isinstance(descriptions, str):
                    descriptions = [descriptions]
                desc = " ".join(clean_text(x) for x in descriptions).lower()
                score = _actor_name_match_score(query_name, title)
                if any(word in desc for word in actor_words):
                    score += 25
                # For non-explicit plain folders demand a strong name match;
                # for explicitly labelled actor folders allow a good search hit.
                ranked.append((score, title, image_url, desc))
            ranked.sort(key=lambda item: item[0], reverse=True)
            minimum = 85 if not _actor_explicit_label(value) else 45
            if ranked and ranked[0][0] >= minimum:
                score, title, image_url, desc = ranked[0]
                image_key = hashlib.sha1(image_url.encode("utf-8", "ignore")).hexdigest()
                image_path = download_image_cached(image_url, ACTOR_CACHE_DIR, key=image_key, timeout=12, max_bytes=3 * 1024 * 1024)
                if image_path:
                    _save_actor_cache_record(value, {
                        "query": query_name,
                        "name": title,
                        "image_url": image_url,
                        "image_key": image_key,
                        "source": "wikipedia-%s" % lang,
                    })
                    return image_path
        except Exception:
            continue
    return ""


def resolve_actor_category_image(value):
    """Resolve an actor category asynchronously.

    A TMDb key/token is required to validate the category as a real person.
    Wikipedia remains a secondary portrait fallback after the TMDb attempt.
    This avoids guessing ordinary two-word movie folders as actors.
    """
    settings = load_global_settings()
    if not settings.get("actor_category_images", True) or not _looks_like_actor_category(value):
        return ""
    if not clean_text(settings.get("tmdb_api_key", "")):
        return ""
    resolved, cached_path = actor_category_cache_record(value)
    if resolved:
        return cached_path
    path = _tmdb_actor_category_image(value, settings)
    if path:
        return path
    path = _wikipedia_actor_category_image(value, settings)
    if path:
        return path
    _save_actor_cache_record(value, {"query": _actor_category_clean_name(value), "source": "none"})
    return ""


def tmdb_actor_category_image(value):
    # Compatibility wrapper for older internal call sites.
    return resolve_actor_category_image(value)


def metadata_cache_key(entry, kind, language):
    raw = "%s|%s|%s" % (kind, clean_media_title(entry.get("title", ""), kind).lower(), language)
    return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()


def tmdb_lookup(entry, kind):
    settings = load_global_settings()
    language = settings.get("metadata_language", "de-DE")
    cache = read_json(METADATA_CACHE_FILE, {})
    if not isinstance(cache, dict):
        cache = {}
    key = metadata_cache_key(entry, kind, language)
    cached = cache.get(key)
    if isinstance(cached, dict) and int(time.time()) - int(cached.get("cached_at", 0)) < 30 * 86400:
        return cached
    original_title = entry.get("title", "")
    title = clean_media_title(original_title, kind)
    year = extract_year(original_title)
    media_type = "tv" if kind == "series" else "movie"
    params = {"query": title, "language": language, "include_adult": "false"}
    if year:
        params["first_air_date_year" if media_type == "tv" else "year"] = year
    result = tmdb_request("/search/%s" % media_type, params, settings)
    results = result.get("results", []) if isinstance(result, dict) else []
    if not results:
        raise Exception("Keine passenden TMDb-Daten gefunden.")
    hit = results[0]
    media_id = hit.get("id")
    details = tmdb_request("/%s/%s" % (media_type, media_id), {"language": language}, settings)
    release = details.get("first_air_date", "") if media_type == "tv" else details.get("release_date", "")
    runtime = 0
    if media_type == "tv":
        runtimes = details.get("episode_run_time", []) or []
        runtime = runtimes[0] if runtimes else 0
    else:
        runtime = details.get("runtime", 0) or 0
    metadata = {
        "cached_at": int(time.time()),
        "title": details.get("name") if media_type == "tv" else details.get("title"),
        "original_title": details.get("original_name") if media_type == "tv" else details.get("original_title"),
        "rating": details.get("vote_average", 0),
        "votes": details.get("vote_count", 0),
        "overview": details.get("overview", ""),
        "release": release,
        "runtime": runtime,
        "genres": [g.get("name", "") for g in details.get("genres", []) if isinstance(g, dict)],
        "poster_path": details.get("poster_path", ""),
        "tmdb_id": media_id,
    }
    cache[key] = metadata
    write_json(METADATA_CACHE_FILE, cache)
    return metadata


def tmdb_poster_file(metadata):
    poster_path = clean_text((metadata or {}).get("poster_path", ""))
    if not poster_path:
        return ""
    key = hashlib.sha1(poster_path.encode("utf-8", "ignore")).hexdigest()
    cached = _cached_image_path(POSTER_CACHE_DIR, key)
    if cached:
        return cached
    url = "https://image.tmdb.org/t/p/w500%s" % poster_path
    return download_image_cached(url, POSTER_CACHE_DIR, key=key, timeout=12)


# -------------------- Weather --------------------

def _weather_condition(code, fallback=""):
    mapping = {
        113: "Klar", 116: "Leicht bewölkt", 119: "Bewölkt", 122: "Bedeckt",
        143: "Nebel", 176: "Regenschauer", 179: "Schneeschauer", 182: "Schneeregen",
        185: "Nieselregen", 200: "Gewitter", 227: "Schnee", 230: "Starker Schnee",
        248: "Nebel", 260: "Gefrierender Nebel", 263: "Nieselregen", 266: "Nieselregen",
        281: "Gefrierender Nieselregen", 284: "Starker Nieselregen", 293: "Leichter Regen",
        296: "Regen", 299: "Regen", 302: "Regen", 305: "Starker Regen", 308: "Starkregen",
        311: "Gefrierender Regen", 314: "Gefrierender Regen", 317: "Schneeregen", 320: "Schneeregen",
        323: "Leichter Schnee", 326: "Schnee", 329: "Schnee", 332: "Schnee",
        335: "Starker Schnee", 338: "Starker Schnee", 350: "Graupel", 353: "Regenschauer",
        356: "Starke Schauer", 359: "Starkregen", 362: "Schneeregenschauer", 365: "Schneeregenschauer",
        368: "Schneeschauer", 371: "Starke Schneeschauer", 374: "Graupelschauer", 377: "Graupelschauer",
        386: "Gewitter", 389: "Starkes Gewitter", 392: "Gewitter mit Schnee", 395: "Starker Schneeschauer"
    }
    try:
        code = int(code)
    except Exception:
        code = 0
    return mapping.get(code, clean_text(fallback) or "Wetter")

def load_weather_cache():
    data = read_json(WEATHER_CACHE_FILE, {})
    return data if isinstance(data, dict) else {}

def weather_cache_fresh(max_age=30 * 60):
    data = load_weather_cache()
    try:
        return bool(data.get("location")) and (int(time.time()) - int(data.get("timestamp", 0))) < int(max_age)
    except Exception:
        return False

def weather_text(include_condition=True):
    settings = load_global_settings()
    if not settings.get("weather_enabled", True):
        return ""
    data = load_weather_cache()
    location = clean_text(data.get("location", ""))
    temp = clean_text(data.get("temp_c", ""))
    condition = clean_text(data.get("condition", ""))
    if not location:
        return "Wetter wird geladen …"
    result = location
    if temp:
        result += "  %s°C" % temp
    if include_condition and condition:
        result += "  %s" % condition
    return result

def weather_icon_kind(data=None):
    data = data if isinstance(data, dict) else load_weather_cache()
    try:
        code = int(data.get("code", 0) or 0)
    except Exception:
        code = 0
    condition = clean_text(data.get("condition", "")).lower()
    if code in (200, 386, 389, 392) or "gewitter" in condition:
        return "storm"
    if code in (143, 248, 260) or "nebel" in condition:
        return "fog"
    if code in (179, 227, 230, 317, 320, 323, 326, 329, 332, 335, 338, 350, 362, 365, 368, 371, 374, 377, 392, 395) or "schnee" in condition or "graupel" in condition:
        return "snow"
    if code in (176, 182, 185, 263, 266, 281, 284, 293, 296, 299, 302, 305, 308, 311, 314, 353, 356, 359) or "regen" in condition or "niesel" in condition:
        return "rain"
    if code == 113 or "klar" in condition or "sonn" in condition:
        return "sun"
    return "cloud"


def weather_display_parts():
    settings = load_global_settings()
    if not settings.get("weather_enabled", True):
        return "", "", ""
    data = load_weather_cache()
    location = clean_text(data.get("location", ""))
    temp = clean_text(data.get("temp_c", ""))
    condition = clean_text(data.get("condition", ""))
    if not location:
        return "Wetter wird geladen …", "", WEATHER_ICONS.get("cloud", "")
    main = location
    if temp:
        main += "   %s°C" % temp
    return main, condition, WEATHER_ICONS.get(weather_icon_kind(data), WEATHER_ICONS.get("cloud", ""))


def set_weather_icon(widget, icon_path):
    try:
        if not icon_path or not os.path.isfile(icon_path):
            widget.hide()
            return
        if widget.instance is not None:
            widget.instance.setPixmapFromFile(icon_path)
        widget.show()
    except Exception:
        try:
            widget.hide()
        except Exception:
            pass

def _resolve_weather_query(requested):
    """Return (wttr_query, display_name) for a configured weather location.

    A five-digit value is treated as a German postal code. Nominatim is used
    only for this explicit user request and is protected by the normal weather
    cache, so this does not create repeated geocoding traffic. Coordinates are
    then passed to wttr.in for more local weather than a city-name lookup.
    """
    requested = clean_text(requested)
    if not re.match(r"^\d{5}$", requested):
        return requested, requested
    try:
        params = urlencode({
            "postalcode": requested,
            "country": "Germany",
            "countrycodes": "de",
            "format": "jsonv2",
            "addressdetails": "1",
            "limit": "1"
        })
        url = "https://nominatim.openstreetmap.org/search?%s" % params
        req = Request(url, headers={
            "User-Agent": "EpiMediaHub/%s (weather postal-code lookup)" % PLUGIN_VERSION,
            "Accept": "application/json"
        })
        resp = urlopen(req, timeout=7)
        try:
            raw = resp.read()
        finally:
            try:
                resp.close()
            except Exception:
                pass
        if not isinstance(raw, str):
            raw = raw.decode("utf-8", "replace")
        result = json.loads(raw)
        if isinstance(result, list) and result:
            hit = result[0] if isinstance(result[0], dict) else {}
            lat = clean_text(hit.get("lat", ""))
            lon = clean_text(hit.get("lon", ""))
            addr = hit.get("address", {}) if isinstance(hit.get("address", {}), dict) else {}
            district = ""
            for key in ("suburb", "city_district", "borough", "quarter", "neighbourhood"):
                district = clean_text(addr.get(key, ""))
                if district:
                    break
            city = ""
            for key in ("city", "town", "village", "municipality", "county"):
                city = clean_text(addr.get(key, ""))
                if city:
                    break
            if district and city and district.lower() != city.lower():
                display = "%s · %s" % (district, city)
            else:
                display = district or city or requested
            if lat and lon:
                return "%s,%s" % (lat, lon), display
            return requested, display
    except Exception:
        pass
    return requested, requested


def fetch_weather_snapshot(settings=None):
    settings = settings or load_global_settings()
    if not settings.get("weather_enabled", True):
        return {}
    requested = clean_text(settings.get("weather_location", ""))
    query, resolved_name = _resolve_weather_query(requested)
    location_part = quote(query) if query else ""
    url = "https://wttr.in/%s?format=j1" % location_part
    request = Request(url, headers={"User-Agent": "EpiMediaHub/%s" % PLUGIN_VERSION, "Accept": "application/json"})
    response = urlopen(request, timeout=10)
    try:
        raw = response.read()
    finally:
        try:
            response.close()
        except Exception:
            pass
    if not isinstance(raw, str):
        raw = raw.decode("utf-8", "replace")
    payload = json.loads(raw)
    current = (payload.get("current_condition") or [{}])[0]
    nearest = (payload.get("nearest_area") or [{}])[0]
    area_names = nearest.get("areaName") or []
    region_names = nearest.get("region") or []
    area = clean_text(area_names[0].get("value", "")) if area_names and isinstance(area_names[0], dict) else ""
    region = clean_text(region_names[0].get("value", "")) if region_names and isinstance(region_names[0], dict) else ""
    if re.match(r"^\d{5}$", requested):
        location = resolved_name or area or region or requested
    else:
        location = requested or area or region or "Standort"
        # Prefer the town name; append region only when it adds useful information.
        if not requested and area and region and region.lower() != area.lower():
            location = "%s" % area
    desc = ""
    descs = current.get("weatherDesc") or []
    if descs and isinstance(descs[0], dict):
        desc = clean_text(descs[0].get("value", ""))
    snapshot = {
        "timestamp": int(time.time()),
        "location": location,
        "temp_c": clean_text(current.get("temp_C", "")),
        "condition": _weather_condition(current.get("weatherCode", 0), desc),
        "code": current.get("weatherCode", 0),
        "requested_location": requested,
    }
    write_json(WEATHER_CACHE_FILE, snapshot)
    return snapshot


class EpiSplash(Screen):
    skin = SPLASH_SKIN

    def __init__(self, session):
        Screen.__init__(self, session)
        self["intro"] = Pixmap()
        self["version"] = Label("Epi MediaHub v%s" % PLUGIN_VERSION)
        self["skip"] = Label(self._skipText())
        self["actions"] = ActionMap(
            ["OkCancelActions"],
            {"ok": self.finish, "cancel": self.finish},
            -10
        )
        self._timer = eTimer()
        connect_timer(self._timer, self._nextFrame)
        self._frame = -1
        self._finished = False
        self._previous_service = None
        self._intro_audio_started = False
        self._intro_audio_ref = None
        self.onShown.append(self.startTimer)

    def _skipText(self):
        lang = current_app_language()
        texts = {
            "de": "OK / EXIT = Intro überspringen",
            "en": "OK / EXIT = Skip intro",
            "tr": "OK / EXIT = Girişi atla",
            "it": "OK / EXIT = Salta intro",
            "es": "OK / EXIT = Omitir intro",
        }
        return texts.get(lang, texts["de"])

    def _paintFrame(self):
        if self._frame < 0 or self._frame >= len(INTRO_FRAMES):
            return False
        path = INTRO_FRAMES[self._frame]
        if not os.path.isfile(path):
            return False
        try:
            widget = self["intro"]
            if widget.instance is not None:
                widget.instance.setPixmapFromFile(path)
                widget.show()
                return True
        except Exception:
            pass
        return False

    def _rememberPreviousService(self):
        try:
            service = self.session.nav.getCurrentlyPlayingServiceOrGroup()
            if service is not None:
                return service
        except Exception:
            pass
        try:
            return self.session.nav.getCurrentlyPlayingServiceReference()
        except Exception:
            return None

    def _startIntroAudio(self):
        if self._intro_audio_started or not os.path.isfile(INTRO_SOUND):
            return
        self._previous_service = self._rememberPreviousService()
        try:
            # Enigma2's own MediaPlayer feeds local MP3/WAV files to service
            # type 4097 as a plain filesystem path.  The old implementation
            # prepended file://, which is rejected on a number of OpenATV builds.
            ref = eServiceReference(4097, 0, INTRO_SOUND)
            ref.setName("Epi MediaHub Intro")
            result = self.session.nav.playService(ref)
            # Navigation.playService normally returns 0/None on accepted starts.
            # Keep the reference alive for the complete splash lifetime.
            if result not in (None, 0):
                self._intro_audio_ref = None
                return
            self._intro_audio_ref = ref
            self._intro_audio_started = True
        except Exception:
            self._intro_audio_ref = None
            self._intro_audio_started = False

    def _stopIntroAudio(self):
        started = self._intro_audio_started
        self._intro_audio_started = False
        self._intro_audio_ref = None
        if started:
            try:
                self.session.nav.stopService()
            except Exception:
                pass
        if self._previous_service is not None:
            try:
                self.session.nav.playService(self._previous_service)
            except Exception:
                pass
        self._previous_service = None

    def startTimer(self):
        self._frame = 0
        if not self._paintFrame():
            self.finish()
            return
        # v0.9.19: sound and visuals share the same 3.20 s timeline.
        # The melody hits frames 0/2/4/6/8/9 and the final chord decays while
        # the completed logo remains on screen.
        self._startIntroAudio()
        self._scheduleNext(180)

    def _scheduleNext(self, delay):
        try:
            self._timer.start(int(delay), True)
        except TypeError:
            self._timer.start(int(delay))
        except Exception:
            self.finish()

    def _nextFrame(self):
        if self._finished:
            return
        self._frame += 1
        if self._frame >= len(INTRO_FRAMES):
            self.finish()
            return
        if not self._paintFrame():
            self.finish()
            return
        # Frames 1-9 advance on a strict 180 ms beat grid. Once frame 9 is
        # visible, hold it for 1.58 s so animation and the 3.20 s signature
        # melody end together.
        self._scheduleNext(1580 if self._frame == len(INTRO_FRAMES) - 1 else 180)

    def finish(self):
        if self._finished:
            return
        self._finished = True
        try:
            self._timer.stop()
        except Exception:
            pass
        self._stopIntroAudio()
        self.close()


if MoviePlayer is not None:
    class EpiMoviePlayer(MoviePlayer):
        def __init__(self, session, service, preferences, profile_id="", entry_url="", resume_position=0, entry=None, episode_queue=None, episode_index=-1):
            self._epi_preferences = preferences or ["deu", "ita", "eng"]
            self._epi_profile_id = profile_id
            self._epi_entry_url = entry_url
            self._epi_entry = dict(entry or {})
            self._epi_resume_position = int(resume_position or 0)
            self._epi_episode_queue = [dict(item) for item in (episode_queue or []) if isinstance(item, dict) and clean_text(item.get("url", ""))]
            try:
                self._epi_episode_index = int(episode_index)
            except Exception:
                self._epi_episode_index = -1
            self._epi_manual_exit = False
            self._epi_eof_guard = False
            self._epi_ignore_eof_until = 0.0
            self._epi_last_switch = 0.0
            MoviePlayer.__init__(self, session, service)
            self._epi_audio_timer = eTimer()
            self._epi_resume_timer = eTimer()
            connect_timer(self._epi_audio_timer, self.applyPreferredAudio)
            connect_timer(self._epi_resume_timer, self.applyResume)
            self._restartMediaTimers()
            try:
                self.onClose.append(self.savePosition)
            except Exception:
                pass
            # Some OpenATV images let MoviePlayer action maps swallow EXIT/STOP
            # for streamed VOD. Give Epi MediaHub a higher-priority explicit exit.
            self["epiExitActions"] = ActionMap(
                ["OkCancelActions", "InfobarActions", "MediaPlayerActions", "ColorActions"],
                {"cancel": self.epiExit, "stop": self.epiExit, "red": self.epiExit},
                -10
            )
            # v0.8.5: Series episode navigation is intentionally attached to
            # several action contexts because OpenATV/OpenHDF images map the same
            # physical cursor/previous/next keys differently.  A debounce in
            # _switchEpisode prevents one physical press (make + break) from
            # advancing twice. Movies keep their normal seeking behaviour.
            if self._epi_episode_queue and self._epi_episode_index >= 0:
                self["epiEpisodeActions"] = ActionMap(
                    ["DirectionActions", "NavigationActions", "InfobarSeekActions", "InfobarArrowSeekActions", "MediaPlayerActions"],
                    {
                        "left": self.epiPreviousEpisode,
                        "right": self.epiNextEpisode,
                        "leftUp": self.epiPreviousEpisode,
                        "rightUp": self.epiNextEpisode,
                        "moveUp": self.epiPreviousEpisode,
                        "moveDown": self.epiNextEpisode,
                        "previous": self.epiPreviousEpisode,
                        "next": self.epiNextEpisode,
                    },
                    -20
                )

        def _restartMediaTimers(self):
            try:
                self._epi_audio_timer.stop()
            except Exception:
                pass
            try:
                self._epi_resume_timer.stop()
            except Exception:
                pass
            try:
                self._epi_audio_timer.start(1400, True)
                if self._epi_resume_position > 0:
                    self._epi_resume_timer.start(2200, True)
            except TypeError:
                try:
                    self._epi_audio_timer.start(1400)
                    if self._epi_resume_position > 0:
                        self._epi_resume_timer.start(2200)
                except Exception:
                    pass
            except Exception:
                pass

        def epiExit(self):
            self._epi_manual_exit = True
            try:
                self.savePosition()
            except Exception:
                pass
            try:
                self.session.nav.stopService()
            except Exception:
                pass
            self.close()

        def leavePlayer(self):
            self.epiExit()

        def doEofInternal(self, playing):
            # OpenATV routes natural VOD EOF through this hook. Series episodes
            # use it to advance inside the current season instead of closing.
            if not playing:
                return
            if self._epi_manual_exit:
                return
            if time.time() < self._epi_ignore_eof_until:
                return
            if self._handleEpisodeEof():
                return
            try:
                return MoviePlayer.doEofInternal(self, playing)
            except Exception:
                self.epiExit()

        def _handleEpisodeEof(self):
            if self._epi_eof_guard:
                return True
            current = self._epi_entry or {}
            if current.get("type") != "series" or not current.get("is_episode"):
                return False
            self._epi_eof_guard = True
            try:
                # The completed episode becomes the current "recent" item and
                # any stored resume point is cleared.
                save_recent_entry(self._epi_profile_id, current)
                save_resume_position(self._epi_profile_id, self._epi_entry_url, 0, 1)

                next_index = self._epi_episode_index + 1
                if next_index < 0 or next_index >= len(self._epi_episode_queue):
                    self._epi_eof_guard = False
                    return False
                next_entry = self._epi_episode_queue[next_index]
                next_url = clean_text(next_entry.get("url", ""))
                if not next_url:
                    self._epi_eof_guard = False
                    return False

                self._epi_episode_index = next_index
                self._epi_entry = dict(next_entry)
                self._epi_entry_url = next_url
                self._epi_resume_position = 0
                self._epi_ignore_eof_until = time.time() + 1.0

                # Updating this at playback start means "Recently watched"
                # immediately follows the episode the viewer has advanced to.
                save_recent_entry(self._epi_profile_id, next_entry)

                ref = eServiceReference(1, 0, next_url)
                ref.setName(next_entry.get("title", "Epi MediaHub"))
                try:
                    self.session.nav.stopService()
                except Exception:
                    pass
                self.session.nav.playService(ref)
                try:
                    self.cur_service = ref
                except Exception:
                    pass
                self._restartMediaTimers()
                self._epi_eof_guard = False
                return True
            except Exception:
                self._epi_eof_guard = False
                return False

        def _epiCanNavigateEpisodes(self):
            return bool(self._epi_episode_queue and self._epi_episode_index >= 0)

        # MoviePlayer itself binds DirectionActions to self.left/self.right on
        # many Enigma2 images. Overriding those methods is more reliable than
        # relying on an additional ActionMap alone.
        def left(self):
            if self._epiCanNavigateEpisodes():
                return self.epiPreviousEpisode()
            try:
                return MoviePlayer.left(self)
            except Exception:
                return 0

        def right(self):
            if self._epiCanNavigateEpisodes():
                return self.epiNextEpisode()
            try:
                return MoviePlayer.right(self)
            except Exception:
                return 0

        def epiPreviousEpisode(self):
            return self._switchEpisode(-1)

        def epiNextEpisode(self):
            return self._switchEpisode(1)

        def _switchEpisode(self, delta):
            if not self._epi_episode_queue or self._epi_episode_index < 0:
                return 1
            now = time.time()
            if now - float(getattr(self, "_epi_last_switch", 0.0) or 0.0) < 0.45:
                return 1
            self._epi_last_switch = now
            target_index = self._epi_episode_index + int(delta)
            if target_index < 0 or target_index >= len(self._epi_episode_queue):
                return 1
            try:
                # Manual episode switching should preserve progress of the
                # episode being left, unlike natural EOF which marks it done.
                self.savePosition()
            except Exception:
                pass
            target = dict(self._epi_episode_queue[target_index])
            target_url = clean_text(target.get("url", ""))
            if not target_url:
                return 1
            self._epi_episode_index = target_index
            self._epi_entry = target
            self._epi_entry_url = target_url
            self._epi_resume_position = 0
            self._epi_manual_exit = False
            self._epi_eof_guard = False
            self._epi_ignore_eof_until = time.time() + 1.0
            try:
                save_recent_entry(self._epi_profile_id, target)
            except Exception:
                pass
            ref = eServiceReference(1, 0, target_url)
            ref.setName(target.get("title", "Epi MediaHub"))
            try:
                self.session.nav.stopService()
            except Exception:
                pass
            self.session.nav.playService(ref)
            try:
                self.cur_service = ref
            except Exception:
                pass
            self._restartMediaTimers()
            return 1

        def applyPreferredAudio(self):
            try:
                service = self.session.nav.getCurrentService()
                tracks = service.audioTracks() if service else None
                if tracks is None:
                    return
                best_index = -1
                best_score = 999
                for index in range(tracks.getNumberOfTracks()):
                    info = tracks.getTrackInfo(index)
                    language = info.getLanguage() if info else ""
                    score = audio_match_score(language, self._epi_preferences)
                    if score < best_score:
                        best_score = score
                        best_index = index
                if best_index >= 0 and best_score < 999:
                    tracks.selectTrack(best_index)
            except Exception:
                pass

        def applyResume(self):
            if self._epi_resume_position <= 0:
                return
            try:
                service = self.session.nav.getCurrentService()
                seek = service.seek() if service else None
                if seek is not None:
                    seek.seekTo(self._epi_resume_position)
                    self._epi_resume_position = 0
            except Exception:
                pass

        def savePosition(self):
            if not self._epi_profile_id or not self._epi_entry_url:
                return
            try:
                service = self.session.nav.getCurrentService()
                seek = service.seek() if service else None
                if seek is None:
                    return
                pos_result = seek.getPlayPosition()
                len_result = seek.getLength()
                position = int(pos_result[1]) if pos_result and len(pos_result) > 1 and pos_result[0] == 0 else 0
                length = int(len_result[1]) if len_result and len(len_result) > 1 and len_result[0] == 0 else 0
                save_resume_position(self._epi_profile_id, self._epi_entry_url, position, length)
            except Exception:
                pass

else:
    EpiMoviePlayer = None



class EpiPinScreen(Screen):
    skin = PIN_SKIN

    def __init__(self, session, title=None):
        Screen.__init__(self, session)
        self.value = ""
        self["logo"] = Pixmap()
        self["title"] = Label(title or tr("pin_default"))
        self["pin"] = Label("")
        self["info"] = Label(tr("pin_help"))
        actions = {
            "ok": self.accept,
            "cancel": self.cancel,
            "left": self.backspace,
        }
        for digit in range(10):
            actions[str(digit)] = self._digit_handler(str(digit))
        self["actions"] = ActionMap(
            ["OkCancelActions", "NumberActions", "DirectionActions"],
            actions,
            -1
        )
        self.refresh()

    def _digit_handler(self, digit):
        return lambda: self.addDigit(digit)

    def addDigit(self, digit):
        if len(self.value) < 4:
            self.value += digit
            self.refresh()
        if len(self.value) >= 4:
            # Keep the PIN visible as four stars; confirmation still happens
            # with OK so accidental key presses do not submit immediately.
            pass

    def backspace(self):
        self.value = self.value[:-1]
        self.refresh()

    def refresh(self):
        shown = ["*" if index < len(self.value) else "_" for index in range(4)]
        self["pin"].setText("   ".join(shown))

    def accept(self):
        if len(self.value) != 4:
            self["info"].setText(tr("pin_four"))
            return
        self.close(self.value)

    def cancel(self):
        self.close(None)


class EpiExitConfirm(Screen):
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


class EpiLivePlayer(Screen):
    skin = LIVE_PLAYER_SKIN

    def __init__(self, session, profile_id, entries, start_index=0):
        Screen.__init__(self, session)
        self.profile_id = profile_id
        self.entries = [entry for entry in list(entries or []) if entry.get("url")]
        self.index = int(start_index or 0)
        if self.index < 0 or self.index >= len(self.entries):
            self.index = 0

        self["picon"] = Pixmap()
        self["channel"] = Label("")
        self["bannerAccent"] = Label("")
        self["weather_icon"] = Pixmap()
        self["weather"] = Label("")
        self["clock"] = Label("")
        self["now"] = Label("")
        self["next"] = Label("")
        self["help"] = Label(tr("live_help"))
        if parseColor is not None:
            try:
                if self["bannerAccent"].instance is not None:
                    self["bannerAccent"].instance.setBackgroundColor(parseColor(theme_accent()))
            except Exception:
                pass

        self._banner_timer = eTimer()
        connect_timer(self._banner_timer, self.hideBanner)
        self._epg_job = None
        self._epg_result = None
        self._epg_timer = eTimer()
        connect_timer(self._epg_timer, self._pollLiveEpg)
        self._picon_job = None
        self._picon_result = None
        self._picon_timer = eTimer()
        connect_timer(self._picon_timer, self._pollBannerPicon)

        # Live-stream watchdog. Broken/offline IPTV services can otherwise keep
        # Enigma2 busy for several seconds. We listen for native service events
        # and also enforce a bounded startup window before stopping the attempt.
        self._stream_watchdog = eTimer()
        connect_timer(self._stream_watchdog, self._liveWatchdogExpired)
        self._stream_failure_shown = False
        self._stream_started = False
        self._ignore_failure_until = 0.0
        self._recent_live_url = ""
        self._service_event_tracker = None
        try:
            eventmap = {}
            if iPlayableService is not None:
                for event_name, callback in (("evTunedIn", self._liveReady), ("evVideoSizeChanged", self._liveReady), ("evTuneFailed", self._liveFailedEvent), ("evEOF", self._liveFailedEvent)):
                    event_id = getattr(iPlayableService, event_name, None)
                    if event_id is not None:
                        eventmap[event_id] = callback
            if eventmap and ServiceEventTracker is not None:
                self._service_event_tracker = ServiceEventTracker(screen=self, eventmap=eventmap)
        except Exception:
            self._service_event_tracker = None

        self["actions"] = ActionMap(
            ["OkCancelActions", "DirectionActions", "InfoActions", "InfobarEPGActions"],
            {
                "cancel": self.exitToList,
                "ok": self.exitToList,
                "up": self.zapNext,
                "down": self.zapPrevious,
                "left": self.zapPrevious,
                "right": self.zapNext,
                "chplus": self.zapNext,
                "chminus": self.zapPrevious,
                "info": self.showBanner,
                "showEventInfo": self.showBanner,
                "EPGPressed": self.openGrid,
            },
            -2
        )
        self.onShown.append(self.startCurrent)

    def startCurrent(self):
        if self.entries:
            self.playIndex(self.index)

    def playIndex(self, index):
        if not self.entries:
            return
        self.index = int(index) % len(self.entries)
        entry = self.entries[self.index]
        self._stream_failure_shown = False
        self._stream_started = False
        # Ignore the tail-end EOF generated by the service we just replaced.
        self._ignore_failure_until = time.time() + 0.8
        try:
            self._stream_watchdog.stop()
        except Exception:
            pass
        try:
            ref = eServiceReference(1, 0, entry.get("url", ""))
            ref.setName(entry.get("title", "Epi MediaHub"))
            self.session.nav.playService(ref)
            try:
                self._stream_watchdog.start(7000, True)
            except TypeError:
                self._stream_watchdog.start(7000)
        except Exception:
            self._showLiveUnavailable()
        self.updateBanner()

    def _liveReady(self):
        self._stream_started = True
        try:
            self._stream_watchdog.stop()
        except Exception:
            pass
        # Only successful tunes enter LIVE history. This keeps broken/offline
        # services out of "Zuletzt angesehen" and also records zapping.
        try:
            entry = self.entries[self.index] if self.entries else None
            url = clean_text((entry or {}).get("url", ""))
            if entry and url and url != self._recent_live_url:
                save_recent_entry(self.profile_id, entry)
                self._recent_live_url = url
        except Exception:
            pass

    def _liveFailedEvent(self):
        if time.time() < self._ignore_failure_until:
            return
        self._showLiveUnavailable()

    def _serviceLooksPlayable(self):
        try:
            service = self.session.nav.getCurrentService()
            if service is None:
                return False
            info = service.info()
            if info is None or iServiceInformation is None:
                return self._stream_started
            for attr in ("sVideoWidth", "sVideoHeight", "sAudioPID"):
                key = getattr(iServiceInformation, attr, None)
                if key is None:
                    continue
                try:
                    if int(info.getInfo(key)) > 0:
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return self._stream_started

    def _liveWatchdogExpired(self):
        if self._serviceLooksPlayable():
            self._liveReady()
            return
        self._showLiveUnavailable()

    def _showLiveUnavailable(self):
        if self._stream_failure_shown:
            return
        self._stream_failure_shown = True
        try:
            self._stream_watchdog.stop()
        except Exception:
            pass
        try:
            self.session.nav.stopService()
        except Exception:
            pass
        try:
            self["now"].setText(tr("channel_unavailable"))
            self["next"].setText("")
            self.showBanner()
        except Exception:
            pass
        # v0.8.1: make a broken/offline stream impossible to miss. The dialog
        # is intentionally time-limited, so users can dismiss it immediately
        # with OK/EXIT or simply wait a few seconds and continue zapping.
        try:
            message = "%s\n\n%s" % (tr("channel_unavailable_title"), tr("channel_unavailable"))
            self.session.open(
                MessageBox,
                message,
                MessageBox.TYPE_ERROR,
                timeout=7
            )
        except Exception:
            pass

    def updateBanner(self):
        if not self.entries:
            return
        entry = self.entries[self.index]
        self["channel"].setText("%d   %s" % (self.index + 1, entry.get("title", tr("channel"))))
        self._setBannerPicon(entry)
        wmain, wdetail, wicon = weather_display_parts()
        weather_line = wmain
        if wdetail:
            weather_line += " · %s" % wdetail
        self["weather"].setText(weather_line)
        set_weather_icon(self["weather_icon"], wicon)
        self["clock"].setText(time.strftime("%H:%M"))
        current, next_item = epg_now_next(self.profile_id, entry)
        if current:
            start = format_clock(current.get("start", 0))
            stop = format_clock(current.get("stop", 0))
            duration = max(1, int(current.get("stop", 0)) - int(current.get("start", 0)))
            elapsed = max(0, int(time.time()) - int(current.get("start", 0)))
            percent = max(0, min(100, int((float(elapsed) / float(duration)) * 100.0)))
            self["now"].setText("%s  %s-%s   %s   [%d%%]" % (
                tr("now"), start, stop, current.get("title", tr("no_title")), percent
            ))
        else:
            if db_source_mode(self.profile_id) == "xtream":
                self["now"].setText("%s  %s" % (tr("now"), tr("epg_loading")))
                self._startLiveEpg(entry)
            else:
                self["now"].setText("%s  %s" % (tr("now"), tr("no_epg")))
        if next_item:
            self["next"].setText("%s  %s-%s   %s" % (
                tr("next"),
                format_clock(next_item.get("start", 0)),
                format_clock(next_item.get("stop", 0)),
                next_item.get("title", tr("no_title"))
            ))
        else:
            self["next"].setText("%s  --" % tr("next"))
        self.showBanner()

    def _setBannerPicon(self, entry):
        path = picon_local_file(entry)
        try:
            if path and os.path.isfile(path) and self["picon"].instance is not None:
                self["picon"].instance.setPixmapFromFile(path)
                self["picon"].show()
                return
            self["picon"].hide()
        except Exception:
            pass
        if not clean_text((entry or {}).get("logo", "")):
            return
        if self._picon_job is not None and self._picon_job.is_alive():
            return
        snapshot = dict(entry)
        self._picon_result = None
        self._picon_job = threading.Thread(target=self._bannerPiconWorker, args=(snapshot,))
        self._picon_job.daemon = True
        self._picon_job.start()
        try:
            self._picon_timer.start(180, True)
        except TypeError:
            self._picon_timer.start(180)

    def _bannerPiconWorker(self, entry):
        try:
            path = ensure_picon_file(entry)
            self._picon_result = (clean_text(entry.get("url", "")), path)
        except Exception:
            self._picon_result = (clean_text(entry.get("url", "")), "")

    def _pollBannerPicon(self):
        if self._picon_job is not None and self._picon_job.is_alive():
            try:
                self._picon_timer.start(180, True)
            except TypeError:
                self._picon_timer.start(180)
            return
        result = self._picon_result
        self._picon_job = None
        self._picon_result = None
        if not self.entries:
            return
        current = self.entries[self.index]
        current_url = clean_text(current.get("url", ""))
        if result and result[0] == current_url and result[1]:
            try:
                if self["picon"].instance is not None:
                    self["picon"].instance.setPixmapFromFile(result[1])
                    self["picon"].show()
            except Exception:
                pass
        elif clean_text(current.get("logo", "")):
            # The user may have zapped while a previous Picon was downloading.
            self._setBannerPicon(current)

    def _startLiveEpg(self, entry):
        if db_source_mode(self.profile_id) != "xtream":
            return
        if xtream_epg_cache_fresh(self.profile_id, entry):
            return
        if self._epg_job is not None and self._epg_job.is_alive():
            return
        snapshot = dict(entry)
        self._epg_result = None
        self._epg_job = threading.Thread(target=self._liveEpgWorker, args=(snapshot,))
        self._epg_job.daemon = True
        self._epg_job.start()
        try:
            self._epg_timer.start(250, True)
        except TypeError:
            self._epg_timer.start(250)

    def _liveEpgWorker(self, entry):
        try:
            items = xtream_short_epg(self.profile_id, entry, limit=8, force=True)
            self._epg_result = (True, clean_text(entry.get("url", "")), len(items), "")
        except Exception as error:
            self._epg_result = (False, clean_text(entry.get("url", "")), 0, str(error))

    def _pollLiveEpg(self):
        if self._epg_job is not None and self._epg_job.is_alive():
            try:
                self._epg_timer.start(250, True)
            except TypeError:
                self._epg_timer.start(250)
            return
        result = self._epg_result
        self._epg_job = None
        self._epg_result = None
        if not result or not self.entries:
            return
        current_url = clean_text(self.entries[self.index].get("url", ""))
        if result[1] == current_url:
            self.updateBanner()

    def showBanner(self):
        try:
            self.show()
        except Exception:
            pass
        try:
            self._banner_timer.stop()
        except Exception:
            pass
        try:
            self._banner_timer.start(4500, True)
        except Exception:
            pass

    def hideBanner(self):
        try:
            self.hide()
        except Exception:
            pass

    def zapNext(self):
        if self.entries:
            self.playIndex(self.index + 1)

    def zapPrevious(self):
        if self.entries:
            self.playIndex(self.index - 1)

    def openGrid(self):
        if not self.entries:
            return
        self.session.open(EpiEPGGridScreen, self.profile_id, self.entries, self.index)

    def exitToList(self):
        try:
            self._banner_timer.stop()
        except Exception:
            pass
        try:
            self._stream_watchdog.stop()
        except Exception:
            pass
        current_url = ""
        if self.entries and 0 <= self.index < len(self.entries):
            current_url = self.entries[self.index].get("url", "")
        self.close(current_url)


class EpiHelpScreen(Screen):
    skin = HELP_SKIN

    def __init__(self, session):
        Screen.__init__(self, session)
        self["logo"] = Pixmap()
        self.topics = localized_help_topics()
        self["title"] = Label(tr("help_title"))
        self["subtitle"] = Label(tr("help_subtitle"))
        self["list"] = MenuList([topic[0] for topic in self.topics])
        self["detail"] = Label("")
        self["info"] = Label(tr("help_info"))
        self["red"] = Label("ROT  %s" % tr("back"))
        self["green"] = Label("GRÜN  %s" % tr("scan"))
        self["yellow"] = Label("GELB  Playlist-Ordner")
        self["blue"] = Label("BLAU  Web-Setup")
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions", "MenuActions"],
            {
                "cancel": self.close,
                "red": self.close,
                "green": self.scanFiles,
                "yellow": self.showPlaylistFolder,
                "blue": self.showOverview,
                "menu": self.close,
                "ok": self.showSelected,
            },
            -1
        )
        try:
            self["list"].onSelectionChanged.append(self.selectionChanged)
        except Exception:
            pass
        self.selectionChanged()

    def selectionChanged(self):
        try:
            index = self["list"].getSelectedIndex()
        except Exception:
            index = 0
        if index < 0 or index >= len(self.topics):
            index = 0
        self["detail"].setText(self.topics[index][1])

    def showSelected(self):
        self.selectionChanged()

    def showOverview(self):
        try:
            self["list"].moveToIndex(0)
        except Exception:
            pass
        self.selectionChanged()

    def showPlaylistFolder(self):
        self.session.open(
            MessageBox,
            "Schnellimport:\n%s\n\nFormat: M3U-PLUS-URL # Playlistname\n\nAlternative für komplette Dateien:\n%s" % (PLAYLIST_TEXT_FILE, FTP_PLAYLIST_DIR),
            MessageBox.TYPE_INFO
        )

    def scanFiles(self):
        added, updated = scan_local_playlists()
        self.session.open(
            MessageBox,
            "Playlist-Quellen neu eingelesen.\nNeu: %d   Aktualisiert/entfernt: %d\n\nSchnellimport:\n%s\n\nM3U-Ordner:\n%s" % (added, updated, PLAYLIST_TEXT_FILE, FTP_PLAYLIST_DIR),
            MessageBox.TYPE_INFO,
            timeout=6
        )


WEB_PLAYLIST_QR_PATH = "/tmp/epimediahub_websetup_qr.png"

WEB_PLAYLIST_SETUP_SKIN = build_fullscreen_skin(
    "EpiWebPlaylistSetup",
    overlay_pixmap(SETTINGS_GLASS_OVERLAY) +
    logo_widget(w=300, h=100) +
    label_widget("title", 380, 28, 845, 48, 29, "right") +
    label_widget("subtitle", 380, 78, 845, 30, 17, "right", fg="#9EADBF") +
    '<widget name="qr" position="%s" size="%s" alphatest="blend" scale="1" zPosition="4" />' % (pos(90, 155), size(275, 275)) +
    label_widget("url", 410, 165, 770, 58, 24, "center", "center", "#101722", "#FFFFFF") +
    label_widget("pin", 535, 250, 520, 78, 40, "center", "center", "#141B27", "#FFFFFF") +
    label_widget("status", 410, 350, 770, 118, 20, "center", "center", "#0D121B", "#E7EEF7") +
    label_widget("info", 100, 505, 1080, 62, 17, "center", "center", None, "#9EADBF") +
    color_button("red", 55, "#8D2830") +
    color_button("green", 350, "#267A42") +
    color_button("yellow", 645, "#8A7624") +
    color_button("blue", 940, "#245B8F")
)


def _playlist_web_generate_qr(value):
    value = clean_text(value)
    if not value:
        return False
    try:
        vendor = os.path.join(PLUGIN_DIR, "vendor")
        if vendor not in sys.path:
            sys.path.insert(0, vendor)
        import segno
        qr = segno.make_qr(value, error="m")
        qr.save(WEB_PLAYLIST_QR_PATH, kind="png", scale=9, border=2, dark="#000000", light="#FFFFFF")
        try:
            os.chmod(WEB_PLAYLIST_QR_PATH, 0o600)
        except Exception:
            pass
        return os.path.isfile(WEB_PLAYLIST_QR_PATH) and os.path.getsize(WEB_PLAYLIST_QR_PATH) > 0
    except Exception:
        return False


def _playlist_web_remove_qr():
    try:
        if os.path.exists(WEB_PLAYLIST_QR_PATH):
            os.remove(WEB_PLAYLIST_QR_PATH)
    except Exception:
        pass


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
        self["qr"] = Pixmap()
        self["url"] = Label("Webserver wird gestartet ...")
        self["pin"] = Label("------")
        self["status"] = Label("QR-Code scannen oder die angezeigte Adresse im Browser öffnen und den PIN eingeben.")
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
        _playlist_web_remove_qr()
        try:self["qr"].hide()
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
            try:self["qr"].hide()
            except Exception:pass
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
        setup_url = "http://%s:%d/" % (ip, port)
        self["url"].setText(setup_url)
        self["pin"].setText(pin)
        if _playlist_web_generate_qr(setup_url):
            try:
                if self["qr"].instance is not None:
                    self["qr"].instance.setPixmapFromFile(WEB_PLAYLIST_QR_PATH)
                self["qr"].show()
            except Exception:
                try:self["qr"].hide()
                except Exception:pass
        else:
            try:self["qr"].hide()
            except Exception:pass
        self["status"].setText("1. QR scannen oder Adresse öffnen\n2. PIN eingeben\n3. M3U oder Xtream eintragen und senden")
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


class EpiProfileSelect(Screen):
    skin = PROFILE_SKIN

    def __init__(self, session):
        Screen.__init__(self, session)
        scan_local_playlists()
        self.data = load_profiles()
        self.profiles = self.data.get("profiles", [])
        self["logo"] = Pixmap()
        self["title"] = Label(tr("profile_title"))
        self["subtitle"] = Label(tr("profile_subtitle"))
        self["list"] = MenuList([])
        self._status_slots = []
        for _slot in range(8):
            _name = "profile_status%d" % _slot
            self[_name] = Pixmap()
            self._status_slots.append(_name)
        self["info"] = Label("")
        self["red"] = Label("ROT  %s" % tr("delete"))
        self["green"] = Label("GRÜN  %s" % tr("add_url"))
        self["yellow"] = Label("GELB  %s" % tr("edit"))
        self["blue"] = Label("BLAU  %s" % tr("help"))
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions", "MenuActions"],
            {"ok": self.openSelected, "cancel": self.requestExit, "red": self.deleteSelected,
             "green": self.addProfile, "yellow": self.editSelected, "blue": self.openWebSetup,
             "menu": self.openHelp}, -1
        )
        self._expiry_job = None
        self._expiry_stop = False
        self._expiry_changed = False
        self._expiry_timer = eTimer()
        connect_timer(self._expiry_timer, self._pollExpiryJob)
        self._health_job = None
        self._health_live = {}
        self._health_stop = False
        self._health_changed = False
        self._health_timer = eTimer()
        connect_timer(self._health_timer, self._pollHealthJob)
        self._web_setup_auto_shown = False
        self._web_setup_timer = eTimer()
        connect_timer(self._web_setup_timer, self._autoWebSetupIfEmpty)
        try:
            self.onShown.append(self._scheduleAutoWebSetupIfEmpty)
        except Exception:
            pass
        try:
            self.onClose.append(self._stopWebSetupAutoTimer)
            self.onClose.append(self._stopExpiryJob)
            self.onClose.append(self._stopHealthJob)
            self["list"].onSelectionChanged.append(self._updateStatusSlots)
        except Exception:
            pass
        self.refreshList()
        self._startHealthJob()
        self._startExpiryJob()

    def _scheduleAutoWebSetupIfEmpty(self):
        if self._web_setup_auto_shown:
            return
        try:
            self._web_setup_timer.start(50, True)
        except Exception:
            pass

    def _stopWebSetupAutoTimer(self):
        try:
            self._web_setup_timer.stop()
        except Exception:
            pass

    def _autoWebSetupIfEmpty(self):
        try:
            self._web_setup_timer.stop()
        except Exception:
            pass
        if self._web_setup_auto_shown:
            return
        # OpenATV 7.6 forbids opening a modal child while the parent is still
        # being skinned/instantiated. Wait until this screen is the executing
        # current dialog, then open the automatic web setup.
        session = self.session
        if getattr(session, "current_dialog", None) is not self or not getattr(session, "in_exec", False):
            try:
                self._web_setup_timer.start(100, True)
            except Exception:
                pass
            return
        self._web_setup_auto_shown = True
        self.data = load_profiles()
        self.profiles = self.data.get("profiles", [])
        if not self.profiles:
            self.openWebSetup()

    def openWebSetup(self):
        self.session.openWithCallback(self._webSetupClosed, EpiWebPlaylistSetup)

    def _webSetupClosed(self, profile_id=None):
        scan_local_playlists()
        self.data = load_profiles()
        self.profiles = self.data.get("profiles", [])
        self.refreshList()
        if profile_id:
            set_active_profile(profile_id)
            self.close(profile_id)
            return
        self._startHealthJob()
        self._startExpiryJob()

    def requestExit(self):
        self.session.openWithCallback(self._exitConfirmed, EpiExitConfirm)

    def _exitConfirmed(self, confirmed=False):
        if confirmed:
            self.close(None)

    def refreshList(self):
        self.data = load_profiles()
        self.profiles = self.data.get("profiles", [])
        rows = []
        active_id = self.data.get("active_id", "")
        for profile in self.profiles:
            marker = "[%s] " % tr("active") if profile.get("id") == active_id else ""
            source = "FTP TXT" if profile.get("managed_text_file") else ("FTP/SFTP" if profile.get("managed_file") else "URL")
            cached = playlist_total_count(profile.get("id"))
            online = clean_text(getattr(self, "_health_live", {}).get(profile.get("id", ""), profile.get("online_status", "")))
            status_text = "Online" if online == "online" else ("Server nicht erreichbar" if online == "offline" else "Prüfe...")
            rows.append("        %s%s   |   %s   |   %d %s   |   %s   |   %s" % (
                marker, profile.get("name", "Playlist"), source, cached, tr("entries"), expiry_summary(profile.get("expiry", "")), status_text
            ))
        if not rows:
            rows = ["%s - BLAU = Web-Setup   |   GRÜN = URL" % tr("no_playlist")]
        self["list"].setList(rows)
        self["info"].setText("BLAU = Web-Setup   |   MENU = Hilfe   |   Schnellimport: %s" % PLAYLIST_TEXT_FILE)
        self._updateStatusSlots()

    def _visibleProfileStart(self):
        try:
            selected = int(self["list"].getSelectedIndex())
        except Exception:
            selected = 0
        total = len(self.profiles)
        if total <= 8:
            return 0
        return max(0, min(selected - 7 if selected >= 8 else 0, total - 8))

    def _updateStatusSlots(self):
        start = self._visibleProfileStart()
        for slot, name in enumerate(self._status_slots):
            widget = self[name]
            index = start + slot
            if index >= len(self.profiles):
                try:
                    widget.hide()
                except Exception:
                    pass
                continue
            _profile = self.profiles[index]
            status = clean_text(getattr(self, "_health_live", {}).get(_profile.get("id", ""), _profile.get("online_status", "")))
            icon = PLAYLIST_STATUS_ONLINE if status == "online" else (PLAYLIST_STATUS_OFFLINE if status == "offline" else "")
            try:
                if icon and os.path.isfile(icon) and widget.instance is not None:
                    widget.instance.setPixmapFromFile(icon)
                    widget.show()
                else:
                    widget.hide()
            except Exception:
                try:
                    widget.hide()
                except Exception:
                    pass

    def _startHealthJob(self):
        if self._health_job is not None and self._health_job.is_alive():
            return
        queue = [dict(p) for p in self.profiles if clean_text(p.get("m3u_url", "")) or clean_text(p.get("managed_file", ""))]
        if not queue:
            self._updateStatusSlots()
            return
        self._health_stop = False
        self._health_job = threading.Thread(target=self._healthWorker, args=(queue,))
        self._health_job.daemon = True
        self._health_job.start()
        try:
            self._health_timer.start(180, True)
        except TypeError:
            self._health_timer.start(180)

    def _publishHealthResult(self, result, completed):
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

    def _pollHealthJob(self):
        if self._health_changed:
            self._health_changed = False
            self.refreshList()
        if self._health_job is not None and self._health_job.is_alive() and not self._health_stop:
            try:
                self._health_timer.start(180, True)
            except TypeError:
                self._health_timer.start(180)
        else:
            self._health_job = None
            self.refreshList()

    def _stopHealthJob(self):
        self._health_stop = True
        try:
            self._health_timer.stop()
        except Exception:
            pass

    def _startExpiryJob(self):
        if self._expiry_job is not None and self._expiry_job.is_alive():
            return
        now = int(time.time())
        queue = []
        for profile in self.profiles:
            url = clean_text(profile.get("m3u_url", ""))
            if not url:
                continue
            # Only Xtream-style URLs can expose account expiry. Refresh an
            # already known value at most every 6 hours, but fetch missing
            # values immediately so a multi-playlist selector fills itself.
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            if not query.get("username") or not query.get("password"):
                continue
            try:
                checked = int(profile.get("expiry_checked_at", 0) or 0)
            except Exception:
                checked = 0
            if checked and (now - checked) < 6 * 60 * 60:
                continue
            queue.append((profile.get("id", ""), url))
        if not queue:
            return
        self._expiry_stop = False
        self._expiry_job = threading.Thread(target=self._expiryWorker, args=(queue,))
        self._expiry_job.daemon = True
        self._expiry_job.start()
        try:
            self._expiry_timer.start(300, True)
        except TypeError:
            self._expiry_timer.start(300)

    def _expiryWorker(self, queue):
        for profile_id, url in queue:
            if self._expiry_stop:
                break
            expiry = try_fetch_expiry(url)
            data = load_profiles()
            changed = False
            for profile in data.get("profiles", []):
                if profile.get("id") != profile_id:
                    continue
                # Do not write stale data if the URL was edited while this
                # background request was running.
                if clean_text(profile.get("m3u_url", "")) != clean_text(url):
                    break
                profile["expiry_checked_at"] = int(time.time())
                if expiry and clean_text(profile.get("expiry", "")) != expiry:
                    profile["expiry"] = expiry
                changed = True
                break
            if changed:
                save_profiles(data)
                self._expiry_changed = True

    def _pollExpiryJob(self):
        if self._expiry_changed:
            self._expiry_changed = False
            self.refreshList()
        if self._expiry_job is not None and self._expiry_job.is_alive() and not self._expiry_stop:
            try:
                self._expiry_timer.start(300, True)
            except TypeError:
                self._expiry_timer.start(300)
        else:
            self._expiry_job = None

    def _stopExpiryJob(self):
        self._expiry_stop = True
        try:
            self._expiry_timer.stop()
        except Exception:
            pass

    def selectedProfile(self):
        if not self.profiles:
            return None
        index = self["list"].getSelectedIndex()
        return self.profiles[index] if 0 <= index < len(self.profiles) else None

    def openSelected(self):
        profile = self.selectedProfile()
        if not profile:
            self.addProfile()
            return
        set_active_profile(profile["id"])
        self.close(profile["id"])

    def addProfile(self):
        self.session.openWithCallback(self.addNameEntered, VirtualKeyBoard, title="Name der Playlist", text="Playlist")

    def addNameEntered(self, name):
        name = clean_text(name)
        if not name:
            return
        self._new_name = name
        self.session.openWithCallback(self.addUrlEntered, VirtualKeyBoard, title="M3U-URL", text="")

    def addUrlEntered(self, url):
        if url is None:
            return
        profile = default_profile(self._new_name, clean_text(url))
        data = load_profiles()
        data["profiles"].append(profile)
        data["active_id"] = profile["id"]
        save_profiles(data)
        self.refreshList()

    def editSelected(self):
        profile = self.selectedProfile()
        if not profile:
            return
        if profile.get("managed_text_file"):
            self.session.open(
                MessageBox,
                "Diese Playlist wird über playlists.txt verwaltet.\n\nBitte per FTP/SFTP bearbeiten:\n%s\n\nFormat: M3U-PLUS-URL # Playlistname" % PLAYLIST_TEXT_FILE,
                MessageBox.TYPE_INFO,
                timeout=8
            )
            return
        self._edit_profile = dict(profile)
        self.session.openWithCallback(self.editNameEntered, VirtualKeyBoard, title="Playlist-Name ändern", text=profile.get("name", ""))

    def editNameEntered(self, name):
        name = clean_text(name)
        if not name:
            return
        self._edit_profile["name"] = name
        if self._edit_profile.get("managed_file"):
            update_profile(self._edit_profile)
            self.refreshList()
        else:
            self.session.openWithCallback(self.editUrlEntered, VirtualKeyBoard, title="M3U-URL ändern", text=self._edit_profile.get("m3u_url", ""))

    def editUrlEntered(self, url):
        if url is None:
            return
        self._edit_profile["m3u_url"] = clean_text(url)
        self._edit_profile["expiry"] = ""
        self._edit_profile["expiry_checked_at"] = 0
        self._edit_profile["online_status"] = ""
        self._edit_profile["online_checked_at"] = 0
        self._edit_profile["online_error"] = ""
        self._edit_profile["source_mode"] = "m3u"
        try:
            meta = xtream_meta_path(self._edit_profile.get("id", ""))
            if os.path.exists(meta):
                os.remove(meta)
        except Exception:
            pass
        update_profile(self._edit_profile)
        self.refreshList()

    def deleteSelected(self):
        profile = self.selectedProfile()
        if not profile:
            return
        self._delete_profile = profile
        if profile.get("managed_text_file"):
            note = "\nHinweis: Solange die Zeile in playlists.txt steht, wird die Playlist beim nächsten Start automatisch wieder eingelesen."
        elif profile.get("managed_file"):
            note = "\nDie hochgeladene M3U-Datei bleibt im FTP/SFTP-Ordner erhalten."
        else:
            note = ""
        self.session.openWithCallback(self.deleteConfirmed, MessageBox,
                                      "Playlist '%s' wirklich aus Epi MediaHub entfernen?%s" % (profile.get("name", "Playlist"), note),
                                      MessageBox.TYPE_YESNO)

    def deleteConfirmed(self, confirmed):
        if not confirmed:
            return
        profile = self._delete_profile
        data = load_profiles()
        data["profiles"] = [p for p in data.get("profiles", []) if p.get("id") != profile.get("id")]
        if data.get("active_id") == profile.get("id"):
            data["active_id"] = data["profiles"][0].get("id") if data["profiles"] else ""
        save_profiles(data)
        for path in (
            playlist_path(profile["id"]),
            playlist_index_path(profile["id"]),
            playlist_db_path(profile["id"]),
            favorites_path(profile["id"]),
            resume_path(profile["id"]),
            recent_path(profile["id"]),
            epg_xml_path(profile["id"]),
            epg_cache_path(profile["id"]),
            epg_quick_cache_path(profile["id"]),
            xtream_meta_path(profile["id"])
        ):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        self.refreshList()

    def openHelp(self):
        self.session.open(EpiHelpScreen)

    def scanFiles(self):
        added, updated = scan_local_playlists()
        self.refreshList()
        self.session.open(MessageBox, "Playlist-Quellen neu eingelesen.\nNeu: %d   Aktualisiert/entfernt: %d\n\n%s" % (added, updated, PLAYLIST_TEXT_FILE), MessageBox.TYPE_INFO, timeout=6)



MEDIATHEK_API_URL = "https://mediathekviewweb.de/api/query"
MEDIATHEK_DEBUG_LOG = "/tmp/epimediahub_mediathek.log"

def _mediathek_debug(event, detail=""):
    try:
        with open(MEDIATHEK_DEBUG_LOG, "a") as handle:
            handle.write("%s | %s | %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), clean_text(event), clean_text(detail)))
    except Exception:
        pass


def _mi(name):
    return os.path.join(MEDIATHEK_ICON_DIR,name+".png")

MEDIATHEK_COUNTRIES=[
    {"id":"de","label":"Deutschland","icon":_mi("country_de"),"meta":"ARD · ZDF · Dritte · ARTE · DW","info":"Die größte Auswahl: nationale Sender, Spartenprogramme und alle großen Regionalprogramme."},
    {"id":"at","label":"Österreich","icon":_mi("country_at"),"meta":"ORF","info":"ORF-Sendungen über MediathekView. Einzelne Titel können außerhalb Österreichs lizenzbedingt gesperrt sein."},
    {"id":"ch","label":"Schweiz","icon":_mi("country_ch"),"meta":"SRF","info":"SRF-Inhalte über MediathekView. Auslandsverfügbarkeit ist titelabhängig."},
    {"id":"it","label":"Italien","icon":_mi("country_it"),"meta":"RaiPlay","info":"Frei erreichbare Rai-Inhalte. Geo-Sperren werden nicht umgangen."},
    {"id":"tr","label":"Türkei","icon":_mi("country_tr"),"meta":"TRT · tabii","info":"TRT-Angebote für türkische Inhalte. Direkte Streams werden nur verwendet, wenn TRT sie am Standort ausliefert."},
    {"id":"fr","label":"Frankreich / International","icon":_mi("country_fr"),"meta":"ARTE France · TV5MONDEplus","info":"Französische und internationale Angebote. ARTE France ist direkt integriert; TV5MONDEplus wird als internationaler Anbieter ausgewiesen."}
]

MEDIATHEK_DIRS={
"de":[
 {"id":"ard","label":"ARD / Das Erste","kind":"mvw","channel":"ARD","icon":_mi("provider_ard"),"availability":"Deutschland · frei","info":"Sendungen aus der ARD Mediathek."},
 {"id":"zdf","label":"ZDF","kind":"mvw","channel":"ZDF","icon":_mi("provider_zdf"),"availability":"Deutschland · frei","info":"ZDF, ZDFneo und ZDFinfo über die ZDF-Mediathek."},
 {"id":"3sat","label":"3sat","kind":"mvw","channel":"3sat","icon":_mi("provider_3sat"),"availability":"D/A/CH · frei","info":"3sat-Mediathek."},
 {"id":"kika","label":"KiKA","kind":"mvw","channel":"KIKA","icon":_mi("provider_kika"),"availability":"Deutschland · frei","info":"Kinderprogramme aus der KiKA-Mediathek."},
 {"id":"phoenix","label":"PHOENIX","kind":"mvw","channel":"PHOENIX","icon":_mi("provider_phx"),"availability":"Deutschland · frei","info":"Dokumentationen, Politik und Ereignisse."},
 {"id":"arte_de","label":"ARTE Deutschland","kind":"mvw","channel":"ARTE.DE","icon":_mi("provider_arte"),"availability":"Deutschland · frei/teilweise","info":"ARTE-Angebot für Deutschland."},
 {"id":"dw","label":"Deutsche Welle","kind":"mvw","channel":"DW","icon":_mi("provider_dw"),"availability":"International","info":"Internationale DW-Mediathek."},
 {"id":"regional","label":"Deutsche Regionalprogramme","kind":"dir","target":"de_regional","icon":_mi("provider_reg"),"availability":"9 Mediatheken","info":"BR, HR, MDR, NDR, Radio Bremen, RBB, SR, SWR und WDR."},
 {"id":"tag","label":"Tagesschau","kind":"mvw","channel":"Tagesschau","icon":_mi("provider_tag"),"availability":"Deutschland · frei","info":"Nachrichten und Tagesschau-Angebote."}
],
"de_regional":[
 {"id":"br","label":"BR","kind":"mvw","channel":"BR","icon":_mi("provider_br"),"availability":"Bayern","info":"BR Mediathek."},
 {"id":"hr","label":"HR","kind":"mvw","channel":"HR","icon":_mi("provider_hr"),"availability":"Hessen","info":"HR Mediathek."},
 {"id":"mdr","label":"MDR","kind":"mvw","channel":"MDR","icon":_mi("provider_mdr"),"availability":"Mitteldeutschland","info":"MDR Mediathek."},
 {"id":"ndr","label":"NDR","kind":"mvw","channel":"NDR","icon":_mi("provider_ndr"),"availability":"Norddeutschland","info":"NDR Mediathek."},
 {"id":"rb","label":"Radio Bremen TV","kind":"mvw","channel":"Radio Bremen","icon":_mi("provider_rb"),"availability":"Bremen","info":"Radio Bremen Mediathek."},
 {"id":"rbb","label":"RBB","kind":"mvw","channel":"RBB","icon":_mi("provider_rbb"),"availability":"Berlin/Brandenburg","info":"RBB Mediathek."},
 {"id":"sr","label":"SR","kind":"mvw","channel":"SR","icon":_mi("provider_sr"),"availability":"Saarland","info":"SR Mediathek."},
 {"id":"swr","label":"SWR","kind":"mvw","channel":"SWR","icon":_mi("provider_swr"),"availability":"Südwesten","info":"SWR Mediathek."},
 {"id":"wdr","label":"WDR","kind":"mvw","channel":"WDR","icon":_mi("provider_wdr"),"availability":"NRW","info":"WDR Mediathek."}
],
"at":[{"id":"orf","label":"ORF","kind":"mvw","channel":"ORF","icon":_mi("provider_orf"),"availability":"Deutschland: teilweise","info":"ORF1, ORF2, ORF3 und ORF Sport. Einige Inhalte sind außerhalb Österreichs geogeblockt."}],
"ch":[{"id":"srf","label":"SRF","kind":"mvw","channel":"SRF","icon":_mi("provider_srf"),"availability":"Deutschland: teilweise","info":"SRF1, SRF2 und SRFinfo. Rechteabhängig können einzelne Beiträge gesperrt sein."}],
"fr":[
 {"id":"arte_fr","label":"ARTE France","kind":"mvw","channel":"ARTE.FR","icon":_mi("provider_arte"),"availability":"Deutschland: meist nutzbar","info":"Französisches ARTE-Angebot; einzelne Rechte können regional variieren."},
 {"id":"tv5","label":"TV5MONDEplus","kind":"info","icon":_mi("provider_tv5"),"availability":"International · kostenlos","info":"Internationales französischsprachiges Streaming-Angebot. Direkte native Wiedergabe wird nur aktiviert, wenn eine stabile offene Stream-Schnittstelle verfügbar ist."}
],
"it":[
 {"id":"rai","label":"RaiPlay International · freie Inhalte","kind":"rai","icon":_mi("provider_rai"),"availability":"Deutschland: titelabhängig","info":"Öffentlich erreichbare Rai-News/TGR-Inhalte. Keine Umgehung von Geo-Sperren."}
],
"tr":[
 {"id":"trt1","label":"TRT 1","kind":"trt","page":"https://www.trt1.com.tr/Canli-izle","icon":_mi("provider_trt"),"availability":"Deutschland: streamabhängig","info":"TRT 1. EpiMediaHub versucht nur offiziell ausgelieferte HLS-Streams zu verwenden."},
 {"id":"trthaber","label":"TRT Haber","kind":"trt","page":"https://www.trthaber.com/canli-yayin-izle.html","icon":_mi("provider_trt"),"availability":"International / streamabhängig","info":"TRT Haber Live, sofern der offizielle Webplayer einen offenen Stream liefert."},
 {"id":"tabii","label":"tabii","kind":"info","icon":_mi("provider_tabii"),"availability":"International · Konto/Region abhängig","info":"TRTs Streamingplattform für Serien, Filme und Dokumentationen. Vollzugriff und Preis/Verfügbarkeit hängen vom Land ab."}
]
}

RAI_TGR_URLS=[
 "https://www.raiplay.it/dl/RaiTV/programmi/json/liste/ContentSet-72f5c514-26b0-41d8-958e-cbb5e36c2c47-json-V-1.html",
 "https://www.raiplay.it/dl/RaiTV/programmi/json/liste/ContentSet-c210f09b-abbf-404a-abd5-1f524d6be645-json-V-1.html",
 "https://www.raiplay.it/dl/RaiTV/programmi/json/liste/ContentSet-85d08f9e-08f2-4cf3-86b3-2afaaee5fa83-json-V-1.html",
 "https://www.raiplay.it/dl/RaiTV/programmi/json/liste/ContentSet-f8905105-4b5c-4e6c-afed-e67b4703b50f-json-V-1.html"
]


def mediathek_copy(key):
    lang=current_app_language(); de={"label":"Mediathek","subtitle":"Mediatheken nach Ländern","search_all":"Alle Mediatheken durchsuchen","latest":"Neueste Beiträge","loading":"Beiträge werden geladen ...","play":"GRÜN  Abspielen","search":"GELB  Suche","reload":"BLAU  Neu laden","back":"ROT  Zurück","source":"Quelle: MediathekViewWeb","no_results":"Keine abspielbaren Beiträge gefunden.","search_title":"Mediathek durchsuchen"}
    return de.get(key,key)

def mediathek_label(): return mediathek_copy("label")

def _mediathek_duration(value):
    try: seconds=max(0,int(value or 0))
    except Exception: seconds=0
    h=seconds//3600; m=(seconds%3600)//60
    return ("%d:%02d Std."%(h,m)) if h else (("%d Min."%m) if m else "")

def _mediathek_date(value):
    try:
        stamp=int(value or 0); stamp=stamp//1000 if stamp>20000000000 else stamp
        return time.strftime("%d.%m.%Y",time.localtime(stamp)) if stamp>0 else ""
    except Exception: return ""

def _mediathek_episode_hint(title,topic):
    text="%s %s"%(clean_text(topic),clean_text(title))
    for pattern in (r'(?i)S(?:taffel)?\s*0*(\d+)\s*[/\- ]*E(?:pisode|p\.?|Folge)?\s*0*(\d+)',r'(?i)S(\d+)\s*[/\-]?E(\d+)',r'(?i)Staffel\s*(\d+).*?Folge\s*(\d+)'):
        m=re.search(pattern,text)
        if m: return "Staffel %d · Folge %d"%(int(m.group(1)),int(m.group(2)))
    return ""

def _mediathek_query(channel="",term="",offset=0,size=40):
    q=[]; channel=clean_text(channel); term=clean_text(term)
    if channel: q.append({"fields":["channel"],"query":channel})
    if term: q.append({"fields":["title","topic","description"],"query":term})
    body={"queries":q,"sortBy":"timestamp","sortOrder":"desc","future":False,"offset":int(offset or 0),"size":int(size or 40)}
    payload=json.dumps(body).encode("utf-8"); raw=None; err=None
    for ct in ("application/json","text/plain"):
        try:
            req=Request(MEDIATHEK_API_URL,data=payload); req.add_header("Content-Type",ct); req.add_header("Accept","application/json"); req.add_header("User-Agent","EpiMediaHub/%s"%PLUGIN_VERSION)
            r=urlopen(req,timeout=8); raw=r.read(); r.close(); break
        except Exception as e: err=e; raw=None
    if raw is None: raise Exception(str(err or "MediathekViewWeb nicht erreichbar"))
    text=raw if isinstance(raw,str) else raw.decode("utf-8","replace"); data=json.loads(text); rows=(data.get("result",{}) or {}).get("results",[])
    out=[]
    for item in rows:
        if not isinstance(item,dict): continue
        stream=clean_text(item.get("url_video_hd","")) or clean_text(item.get("url_video","")) or clean_text(item.get("url_video_low",""))
        if not stream: continue
        out.append({"title":clean_text(item.get("title","")) or clean_text(item.get("topic","")) or "Mediathek","topic":clean_text(item.get("topic","")),"channel":clean_text(item.get("channel","")),"description":clean_text(item.get("description","")),"duration":item.get("duration",0),"timestamp":item.get("timestamp",0),"url":stream,"url_website":clean_text(item.get("url_website","")),"type":"movie"})
    return out

def _media_abs_url(value, base="https://www.raiplay.it"):
    value=clean_text(value)
    if not value:return ""
    value=value.replace("[RESOLUTION]","600x-").replace(" ","%20")
    if value.startswith("//"):return "https:"+value
    if value.startswith("/"):return base.rstrip("/")+value
    if "://" not in value:return base.rstrip("/")+"/"+value.lstrip("/")
    if value.startswith("http://www.rai.tv/"):value="https://www.rai.tv/"+value[len("http://www.rai.tv/"):]
    return value

def _rai_duration(value):
    value=clean_text(value)
    if not value:return 0
    try:
        if value.isdigit():return int(value)
        parts=[int(x) for x in value.split(":")]
        if len(parts)==3:return parts[0]*3600+parts[1]*60+parts[2]
        if len(parts)==2:return parts[0]*60+parts[1]
    except Exception:pass
    return 0

def _rai_timestamp(value):
    value=clean_text(value)
    if not value:return 0
    for fmt in ("%d/%m/%Y","%d-%m-%Y","%Y-%m-%d"):
        try:return int(time.mktime(time.strptime(value,fmt)))
        except Exception:pass
    return 0

def _rai_image(item):
    candidates=[]
    images=item.get("images") if isinstance(item,dict) else None
    if isinstance(images,dict):
        for key in ("portrait","landscape","horizontal","square","hero","card"):
            candidates.append(images.get(key,""))
    for key in ("masterImage","image_433","image_300","image_medium","image","thumbnail","thumb","poster","imageUrl"):
        candidates.append(item.get(key,""))
    for value in candidates:
        if isinstance(value,dict):
            value=value.get("url","") or value.get("src","")
        value=_media_abs_url(value)
        if value:return value
    return ""

def _rai_query(term="",limit=45):
    out=[];seen=set()
    for source in RAI_TGR_URLS:
        try:
            req=Request(source);req.add_header("User-Agent","Mozilla/5.0 EpiMediaHub/%s"%PLUGIN_VERSION)
            r=urlopen(req,timeout=5);data=json.loads(r.read().decode("utf-8","replace"));r.close()
            for item in data.get("list",[]):
                if not isinstance(item,dict):continue
                title=clean_text(item.get("name","") or item.get("title","") or item.get("subtitle",""))
                topic=clean_text(item.get("from","")) or clean_text((item.get("isPartOf") or {}).get("name","")) or "Rai"
                date_text=clean_text(item.get("date",""))
                desc=clean_text(item.get("desc","") or item.get("description","") or item.get("synopsis","") or item.get("summary","") or item.get("subtitle","") or item.get("subtitle2",""))
                url=clean_text(item.get("m3u8","") or item.get("mediaUri","") or item.get("h264","") or item.get("videoUrl",""))
                if not title or not url:continue
                if term and term.lower() not in (title+" "+desc+" "+topic+" "+date_text).lower():continue
                if url in seen:continue
                seen.add(url)
                if not desc:
                    desc=("%s · %s%s"%(topic,title,(" · "+date_text) if date_text else "")).strip()
                page=_media_abs_url(item.get("weblink","") or item.get("PathID","") or item.get("pathID","") or item.get("pathId",""))
                out.append({"title":title,"topic":topic,"channel":"RAI","description":desc,"duration":_rai_duration(item.get("length","") or item.get("duration",0)),"timestamp":_rai_timestamp(date_text),"url":url,"url_website":page,"poster_url":_rai_image(item),"type":"movie"})
                if len(out)>=limit:return out
        except Exception:pass
    return out

def _page_hls(page):
    req=Request(page); req.add_header("User-Agent","Mozilla/5.0 (Linux; Enigma2) EpiMediaHub/%s"%PLUGIN_VERSION); r=urlopen(req,timeout=5); raw=r.read(1200000); r.close(); html=raw.decode("utf-8","replace")
    html=html.replace('\\/','/').replace('&amp;','&')
    m=re.search(r'https?://[^"\'<> ]+\.m3u8(?:\?[^"\'<> ]*)?',html,re.I)
    return clean_text(m.group(0)) if m else ""

def _html_meta_clean(value):
    value=clean_text(value).replace('&amp;','&').replace('&quot;','"').replace('&#39;',"'").replace('&apos;',"'")
    value=re.sub(r'<[^>]+>',' ',value)
    return re.sub(r'\s+',' ',value).strip()

def _mediathek_page_meta(page_url):
    page_url=clean_text(page_url)
    out={"image":"","description":"","title":""}
    if not page_url.startswith(("http://","https://")):return out
    try:
        req=Request(page_url);req.add_header("User-Agent","Mozilla/5.0 (Linux; Enigma2) EpiMediaHub/%s"%PLUGIN_VERSION);req.add_header("Accept","text/html,application/xhtml+xml")
        r=urlopen(req,timeout=4);raw=r.read(1200000);r.close();html=raw.decode("utf-8","replace")
        image_patterns=(
            r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::secure_url)?["\']',
            r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)',
            r'["\']thumbnailUrl["\']\s*:\s*["\']([^"\']+)',
            r'["\']image["\']\s*:\s*["\']([^"\']+)',
            r'["\']poster["\']\s*:\s*["\']([^"\']+)')
        for pat in image_patterns:
            m=re.search(pat,html,re.I)
            if m:
                image=_html_meta_clean(m.group(1))
                if image.startswith('//'):image='https:'+image
                elif image.startswith('/'):
                    u=urlparse(page_url);image='%s://%s%s'%(u.scheme,u.netloc,image)
                out["image"]=image;break
        desc_patterns=(
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']*)',
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)',
            r'["\']description["\']\s*:\s*["\']([^"\']{10,1200})')
        for pat in desc_patterns:
            m=re.search(pat,html,re.I|re.S)
            if m:
                out["description"]=_html_meta_clean(m.group(1));break
        title_patterns=(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']*)',r'<title[^>]*>(.*?)</title>')
        for pat in title_patterns:
            m=re.search(pat,html,re.I|re.S)
            if m:
                out["title"]=_html_meta_clean(m.group(1));break
    except Exception:pass
    return out

def _mediathek_fallback_icon(channel,source_kind,label=""):
    if source_kind=="rai":return _mi("provider_rai")
    text=(clean_text(channel)+" "+clean_text(label)).upper()
    mapping=(("ORF","provider_orf"),("SRF","provider_srf"),("ARTE","provider_arte"),("DW","provider_dw"),("ZDF","provider_zdf"),("ARD","provider_ard"),("3SAT","provider_3sat"),("KIKA","provider_kika"),("WDR","provider_wdr"),("NDR","provider_ndr"),("MDR","provider_mdr"),("SWR","provider_swr"),("RBB","provider_rbb"),("BR","provider_br"),("HR","provider_hr"),("SR ","provider_sr"))
    for needle,name in mapping:
        if needle in text:return _mi(name)
    return ""

def _set_pix(widget,path):
    try:
        if widget.instance is not None and path and os.path.isfile(path): widget.instance.setPixmapFromFile(path); widget.show(); return True
    except Exception: pass
    try: widget.hide()
    except Exception: pass
    return False

class EpiMediathekHome(Screen):
    noSkinReload=True
    skin=MEDIATHEK_HOME_SKIN
    def __init__(self,session):
        Screen.__init__(self,session); self._backing=False; self.items=list(MEDIATHEK_COUNTRIES); self["logo"]=Pixmap(); self["title"]=Label("Mediathek"); self["subtitle"]=Label("Nach Land / Nationalität auswählen"); self["list"]=MenuList([x["label"] for x in self.items]); self["provider_title"]=Label(""); self["provider_meta"]=Label(""); self["provider_info"]=Label(""); self["info"]=Label("OK = Land öffnen"); self["red"]=Label("ROT  Zurück"); self["green"]=Label("GRÜN  Öffnen"); self["yellow"]=Label(""); self["blue"]=Label("")
        for i in range(6): self["country_icon%d"%i]=Pixmap()
        self["actions"]=ActionMap(["OkCancelActions","DirectionActions","ColorActions"],{"ok":self.openSelected,"green":self.openSelected,"cancel":self.safeBack,"red":self.safeBack,"up":self.keyUp,"down":self.keyDown},-1)
        self.onLayoutFinish.append(self._layout)
    def _layout(self):
        for i,item in enumerate(self.items): _set_pix(self["country_icon%d"%i],item.get("icon",""))
        try: self["list"].onSelectionChanged.append(self.updateInfo)
        except Exception: pass
        self.updateInfo()
    def selected(self):
        try: i=int(self["list"].getSelectedIndex())
        except Exception: i=0
        return self.items[i] if 0<=i<len(self.items) else None
    def updateInfo(self):
        x=self.selected()
        if not x:return
        self["provider_title"].setText(x["label"]); self["provider_meta"].setText(x.get("meta","")); self["provider_info"].setText(x.get("info",""))
    def keyUp(self):
        try:self["list"].up()
        except Exception:pass
        self.updateInfo()
    def keyDown(self):
        try:self["list"].down()
        except Exception:pass
        self.updateInfo()
    def safeBack(self):
        if self._backing:return
        self._backing=True
        _mediathek_debug("home_back_begin","Mediathek")
        session=self.session
        try:
            _mediathek_debug("home_back_state","current=%s | in_exec=%s | stack=%s" % (
                session.current_dialog is self,
                getattr(session,"in_exec",None),
                len(getattr(session,"dialog_stack",[]) or [])
            ))
            if session.current_dialog is not self:
                raise RuntimeError("Mediathek home is not current dialog")
            if not getattr(session,"in_exec",False):
                raise RuntimeError("Session is not executing Mediathek home")
            if not getattr(session,"dialog_stack",None):
                raise RuntimeError("No parent dialog on stack")
            _mediathek_debug("home_back_execend_begin","Mediathek")
            session.execEnd()
            _mediathek_debug("home_back_execend_ok","Mediathek")
            session.popCurrent()
            _mediathek_debug("home_back_parent_ok","%s | %s" % (
                session.current_dialog.__class__.__name__ if session.current_dialog is not None else "None",
                getattr(session,"in_exec",None)
            ))
            return
        except Exception as error:
            _mediathek_debug("home_back_error","%s: %s" % (error.__class__.__name__,str(error)))
            self._backing=False

    def openSelected(self):
        x=self.selected()
        if not x:return
        try:
            dialog=self.session.instantiateDialog(EpiMediathekDirectory,x["id"],x["label"])
            self.session.execDialog(dialog)
            _mediathek_debug("directory_open_mode","persistent_exec | %s | %s" % (clean_text(x.get("id","")),clean_text(x.get("label",""))))
        except Exception as e:
            _mediathek_debug("directory_open_error",str(e))
            try:self.session.open(MessageBox,"Mediathek konnte nicht geöffnet werden:\n%s"%str(e),MessageBox.TYPE_ERROR,timeout=8)
            except Exception:pass

class EpiMediathekDirectory(Screen):
    noSkinReload=True
    skin=MEDIATHEK_DIRECTORY_SKIN
    def __init__(self,session,directory_id,title=None):
        Screen.__init__(self,session); self.directory_id=directory_id; self._backing=False; self.items=list(MEDIATHEK_DIRS.get(directory_id,[])); self["logo"]=Pixmap(); self["title"]=Label(title or "Mediathek"); self["subtitle"]=Label("Anbieter auswählen"); self["list"]=MenuList([x["label"] for x in self.items]); self["hero_icon"]=Pixmap(); self["provider_title"]=Label(""); self["provider_meta"]=Label(""); self["provider_info"]=Label(""); self["info"]=Label("OK = öffnen"); self["red"]=Label("ROT  Zurück"); self["green"]=Label("GRÜN  Öffnen"); self["yellow"]=Label(""); self["blue"]=Label("")
        for i in range(9): self["provider_icon%d"%i]=Pixmap()
        self["actions"]=ActionMap(["OkCancelActions","DirectionActions","ColorActions"],{"ok":self.openSelected,"green":self.openSelected,"cancel":self.safeBack,"red":self.safeBack,"up":self.keyUp,"down":self.keyDown},-1); self.onLayoutFinish.append(self._layout)
    def _layout(self):
        for i in range(9):
            if i<len(self.items): _set_pix(self["provider_icon%d"%i],self.items[i].get("icon",""))
            else:
                try:self["provider_icon%d"%i].hide()
                except Exception:pass
        try:self["list"].onSelectionChanged.append(self.updateInfo)
        except Exception:pass
        self.updateInfo()
    def selected(self):
        try:i=int(self["list"].getSelectedIndex())
        except Exception:i=0
        return self.items[i] if 0<=i<len(self.items) else None
    def updateInfo(self):
        x=self.selected()
        if not x:return
        _set_pix(self["hero_icon"],x.get("icon","")); self["provider_title"].setText(x["label"]); self["provider_meta"].setText(x.get("availability","")); self["provider_info"].setText(x.get("info",""))
    def keyUp(self):
        try:self["list"].up()
        except Exception:pass
        self.updateInfo()
    def keyDown(self):
        try:self["list"].down()
        except Exception:pass
        self.updateInfo()
    def safeBack(self):
        if self._backing:return
        self._backing=True
        detail="%s" % clean_text(self.directory_id)
        _mediathek_debug("directory_back_begin",detail)
        session=self.session
        try:
            _mediathek_debug("directory_back_state","current=%s | in_exec=%s | stack=%s" % (
                session.current_dialog is self,
                getattr(session,"in_exec",None),
                len(getattr(session,"dialog_stack",[]) or [])
            ))
            if session.current_dialog is not self:
                raise RuntimeError("Mediathek directory is not current dialog")
            if not getattr(session,"in_exec",False):
                raise RuntimeError("Session is not executing Mediathek directory")
            if not getattr(session,"dialog_stack",None):
                raise RuntimeError("No parent dialog on stack")
            _mediathek_debug("directory_back_execend_begin",detail)
            session.execEnd()
            _mediathek_debug("directory_back_execend_ok",detail)
            session.popCurrent()
            _mediathek_debug("directory_back_parent_ok","%s | %s" % (
                session.current_dialog.__class__.__name__ if session.current_dialog is not None else "None",
                getattr(session,"in_exec",None)
            ))
            return
        except Exception as error:
            _mediathek_debug("directory_back_error","%s: %s" % (error.__class__.__name__,str(error)))
            self._backing=False

    def openSelected(self):
        x=self.selected()
        if not x:return
        _mediathek_debug("provider_open", "%s | %s" % (clean_text(x.get("kind","")), clean_text(x.get("label",""))))
        self._open_item(x)
    def _open_item(self,x):
        kind=x.get("kind")
        if kind=="dir":
            try:
                dialog=self.session.instantiateDialog(EpiMediathekDirectory,x.get("target",""),x.get("label",""))
                self.session.execDialog(dialog)
                _mediathek_debug("directory_open_mode","persistent_exec | %s | %s" % (clean_text(x.get("target","")),clean_text(x.get("label",""))))
            except Exception as error:
                _mediathek_debug("directory_open_error",str(error))
            return
        if kind in ("mvw","rai"):
            try:
                dialog=self.session.instantiateDialog(EpiMediathekList,x.get("channel",""),x.get("label",""),"",kind)
                self.session.execDialog(dialog)
                _mediathek_debug("list_open_mode","persistent_exec | %s | %s" % (clean_text(kind),clean_text(x.get("label",""))))
            except Exception as error:
                _mediathek_debug("list_open_error",str(error))
                try:self.session.open(MessageBox,"Mediathek konnte nicht geöffnet werden:\n%s"%str(error),MessageBox.TYPE_ERROR,timeout=7)
                except Exception:pass
            return
        if kind=="trt":
            try:
                url=_page_hls(x.get("page",""))
                if not url: raise Exception("TRT liefert auf dieser Seite aktuell keinen direkt nutzbaren HLS-Stream aus.")
                _open_mediathek_stream(self.session,url,x.get("label","TRT"),"trt")
            except Exception as e:self.session.open(MessageBox,"TRT-Stream nicht verfügbar:\n%s"%str(e),MessageBox.TYPE_INFO,timeout=8)
            return
        self.session.open(MessageBox,"%s\n\n%s\n\n%s"%(x.get("label","Mediathek"),x.get("availability",""),x.get("info","")),MessageBox.TYPE_INFO,timeout=10)

if MoviePlayer is not None:
    class EpiMediathekPlayer(MoviePlayer):
        def __init__(self,session,service):
            MoviePlayer.__init__(self,session,service,fromMovieSelection=False)
            self["epimedia_mediathek_exit"]=ActionMap(
                ["MoviePlayerActions","OkCancelActions"],
                {
                    "leavePlayer":self.epiExit,
                    "leavePlayerOnExit":self.epiExit,
                    "cancel":self.epiExit
                },
                -10
            )
            _mediathek_debug("player_init", clean_text(service.getName()) if service is not None else "")

        def epiExit(self):
            _mediathek_debug("player_exit", "direct")
            try:self.session.nav.stopService()
            except Exception:pass
            self.close()
else:
    EpiMediathekPlayer=None


def _open_mediathek_stream(session,url,title="Mediathek",source=""):
    url=clean_text(url)
    title=clean_text(title) or "Mediathek"
    if not url:
        raise RuntimeError("Kein abspielbarer Stream gefunden.")
    ref=eServiceReference(1,0,url)
    ref.setName(title)
    _mediathek_debug("player_route","%s | %s" % (clean_text(source),title))
    if EpiMediathekPlayer is not None:
        session.open(EpiMediathekPlayer,ref)
        _mediathek_debug("play_opened_mediathek",title)
    else:
        session.nav.playService(ref)
        _mediathek_debug("play_started_nav",title)
    return True


class EpiMediathekList(Screen):
    noSkinReload=True
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
        _mediathek_debug("list_init", "%s | %s" % (self.source_kind, self.channel_label))

    def _timer_start(self,timer,delay):
        try:timer.stop()
        except Exception:pass
        try:timer.start(delay,True)
        except TypeError:timer.start(delay)
        except Exception:pass

    def _layout(self):
        _mediathek_debug("list_layout", "%s | %s" % (self.source_kind, self.channel_label))
        try:self["poster"].hide()
        except Exception:pass
        try:self["list"].onSelectionChanged.append(self._selectionChanged)
        except Exception:pass
        self.reload()

    def safeClose(self):
        # OpenATV 7.6 on the tested GigaBlue can enter a broken non-modal state
        # after the normal Screen/Session close path on this Mediathek list.
        # End the current dialog synchronously and pop the existing provider
        # directory from Session.dialog_stack instead.
        if self._closing:return
        self._closing=True
        detail="%s | %s" % (self.source_kind, self.channel_label)
        _mediathek_debug("list_back_begin", detail)
        try:self._load_timer.stop()
        except Exception as error:_mediathek_debug("load_timer_stop_error", str(error))
        try:self._poster_timer.stop()
        except Exception as error:_mediathek_debug("poster_timer_stop_error", str(error))
        session=self.session
        try:
            _mediathek_debug("list_back_state", "current=%s | in_exec=%s | stack=%s" % (
                session.current_dialog is self,
                getattr(session,"in_exec",None),
                len(getattr(session,"dialog_stack",[]) or [])
            ))
            if session.current_dialog is not self:
                raise RuntimeError("Mediathek list is not current dialog")
            if not getattr(session,"in_exec",False):
                raise RuntimeError("Session is not executing Mediathek list")
            if not getattr(session,"dialog_stack",None):
                raise RuntimeError("No parent dialog on stack")
            _mediathek_debug("list_back_execend_begin", detail)
            session.execEnd()
            _mediathek_debug("list_back_execend_ok", detail)
            session.popCurrent()
            _mediathek_debug("list_back_parent_ok", "%s | %s" % (
                session.current_dialog.__class__.__name__ if session.current_dialog is not None else "None",
                getattr(session,"in_exec",None)
            ))
            # The list was opened with instantiateDialog/execDialog and noSkinReload,
            # so Session no longer references it after popCurrent().  Avoid the
            # normal delayed close path here; Python can reclaim it later.
            return
        except Exception as error:
            _mediathek_debug("list_back_error", "%s: %s" % (error.__class__.__name__,str(error)))
            # Do not fall back to the normal Screen close path on this receiver.
            self._closing=False

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
        title=clean_text(entry.get("title","Mediathek"))
        _mediathek_debug("play_open","%s | %s | %s" % (self.source_kind,self.channel_label,title))
        try:
            _open_mediathek_stream(self.session,url,title,self.source_kind)
        except Exception as error:
            _mediathek_debug("play_open_error",str(error))
            try:self.session.open(MessageBox,"Wiedergabe fehlgeschlagen:\n%s"%str(error),MessageBox.TYPE_ERROR,timeout=7)
            except Exception:pass


class EpiMediaHubHome(Screen):
    skin = HOME_SKIN

    def __init__(self, session, profile_id):
        Screen.__init__(self, session)
        self.profile_id = profile_id
        self.tiles = [tr("live"), tr("movies"), tr("series"), mediathek_label(), tr("switch_playlist"), tr("settings")]
        self.currentIndex = 0
        self["logo"] = Pixmap()
        self["subtitle"] = Label("")
        self["hint"] = Label(tr("home_hint"))
        for index in range(len(self.tiles)):
            self["tile%d" % index] = Label("")
            self["mark%d" % index] = Label("")
        self["status"] = Label("")
        self["clock"] = Label("")
        self["weather_icon"] = Pixmap()
        self["weather"] = Label("")
        self["weather_detail"] = Label("")
        self["version"] = Label("v%s" % PLUGIN_VERSION)
        self["actions"] = ActionMap(
            ["OkCancelActions", "DirectionActions", "MenuActions"],
            {
                "ok": self.keyOK,
                "menu": self.openHelp,
                "cancel": self.requestExit,
                "left": self.keyLeft,
                "right": self.keyRight,
                "up": self.keyUp,
                "down": self.keyDown
            },
            -1
        )
        self._index_job = None
        self._index_result = None
        self._index_timer = eTimer()
        connect_timer(self._index_timer, self._pollIndexJob)

        # Automatic update checks are intentionally background-only.
        # The app checks at most once per 24 hours and asks before installation.
        self._auto_update_started = False
        self._auto_update_job = None
        self._auto_update_result = None
        self._auto_update_timer = eTimer()
        connect_timer(self._auto_update_timer, self._pollAutoUpdate)
        self._release_notes_checked = False

        # Lightweight background attempt to convert an existing M3U fallback
        # into Xtream FAST API mode. It inspects cached/redirect data only and
        # never parses the full playlist on the GUI thread.
        self._fast_recovery_started = False
        self._fast_recovery_job = None
        self._fast_recovery_result = None
        self._fast_recovery_timer = eTimer()
        connect_timer(self._fast_recovery_timer, self._pollFastRecovery)

        # EPG is automatic from v0.7.4 onward. It refreshes in the background
        # when missing or older than six hours and never blocks the home screen.
        self._auto_epg_job = None
        self._auto_epg_result = None
        self._auto_epg_profile_id = ""
        self._auto_epg_timer = eTimer()
        connect_timer(self._auto_epg_timer, self._pollAutoEpg)

        # Weather never blocks startup. Cached values paint immediately;
        # refreshes happen in a small background worker.
        self._weather_job = None
        self._weather_result = None
        self._weather_timer = eTimer()
        connect_timer(self._weather_timer, self._pollWeather)

        # Home clock is local to the receiver and refreshes exactly around the
        # next minute boundary without any network access.
        self._clock_timer = eTimer()
        connect_timer(self._clock_timer, self._updateHomeClock)

        self.onLayoutFinish.append(self.updateUI)
        self.onShown.append(self.refresh)
        self.onShown.append(self._showReleaseNotesIfNeeded)
        self.onShown.append(self._maybeStartAutoUpdate)
        self.onShown.append(self._maybeStartFastRecovery)
        self.onShown.append(self._maybeStartAutoEpg)
        self.onShown.append(self._maybeStartWeather)
        self.onShown.append(self._startHomeClock)
        try:
            self.onClose.append(self._stopHomeClock)
        except Exception:
            pass

    def _startHomeClock(self):
        self._updateHomeClock()

    def _stopHomeClock(self):
        try:
            self._clock_timer.stop()
        except Exception:
            pass

    def _updateHomeClock(self):
        try:
            self["clock"].setText(time.strftime("%H:%M"))
        except Exception:
            pass
        try:
            # Update shortly after the next minute starts.
            sec = int(time.localtime().tm_sec)
            delay = max(1000, (61 - sec) * 1000)
            self._clock_timer.start(delay, True)
        except TypeError:
            try:
                self._clock_timer.start(30000)
            except Exception:
                pass
        except Exception:
            pass

    def requestExit(self):
        self.session.openWithCallback(self._exitConfirmed, EpiExitConfirm)

    def _exitConfirmed(self, confirmed=False):
        if confirmed:
            self.close()

    def openHelp(self):
        self.session.open(EpiHelpScreen)

    def refresh(self):
        profile = get_profile(self.profile_id)
        if profile is None:
            data = load_profiles()
            profiles = data.get("profiles", [])
            if profiles:
                self.profile_id = profiles[0].get("id")
                set_active_profile(self.profile_id)
                profile = profiles[0]

        self.tiles = [tr("live"), tr("movies"), tr("series"), mediathek_label(), tr("switch_playlist"), tr("settings")]
        self["hint"].setText(tr("home_hint"))
        self["subtitle"].setText(
            "%s: %s" % (tr("playlist"), profile.get("name", "Playlist") if profile else tr("no_playlist"))
        )
        self.updateUI()
        self.updateStatus()
        self._paintWeather()

        if self.profile_id and playlist_index_needs_rebuild(self.profile_id):
            self._startIndexRebuild()

    def _startIndexRebuild(self):
        if self._index_job is not None and self._index_job.is_alive():
            return
        profile_id = self.profile_id
        self._index_result = None
        self["hint"].setText("%s …" % tr("playlist"))
        self._index_job = threading.Thread(target=self._indexWorker, args=(profile_id,))
        self._index_job.daemon = True
        self._index_job.start()
        try:
            self._index_timer.start(300, True)
        except TypeError:
            self._index_timer.start(300)

    def _indexWorker(self, profile_id):
        try:
            count = rebuild_playlist_index(profile_id)
            self._index_result = (True, profile_id, count, "")
        except Exception as error:
            self._index_result = (False, profile_id, 0, str(error))

    def _pollIndexJob(self):
        if self._index_job is not None and self._index_job.is_alive():
            try:
                self._index_timer.start(300, True)
            except TypeError:
                self._index_timer.start(300)
            return

        result = self._index_result
        self._index_job = None
        self._index_result = None
        self["hint"].setText(tr("home_hint"))
        self.updateStatus()

        if not result:
            return
        ok, profile_id, count, error = result
        if profile_id != self.profile_id:
            return
        if not ok and playlist_total_count(self.profile_id) <= 0:
            self.session.open(
                MessageBox,
                "Playlist konnte nicht vorbereitet werden:\n%s" % error,
                MessageBox.TYPE_ERROR,
                timeout=7
            )

    def _paintWeather(self):
        try:
            main, detail, icon = weather_display_parts()
            self["weather"].setText(main)
            self["weather_detail"].setText(detail)
            set_weather_icon(self["weather_icon"], icon)
        except Exception:
            self["weather"].setText("")
            self["weather_detail"].setText("")
            try:
                self["weather_icon"].hide()
            except Exception:
                pass

    def _maybeStartWeather(self, force=False):
        settings = load_global_settings()
        self._paintWeather()
        if not settings.get("weather_enabled", True):
            return
        if self._weather_job is not None and self._weather_job.is_alive():
            return
        if not force and weather_cache_fresh():
            return
        self._weather_result = None
        self._weather_job = threading.Thread(target=self._weatherWorker, args=(dict(settings),))
        self._weather_job.daemon = True
        self._weather_job.start()
        try:
            self._weather_timer.start(350, True)
        except TypeError:
            self._weather_timer.start(350)

    def _weatherWorker(self, settings):
        try:
            data = fetch_weather_snapshot(settings)
            self._weather_result = (True, data, "")
        except Exception as error:
            self._weather_result = (False, {}, str(error))

    def _pollWeather(self):
        if self._weather_job is not None and self._weather_job.is_alive():
            try:
                self._weather_timer.start(350, True)
            except TypeError:
                self._weather_timer.start(350)
            return
        self._weather_job = None
        self._weather_result = None
        self._paintWeather()

    def _maybeStartFastRecovery(self):
        if self._fast_recovery_started:
            return
        self._fast_recovery_started = True
        if db_source_mode(self.profile_id) == "xtream":
            return
        profile = get_profile(self.profile_id) or {}
        if not profile:
            return
        # Only try when there is a URL or an already cached/local M3U to inspect.
        if not profile.get("m3u_url") and not profile.get("managed_file") and not os.path.isfile(playlist_path(self.profile_id)):
            return
        self._fast_recovery_result = None
        self._fast_recovery_job = threading.Thread(target=self._fastRecoveryWorker, args=(dict(profile),))
        self._fast_recovery_job.daemon = True
        self._fast_recovery_job.start()
        try:
            self._fast_recovery_timer.start(400, True)
        except TypeError:
            self._fast_recovery_timer.start(400)

    def _fastRecoveryWorker(self, profile):
        try:
            if profile.get("managed_text_file"):
                # Zero-click import for playlists.txt: Xtream/M3U-Plus uses the
                # fast Player API, generic M3U falls back to a background download.
                count = download_playlist(profile)
            else:
                count = xtream_bootstrap(profile)
                if count is None:
                    self._fast_recovery_result = (False, profile, 0, "Keine Xtream-Zugangsdaten erkennbar")
                    return
            profile["last_update"] = time.strftime("%d.%m.%Y %H:%M")
            self._fast_recovery_result = (True, profile, int(count), "")
        except Exception as error:
            profile["fast_api_error"] = str(error)
            self._fast_recovery_result = (False, profile, 0, str(error))

    def _pollFastRecovery(self):
        if self._fast_recovery_job is not None and self._fast_recovery_job.is_alive():
            try:
                self._fast_recovery_timer.start(400, True)
            except TypeError:
                self._fast_recovery_timer.start(400)
            return
        result = self._fast_recovery_result
        self._fast_recovery_job = None
        self._fast_recovery_result = None
        if not result:
            return
        ok, profile, count, error = result
        update_profile(profile)
        if ok:
            if clean_text(profile.get("source_mode", "")) == "xtream":
                self["hint"].setText("FAST API automatisch erkannt – bereit")
            else:
                self["hint"].setText("Playlist automatisch geladen – bereit")
            self.updateStatus()
            self._maybeStartAutoEpg(force=True)
        else:
            # Stay silent in the home screen; Settings -> Datenmodus shows the reason.
            self.updateStatus()

    def _maybeStartAutoEpg(self, force=False):
        if not self.profile_id:
            return
        if self._auto_epg_job is not None and self._auto_epg_job.is_alive():
            return
        profile = get_profile(self.profile_id) or {}
        if not profile or not profile_epg_url(profile):
            return
        if not force and not auto_epg_due(self.profile_id):
            return
        self._auto_epg_profile_id = self.profile_id
        self._auto_epg_result = None
        snapshot = dict(profile)
        self._auto_epg_job = threading.Thread(target=self._autoEpgWorker, args=(snapshot,))
        self._auto_epg_job.daemon = True
        self._auto_epg_job.start()
        try:
            self._auto_epg_timer.start(500, True)
        except TypeError:
            self._auto_epg_timer.start(500)

    def _autoEpgWorker(self, profile):
        try:
            count = download_epg(profile)
            self._auto_epg_result = (True, profile.get("id", ""), int(count), "")
        except Exception as error:
            self._auto_epg_result = (False, profile.get("id", ""), 0, str(error))

    def _pollAutoEpg(self):
        if self._auto_epg_job is not None and self._auto_epg_job.is_alive():
            try:
                self._auto_epg_timer.start(500, True)
            except TypeError:
                self._auto_epg_timer.start(500)
            return
        result = self._auto_epg_result
        self._auto_epg_job = None
        self._auto_epg_result = None
        if result and result[0] and result[1] == self.profile_id:
            self.updateStatus()

    def _showReleaseNotesIfNeeded(self):
        if self._release_notes_checked:
            return
        self._release_notes_checked = True
        try:
            settings = load_global_settings()
            last_seen = clean_text(settings.get("last_seen_version", ""))
            if last_seen == PLUGIN_VERSION:
                return
            text = release_notes_text(PLUGIN_VERSION, last_seen)
            # Mark before opening the window so the same release notes cannot
            # loop if the home screen is shown again while the dialog closes.
            settings["last_seen_version"] = PLUGIN_VERSION
            save_global_settings(settings)
            if text:
                self.session.open(MessageBox, text, MessageBox.TYPE_INFO)
        except Exception:
            pass

    def _maybeStartAutoUpdate(self):
        if self._auto_update_started:
            return
        self._auto_update_started = True
        settings = load_global_settings()
        if not auto_update_check_due(settings):
            return

        # Mark the attempt immediately so a broken network does not cause a
        # fresh blocking/repeated check on every app start.
        mark_auto_update_check()
        url = clean_text(settings.get("update_manifest_url", ""))
        self._auto_update_result = None
        self._auto_update_job = threading.Thread(target=self._autoUpdateWorker, args=(url,))
        self._auto_update_job.daemon = True
        self._auto_update_job.start()
        try:
            self._auto_update_timer.start(500, True)
        except TypeError:
            self._auto_update_timer.start(500)

    def _autoUpdateWorker(self, url):
        try:
            manifest = fetch_update_manifest(url)
            remote = clean_text(manifest.get("version", ""))
            if not remote:
                raise Exception("Versionsnummer fehlt im Manifest.")
            if version_tuple(remote) > version_tuple(PLUGIN_VERSION):
                self._auto_update_result = (True, manifest, "")
            else:
                self._auto_update_result = (False, None, "")
        except Exception as error:
            # Background checks stay silent on network/manifest errors.
            self._auto_update_result = (False, None, str(error))

    def _pollAutoUpdate(self):
        if self._auto_update_job is not None and self._auto_update_job.is_alive():
            try:
                self._auto_update_timer.start(500, True)
            except TypeError:
                self._auto_update_timer.start(500)
            return

        result = self._auto_update_result
        self._auto_update_job = None
        self._auto_update_result = None
        if not result or not result[0]:
            return

        manifest = result[1]
        remote = clean_text(manifest.get("version", ""))
        self._pending_auto_update_manifest = manifest
        self.session.openWithCallback(
            self._autoUpdateConfirmed,
            MessageBox,
            "Epi MediaHub v%s ist verfügbar.\nJetzt installieren?" % remote,
            MessageBox.TYPE_YESNO
        )

    def _autoUpdateConfirmed(self, confirmed):
        if not confirmed:
            return
        manifest = getattr(self, "_pending_auto_update_manifest", None)
        if not manifest:
            return
        try:
            download_and_install_update(manifest)
            if TryQuitMainloop is not None:
                self.session.openWithCallback(
                    self._restartAfterAutoUpdate,
                    MessageBox,
                    "Update wurde installiert.\nEnigma2 jetzt neu starten?",
                    MessageBox.TYPE_YESNO
                )
            else:
                self.session.open(
                    MessageBox,
                    "Update installiert. Bitte die Enigma2-GUI neu starten.",
                    MessageBox.TYPE_INFO,
                    timeout=6
                )
        except Exception as error:
            self.session.open(
                MessageBox,
                "Update konnte nicht installiert werden:\n%s" % str(error),
                MessageBox.TYPE_ERROR,
                timeout=8
            )

    def _restartAfterAutoUpdate(self, confirmed):
        if confirmed and TryQuitMainloop is not None:
            self.session.open(TryQuitMainloop, 3)

    def updateUI(self):
        for index, name in enumerate(self.tiles):
            widget = self["tile%d" % index]
            marker = self["mark%d" % index]
            widget.setText(name)
            try:
                if index == self.currentIndex:
                    marker.show()
                else:
                    marker.hide()
            except Exception:
                pass
            if parseColor is not None:
                try:
                    # Do not set a semi-transparent widget background here. On
                    # OpenATV that can expose the OpenATV desktop artwork. The
                    # glass surface is a plugin-owned PNG overlay underneath.
                    if widget.instance is not None:
                        widget.instance.setForegroundColor(parseColor("#FFFFFF" if index == self.currentIndex else "#E8EEF6"))
                    if marker.instance is not None:
                        marker.instance.setBackgroundColor(parseColor(theme_accent()))
                except Exception:
                    pass

    def updateStatus(self):
        profile = get_profile(self.profile_id) or {}
        counts = playlist_counts(self.profile_id)
        epg_state = "bereit" if epg_cache_available(self.profile_id) else "nicht geladen"
        if db_source_mode(self.profile_id) == "xtream":
            self["status"].setText(
                "FAST API   |   EPG: Auto %s   |   Ablauf: %s" % ("bereit" if epg_state == "bereit" else "lädt/ausstehend", expiry_summary(profile.get("expiry", "")))
            )
        else:
            fast_error = clean_text(profile.get("fast_api_error", ""))
            prefix = "M3U-FALLBACK"
            if fast_error:
                prefix += "   |   FAST API nicht aktiv"
            self["status"].setText(
                "%s   |   Live %d   |   Filme %d   |   Serien %d   |   EPG %s   |   Ablauf: %s" % (
                    prefix, counts["live"], counts["movies"], counts["series"], epg_state, expiry_summary(profile.get("expiry", ""))
                )
            )

    def keyLeft(self):
        if self.currentIndex % 2 == 1:
            self.currentIndex -= 1
            self.updateUI()

    def keyRight(self):
        if self.currentIndex % 2 == 0 and self.currentIndex < len(self.tiles) - 1:
            self.currentIndex += 1
            self.updateUI()

    def keyUp(self):
        if self.currentIndex >= 2:
            self.currentIndex -= 2
            self.updateUI()

    def keyDown(self):
        if self.currentIndex <= 3:
            self.currentIndex += 2
            self.updateUI()

    def keyOK(self):
        if self.currentIndex == 0:
            self.openType("live")
        elif self.currentIndex == 1:
            self.openType("movies")
        elif self.currentIndex == 2:
            self.openType("series")
        elif self.currentIndex == 3:
            try:
                dialog=self.session.instantiateDialog(EpiMediathekHome); self.session.execDialog(dialog); _mediathek_debug("home_open_mode","persistent_exec")
            except Exception as error:
                try:
                    self.session.open(MessageBox, "Mediathek konnte nicht geöffnet werden:\n%s" % str(error), MessageBox.TYPE_ERROR, timeout=8)
                except Exception:
                    pass
        elif self.currentIndex == 4:
            self.session.openWithCallback(self.playlistSelected, EpiProfileSelect)
        elif self.currentIndex == 5:
            self.session.open(EpiSettings, self.profile_id)

    def playlistSelected(self, profile_id=None):
        if profile_id:
            self.profile_id = profile_id
            set_active_profile(profile_id)
            self.refresh()
            self._maybeStartAutoEpg()

    def openType(self, kind):
        if db_source_mode(self.profile_id) == "xtream":
            if not playlist_categories(self.profile_id, kind):
                self.session.open(MessageBox, tr("no_categories_kind", kind=type_label(kind)), MessageBox.TYPE_INFO, timeout=4)
                return
            self.session.open(EpiCategoryScreen, self.profile_id, kind)
            return

        if playlist_total_count(self.profile_id) <= 0:
            if self._index_job is not None and self._index_job.is_alive():
                self.session.open(MessageBox, "Die Playlist wird gerade im Hintergrund vorbereitet.\nBitte einen Moment warten.", MessageBox.TYPE_INFO, timeout=5)
            else:
                self.session.open(MessageBox, "Für diese Playlist wurden noch keine Daten geladen.\nÖffne Einstellungen und wähle GRÜN = Playlist laden.", MessageBox.TYPE_INFO, timeout=6)
            return
        if playlist_counts(self.profile_id).get(kind, 0) <= 0:
            self.session.open(MessageBox, tr("no_kind_entries", kind=type_label(kind)), MessageBox.TYPE_INFO, timeout=5)
            return
        self.session.open(EpiCategoryScreen, self.profile_id, kind)

    def globalSearch(self):
        if db_source_mode(self.profile_id) != "xtream" and playlist_total_count(self.profile_id) <= 0:
            self.session.open(MessageBox, "Noch keine Playlist geladen.", MessageBox.TYPE_INFO, timeout=4)
            return
        self.session.openWithCallback(
            self.globalSearchEntered,
            VirtualKeyBoard,
            title="%s / %s - %s" % (tr("movies"), tr("series"), tr("search")),
            text=""
        )

    def globalSearchEntered(self, query):
        if not query:
            return
        profile = get_profile(self.profile_id) or {}
        if db_source_mode(self.profile_id) == "xtream":
            try:
                xtream_load_kind(self.profile_id, "movies")
                xtream_load_kind(self.profile_id, "series")
            except Exception as error:
                self.session.open(MessageBox, tr("search_index_error", error=str(error)), MessageBox.TYPE_ERROR, timeout=6)
                return
        allowed = {
            "movies": set(allowed_category_names(profile, "movies", include_locked=False)),
            "series": set(allowed_category_names(profile, "series", include_locked=False)),
        }
        results = []
        for entry in playlist_entries(self.profile_id, query=query):
            kind = entry.get("type")
            if kind not in ("movies", "series"):
                continue
            group = clean_text(entry.get("group")) or "Ohne Kategorie"
            if group in allowed.get(kind, set()):
                results.append(entry)

        self.session.open(
            EpiContentScreen,
            self.profile_id,
            tr("search_results", query=query),
            results,
            "mixed",
            allowed
        )


class EpiCategoryScreen(Screen):
    skin = CATEGORY_SKIN

    def __init__(self, session, profile_id, kind):
        Screen.__init__(self, session)
        self.profile_id = profile_id
        self.kind = kind
        self.profile = get_profile(profile_id) or {}
        self.original_categories = []
        self.category_names = []
        self.category_counts = {}
        self.sort_mode = 0
        self._pending_locked_category = None
        self._load_job = None
        self._load_result = None
        self._pending_load = None
        self._load_timer = eTimer()
        connect_timer(self._load_timer, self._pollXtreamLoad)
        # Actor-category thumbnails are resolved lazily and only for visible
        # rows. Network work never runs in the Enigma2 UI thread.
        self._actor_job = None
        self._actor_queue = []
        self._actor_timer = eTimer()
        connect_timer(self._actor_timer, self._pollActorCategoryImages)
        # Do not decode/reload up to ten category images for every key-repeat
        # event. A short one-shot debounce lets native MenuList scrolling stay
        # responsive even on slower OpenATV receivers.
        self._category_icon_timer = eTimer()
        connect_timer(self._category_icon_timer, self._deferredCategoryPiconRefresh)
        self._category_icon_slot_paths = {}
        try:
            self._category_actor_images_enabled = bool(load_global_settings().get("actor_category_images", True))
        except Exception:
            self._category_actor_images_enabled = True

        self["logo"] = Pixmap()
        self["title"] = Label(type_label(kind))
        self["info"] = Label("%s   |   MENU = %s" % (tr("select_category"), tr("manage_categories")))
        self["list"] = MenuList([])
        self._category_picon_slots = []
        for _slot in range(10):
            _name = "category_picon%d" % _slot
            self[_name] = Pixmap()
            self._category_picon_slots.append(_name)
        self["red"] = Label("ROT  %s" % tr("back"))
        self["green"] = Label("GRÜN  %s" % tr("favorites"))
        self["yellow"] = Label("GELB  %s" % tr("search"))
        self["blue"] = Label("BLAU  A-Z")
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions", "MenuActions"],
            {
                "ok": self.openCategory,
                "cancel": self.close,
                "red": self.close,
                "green": self.openFavorites,
                "yellow": self.search,
                "blue": self.toggleSort,
                "menu": self.manageCategories,
            },
            -1
        )
        try:
            self["list"].onSelectionChanged.append(self._categorySelectionChanged)
        except Exception:
            pass
        self.onLayoutFinish.append(self._configureCategoryIcons)
        self.refreshRows()

    def _configureCategoryIcons(self):
        self._updateCategoryPiconStrip()

    def _scheduleCategoryPiconRefresh(self, delay=160):
        try:
            self._category_icon_timer.stop()
        except Exception:
            pass
        try:
            self._category_icon_timer.start(int(delay), True)
        except TypeError:
            self._category_icon_timer.start(int(delay))
        except Exception:
            pass

    def _deferredCategoryPiconRefresh(self):
        self._updateCategoryPiconStrip()

    def _categorySelectionChanged(self):
        self._scheduleCategoryPiconRefresh(160)

    def _categoryIconPath(self, category_name):
        if self.kind == "live":
            entry = first_cached_live_entry(self.profile_id, category_name)
            if entry:
                path = picon_local_file(entry)
                if path:
                    return path
            return HOME_ICONS[0]

        # VOD/series categories usually have no provider image of their own.
        # Recognise common platform names and show a compact local badge.
        # This is deliberately local/offline and does not require a TMDb key.
        name = clean_text(category_name).lower()
        if category_name in ("__all__", "__recent__"):
            return HOME_ICONS[1] if self.kind == "movies" else HOME_ICONS[2]
        rules = (
            (("netflix",), "netflix"),
            (("amazon", "prime video", "primevideo", "prime"), "prime"),
            (("disney+", "disney plus", "disney"), "disney"),
            (("paramount+", "paramount plus", "paramount"), "paramount"),
            (("apple tv+", "apple tv", "appletv"), "apple"),
            (("hbo max", "hbomax", "max"), "max"),
            (("sky",), "sky"),
            (("dazn",), "dazn"),
        )
        for aliases, key in rules:
            if any(alias in name for alias in aliases):
                path = CATEGORY_SERVICE_ICONS.get(key, "")
                if path and os.path.isfile(path):
                    return path

        # Saga / franchise folders have priority over generic VOD icons.
        # The actual network lookup is queued below; this lookup is cache-only.
        if _looks_like_saga_category(category_name):
            resolved, saga_path = saga_category_cache_record(category_name)
            if resolved and saga_path and os.path.isfile(saga_path):
                return saga_path

        # Actor folders: use a cached TMDb profile photo if already available.
        # Missing photos are queued by _updateCategoryPiconStrip and loaded in
        # the background; this function itself never performs network I/O.
        if getattr(self, "_category_actor_images_enabled", True):
            resolved, actor_path = actor_category_cache_record(category_name)
            if resolved and actor_path and os.path.isfile(actor_path):
                return actor_path
        return HOME_ICONS[1] if self.kind == "movies" else HOME_ICONS[2]

    def _restartActorTimer(self):
        try:
            self._actor_timer.start(300, True)
        except TypeError:
            self._actor_timer.start(300)

    def _queueActorCategoryImages(self, names):
        # Despite the historical method name this queue now handles both actor
        # portraits and Saga/collection artwork. It remains one small worker so
        # category scrolling never starts parallel network storms.
        if self.kind not in ("movies", "series"):
            return
        settings = load_global_settings()
        tmdb_ready = bool(clean_text(settings.get("tmdb_api_key", "")))
        actors_enabled = bool(settings.get("actor_category_images", True))
        for category_name in names:
            is_saga = _looks_like_saga_category(category_name)
            is_actor = actors_enabled and tmdb_ready and _looks_like_actor_category(category_name)
            if not is_saga and not is_actor:
                continue
            if is_saga:
                resolved, _path = saga_category_cache_record(category_name)
            else:
                resolved, _path = actor_category_cache_record(category_name)
            if resolved:
                continue
            if category_name not in self._actor_queue:
                self._actor_queue.append(category_name)
        if self._actor_job is None and self._actor_queue:
            batch = self._actor_queue[:6]
            del self._actor_queue[:len(batch)]
            self._actor_job = threading.Thread(target=self._actorCategoryWorker, args=(batch,))
            self._actor_job.daemon = True
            self._actor_job.start()
            self._restartActorTimer()

    def _actorCategoryWorker(self, names):
        for category_name in names:
            try:
                if _looks_like_saga_category(category_name):
                    resolve_saga_category_image(category_name)
                else:
                    resolve_actor_category_image(category_name)
            except Exception:
                pass

    def _pollActorCategoryImages(self):
        if self._actor_job is not None and self._actor_job.is_alive():
            self._restartActorTimer()
            return
        self._actor_job = None
        # Repaint after cached images arrived, but never compete with
        # an active remote-control scroll burst.
        self._scheduleCategoryPiconRefresh(80)
        if self._actor_queue:
            self._queueActorCategoryImages([])

    def _updateCategoryPiconStrip(self):
        icons_enabled = self.kind in ("live", "movies", "series")
        try:
            top = self["list"].getTopIndex()
            if top < 0:
                top = 0
        except Exception:
            try:
                current = self["list"].getSelectedIndex()
            except Exception:
                current = 0
            top = max(0, current - 4)
        visible_actor_candidates = []
        for slot, name in enumerate(getattr(self, "_category_picon_slots", [])):
            try:
                widget = self[name]
                idx = top + slot
                if not icons_enabled or idx >= len(self.category_names):
                    widget.hide()
                    continue
                category_name = self.category_names[idx]
                path = self._categoryIconPath(category_name)
                if path and os.path.isfile(path) and widget.instance is not None:
                    # setPixmapFromFile can be surprisingly expensive on small
                    # receivers. Reuse the pixmap already present in this slot.
                    if self._category_icon_slot_paths.get(name, "") != path:
                        widget.instance.setPixmapFromFile(path)
                        self._category_icon_slot_paths[name] = path
                    widget.show()
                else:
                    self._category_icon_slot_paths[name] = ""
                    widget.hide()
                if self.kind in ("movies", "series") and (
                    _looks_like_saga_category(category_name) or _looks_like_actor_category(category_name)
                ):
                    visible_actor_candidates.append(category_name)
            except Exception:
                pass
        if visible_actor_candidates:
            self._queueActorCategoryImages(visible_actor_candidates)

    def _restartLoadTimer(self):
        try:
            self._load_timer.start(250, True)
        except TypeError:
            self._load_timer.start(250)

    def _startXtreamLoad(self, mode, name="", allowed=None, query=""):
        if self._load_job is not None and self._load_job.is_alive():
            self["info"].setText(tr("loading_busy"))
            return
        self._pending_load = {
            "mode": mode,
            "name": name,
            "allowed": list(allowed or []),
            "query": query,
        }
        self._load_result = None
        if mode == "category":
            self["info"].setText(tr("loading_category", name=name))
        elif mode == "all":
            self["info"].setText(tr("loading_all", kind=type_label(self.kind)))
        else:
            self["info"].setText(tr("loading_search", kind=type_label(self.kind)))
        self._load_job = threading.Thread(
            target=self._xtreamLoadWorker,
            args=(self.profile_id, self.kind, mode, name)
        )
        self._load_job.daemon = True
        self._load_job.start()
        self._restartLoadTimer()

    def _xtreamLoadWorker(self, profile_id, kind, mode, name):
        try:
            if mode == "category":
                entries, cat_order = xtream_fetch_category_entries(profile_id, kind, name)
                self._load_result = (True, len(entries), "", entries, cat_order)
            else:
                count = xtream_load_kind(profile_id, kind)
                self._load_result = (True, count, "", None, 0)
        except Exception as error:
            self._load_result = (False, 0, str(error), None, 0)

    def _pollXtreamLoad(self):
        if self._load_job is not None and self._load_job.is_alive():
            self._restartLoadTimer()
            return
        result = self._load_result
        pending = self._pending_load or {}
        self._load_job = None
        self._load_result = None
        self._pending_load = None
        if not result:
            return
        if not result[0]:
            self["info"].setText("Laden fehlgeschlagen")
            self.session.open(
                MessageBox,
                tr("content_load_error", error=result[2]),
                MessageBox.TYPE_ERROR,
                timeout=7
            )
            return

        self.refreshRows()
        mode = pending.get("mode")
        allowed = pending.get("allowed") or allowed_category_names(
            get_profile(self.profile_id) or {}, self.kind, include_locked=False
        )
        if mode == "category":
            name = pending.get("name", "")
            items = result[3] if len(result) > 3 and isinstance(result[3], list) else []
            cat_order = result[4] if len(result) > 4 else 0
            if not items:
                items = playlist_entries(self.profile_id, kind=self.kind, group=name)
            else:
                cache_thread = threading.Thread(
                    target=xtream_cache_category_entries,
                    args=(self.profile_id, self.kind, name, list(items), cat_order)
                )
                cache_thread.daemon = True
                cache_thread.start()
            self._openItems(name, items, allowed)
        elif mode == "all":
            items = playlist_entries(self.profile_id, kind=self.kind, allowed_groups=allowed)
            self._openItems("%s %s" % (tr("all"), type_label(self.kind)), items, allowed)
        elif mode == "search":
            query = pending.get("query", "")
            items = playlist_entries(
                self.profile_id,
                kind=self.kind,
                query=query,
                allowed_groups=allowed
            )
            self._openItems(tr("search_results", query=query), items, allowed)

    def refreshRows(self):
        self.profile = get_profile(self.profile_id) or self.profile
        hidden = hidden_category_set(self.profile, self.kind)
        locked = effective_locked_category_set(self.profile, self.kind)

        records = []
        self.category_counts = {}
        for name, count in playlist_categories(self.profile_id, self.kind):
            self.category_counts[name] = count
            if name in hidden:
                continue
            records.append((name, count))

        self.original_categories = list(records)

        if self.sort_mode == 1:
            records = sorted(records, key=lambda item: item[0].lower())
        elif self.sort_mode == 2:
            records = sorted(records, key=lambda item: item[0].lower(), reverse=True)

        pseudo = ["__all__"]
        if self.kind in ("live", "movies", "series"):
            pseudo = ["__recent__", "__all__"]
        self.category_names = pseudo + [name for name, _count in records]

        allowed_for_all = [
            name for name, _count in records if name not in locked
        ]
        known_counts = [self.category_counts.get(name, -1) for name in allowed_for_all]
        all_known = all(value >= 0 for value in known_counts)
        all_count = sum(value for value in known_counts if value >= 0)

        # All three media category screens reserve room for the detached icon strip.
        indent = "             " if self.kind in ("live", "movies", "series") else ""
        rows = []
        if self.kind in ("live", "movies", "series"):
            recent_count = len(visible_recent_entries(self.profile_id, self.kind, self.profile, 40))
            rows.append("%s%s   (%d)" % (indent, tr("recent").upper(), recent_count))
        rows.append("%s%s   (%s)" % (indent, tr("all"), str(all_count) if all_known else "…"))
        for name, count in records:
            marker = " [PIN]" if name in locked else ""
            count_text = str(count) if count >= 0 else "…"
            rows.append("%s%s%s   (%s)" % (indent, name, marker, count_text))
        self["list"].setList(rows)
        self._scheduleCategoryPiconRefresh(60)
        self["info"].setText(tr("category_info", count=len(records)))

    def manageCategories(self):
        settings = load_global_settings()
        if settings.get("parental_enabled", False) and clean_text(settings.get("parental_pin_hash", "")):
            self.session.openWithCallback(
                self._managePinEntered,
                EpiPinScreen,
                "Kategorien verwalten - Kindersicherungs-PIN"
            )
            return
        self._openCategoryManager()

    def _managePinEntered(self, pin):
        if pin is None:
            return
        if not pin_matches(pin):
            self.session.open(MessageBox, "PIN ist falsch.", MessageBox.TYPE_ERROR, timeout=3)
            return
        self._openCategoryManager()

    def _openCategoryManager(self):
        self.session.openWithCallback(
            lambda *args: self.refreshRows(),
            EpiCategoryManager,
            self.profile_id,
            self.kind
        )

    def _openItems(self, title, items, search_allowed):
        if not items:
            self.session.open(MessageBox, tr("no_entries"), MessageBox.TYPE_INFO, timeout=3)
            return
        self.session.open(
            EpiContentScreen,
            self.profile_id,
            title,
            items,
            self.kind,
            search_allowed
        )

    def openCategory(self):
        index = self["list"].getSelectedIndex()
        if index < 0 or index >= len(self.category_names):
            return

        name = self.category_names[index]
        self.profile = get_profile(self.profile_id) or self.profile
        unlocked_allowed = allowed_category_names(self.profile, self.kind, include_locked=False)

        if name == "__recent__" and self.kind in ("live", "movies", "series"):
            items = visible_recent_entries(self.profile_id, self.kind, self.profile, 40)
            if not items:
                self.session.open(MessageBox, tr("no_recent"), MessageBox.TYPE_INFO, timeout=3)
                return
            self._openItems(tr("recent"), items, unlocked_allowed)
            return

        if name == "__all__":
            if db_source_mode(self.profile_id) == "xtream" and not load_xtream_meta(self.profile_id).get("full_loaded", {}).get(self.kind, False):
                self._startXtreamLoad("all", allowed=unlocked_allowed)
                return
            items = playlist_entries(
                self.profile_id,
                kind=self.kind,
                allowed_groups=unlocked_allowed
            )
            self._openItems("%s %s" % (tr("all"), type_label(self.kind)), items, unlocked_allowed)
            return

        locked = effective_locked_category_set(self.profile, self.kind)
        if name in locked:
            self._pending_locked_category = name
            self.session.openWithCallback(
                self._lockedPinEntered,
                EpiPinScreen,
                "Kindersicherung - PIN für %s" % name
            )
            return

        if db_source_mode(self.profile_id) == "xtream" and not xtream_category_loaded(self.profile_id, self.kind, name):
            self._startXtreamLoad("category", name=name, allowed=unlocked_allowed)
            return
        items = playlist_entries(self.profile_id, kind=self.kind, group=name)
        self._openItems(name, items, unlocked_allowed)

    def _lockedPinEntered(self, pin):
        name = self._pending_locked_category
        self._pending_locked_category = None
        if not name:
            return
        if not pin or not pin_matches(pin):
            if pin is not None:
                self.session.open(MessageBox, "PIN ist falsch.", MessageBox.TYPE_ERROR, timeout=3)
            return

        self.profile = get_profile(self.profile_id) or self.profile
        allowed = allowed_category_names(self.profile, self.kind, include_locked=False)
        if name not in allowed:
            allowed.append(name)
        if db_source_mode(self.profile_id) == "xtream" and not xtream_category_loaded(self.profile_id, self.kind, name):
            self._startXtreamLoad("category", name=name, allowed=allowed)
            return
        items = playlist_entries(self.profile_id, kind=self.kind, group=name)
        self._openItems(name, items, allowed)

    def openFavorites(self):
        self.profile = get_profile(self.profile_id) or self.profile
        allowed = set(allowed_category_names(self.profile, self.kind, include_locked=False))
        favorites = []
        for entry in favorite_entries(self.profile_id):
            if entry.get("type") != self.kind:
                continue
            group = clean_text(entry.get("group")) or "Ohne Kategorie"
            if group in allowed:
                favorites.append(entry)

        if not favorites:
            self.session.open(
                MessageBox,
                tr("no_favorites", kind=type_label(self.kind)),
                MessageBox.TYPE_INFO,
                timeout=4
            )
            return

        self._openItems(
            tr("favorites_kind", kind=type_label(self.kind)),
            favorites,
            list(allowed)
        )

    def search(self):
        self.session.openWithCallback(
            self.searchEntered,
            VirtualKeyBoard,
            title="%s - %s" % (type_label(self.kind), tr("search_area")),
            text=""
        )

    def searchEntered(self, query):
        if not query:
            return
        self.profile = get_profile(self.profile_id) or self.profile
        allowed = allowed_category_names(self.profile, self.kind, include_locked=False)
        if db_source_mode(self.profile_id) == "xtream" and not load_xtream_meta(self.profile_id).get("full_loaded", {}).get(self.kind, False):
            self._startXtreamLoad("search", allowed=allowed, query=query)
            return
        results = playlist_entries(
            self.profile_id,
            kind=self.kind,
            query=query,
            allowed_groups=allowed
        )
        self._openItems(
            tr("search_results", query=query),
            results,
            allowed
        )

    def toggleSort(self):
        self.sort_mode = (self.sort_mode + 1) % 3
        if self.sort_mode == 0:
            self["blue"].setText("BLAU  A-Z")
        elif self.sort_mode == 1:
            self["blue"].setText("BLAU  Z-A")
        else:
            self["blue"].setText("BLAU  Original")
        self.refreshRows()


class EpiCategoryManager(Screen):
    skin = CATEGORY_MANAGER_SKIN

    def __init__(self, session, profile_id, kind):
        Screen.__init__(self, session)
        self.profile_id = profile_id
        self.kind = kind
        self.profile = ensure_profile_category_maps(get_profile(profile_id) or {})
        self.categories = playlist_categories(profile_id, kind)

        self["logo"] = Pixmap()
        self["title"] = Label("%s - KATEGORIEN" % type_label(kind))
        self["info"] = Label("[X] = ausgeblendet   |   [PIN] = manuell gesperrt   |   18+ wird automatisch erkannt")
        self["list"] = MenuList([])
        self["red"] = Label("ROT  Fertig")
        self["green"] = Label("GRÜN  PIN-Sperre")
        self["yellow"] = Label("GELB  Sichtbar/Aus")
        self["blue"] = Label("BLAU  Alle zeigen")
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions"],
            {
                "ok": self.toggleVisible,
                "cancel": self.finish,
                "red": self.finish,
                "green": self.toggleLock,
                "yellow": self.toggleVisible,
                "blue": self.showAll,
            },
            -1
        )
        self.refreshRows()

    def currentName(self):
        index = self["list"].getSelectedIndex()
        if 0 <= index < len(self.categories):
            return self.categories[index][0]
        return ""

    def refreshRows(self):
        hidden = hidden_category_set(self.profile, self.kind)
        manual_locked = manual_locked_category_set(self.profile, self.kind)
        rows = []
        for name, count in self.categories:
            hidden_marker = "[X]" if name in hidden else "[ ]"
            lock_marker = " [PIN]" if name in manual_locked else ""
            adult_marker = " [18+]" if is_adult_category(name) else ""
            count_text = str(count) if count >= 0 else "…"
            rows.append("%s %s%s%s   (%s)" % (
                hidden_marker, name, lock_marker, adult_marker, count_text
            ))
        self["list"].setList(rows)

    def _save(self):
        update_profile(self.profile)
        self.refreshRows()

    def toggleVisible(self):
        name = self.currentName()
        if not name:
            return
        hidden = self.profile["hidden_categories"].setdefault(self.kind, [])
        if name in hidden:
            hidden.remove(name)
        else:
            hidden.append(name)
        self._save()

    def toggleLock(self):
        name = self.currentName()
        if not name:
            return
        locked = self.profile["locked_categories"].setdefault(self.kind, [])
        if name in locked:
            locked.remove(name)
        else:
            locked.append(name)
        self._save()

    def showAll(self):
        self.profile["hidden_categories"][self.kind] = []
        self._save()

    def finish(self):
        update_profile(self.profile)
        self.close(True)


class EpiSeasonScreen(Screen):
    skin = SEASON_SKIN

    def __init__(self, session, profile_id, series_title, season_groups):
        Screen.__init__(self, session)
        self.profile_id = profile_id
        self.series_title = clean_text(series_title) or tr("series")
        self.season_groups = [group for group in (season_groups or []) if group.get("episodes")]

        self["logo"] = Pixmap()
        self["title"] = Label(self.series_title)
        self["info"] = Label(tr("season_select"))
        self["list"] = MenuList([])
        self["red"] = Label("ROT  %s" % tr("back"))
        self["green"] = Label("")
        self["yellow"] = Label("")
        self["blue"] = Label("")
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions"],
            {
                "ok": self.openSeason,
                "cancel": self.close,
                "red": self.close,
            },
            -1
        )
        self.refreshRows()

    def refreshRows(self):
        rows = []
        for group in self.season_groups:
            count = len(group.get("episodes", []))
            label = clean_text(group.get("label", ""))
            season_number = group.get("season")
            if season_number == 0:
                label = tr("specials")
            elif season_number is None:
                label = tr("more_episodes")
            elif season_number is not None:
                label = "%s %d" % (tr("season"), int(season_number))
            rows.append("%s   (%d %s)" % (label, count, tr("episode") if count == 1 else tr("episodes")))
        self["list"].setList(rows)
        self["info"].setText(tr("season_info", count=len(rows)))

    def openSeason(self):
        try:
            index = self["list"].getSelectedIndex()
        except Exception:
            index = -1
        if index < 0 or index >= len(self.season_groups):
            return
        group = self.season_groups[index]
        episodes = list(group.get("episodes", []))
        if not episodes:
            self.session.open(MessageBox, tr("season_empty"), MessageBox.TYPE_INFO, timeout=3)
            return
        title = "%s - %s" % (self.series_title, clean_text(group.get("label", "Staffel")))
        self.session.open(
            EpiContentScreen,
            self.profile_id,
            title,
            episodes,
            "series",
            [self.series_title]
        )


class EpiContentScreen(Screen):
    skin = CONTENT_SKIN

    def __init__(self, session, profile_id, title, visible_items, kind, search_allowed_groups=None):
        Screen.__init__(self, session)
        self.profile_id = profile_id
        self.kind = kind
        self.visible_items = list(visible_items or [])
        self.original_items = list(self.visible_items)
        self.search_allowed_groups = search_allowed_groups
        self._is_recent_view = clean_text(title) == clean_text(tr("recent"))
        self.sort_mode = 0

        self["logo"] = Pixmap()
        self["title"] = Label(title)
        self["info"] = Label("")
        # IMPORTANT: keep Live-TV on the stock MenuList/eListboxPythonStringContent.
        # The custom eListboxPythonMultiContent introduced for inline Picons was
        # the only structural change that coincided with the broken UP/DOWN
        # navigation on OpenATV 7.5.x.  Picons are now drawn in separate Pixmap
        # slots instead of changing the list content class.
        self._multi_live = False
        self["list"] = MenuList([])
        self._live_picon_slots = []
        for _slot in range(10):
            name = "live_picon%d" % _slot
            self[name] = Pixmap()
            self._live_picon_slots.append(name)
        self["preview_panel"] = Label("")
        self["preview_poster"] = Pixmap()
        self["preview_title"] = Label("")
        self["preview_meta"] = Label("")
        self["preview_overview"] = Label("")
        self._preview_decoder = None
        self._media_preview_job = None
        self._media_preview_result = None
        self._media_preview_token = None
        self._media_preview_timer = eTimer()
        connect_timer(self._media_preview_timer, self._mediaPreviewTimerFired)
        self._live_preview_job = None
        self._live_preview_result = None
        self._live_preview_window = None
        self._live_preview_timer = eTimer()
        connect_timer(self._live_preview_timer, self._pollLivePreview)
        self["red"] = Label("ROT  %s" % tr("back"))
        self["green"] = Label("GRÜN  %s" % tr("favorite"))
        self["yellow"] = Label("GELB  %s" % tr("search"))
        self["blue"] = Label("BLAU  %s" % tr("sort"))
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions", "NumberActions", "InfoActions", "InfobarEPGActions"],
            {
                "ok": self.playCurrent,
                "cancel": self.close,
                "red": self.close,
                "green": self.toggleFavorite,
                "yellow": self.search,
                "blue": self.sortItems,
                "0": self.showDetails,
                "info": self.showDetails,
                "showEventInfo": self.showDetails,
                "EPGPressed": self.showGrid
            },
            -1
        )
        try:
            self.onClose.append(self.cleanup)
        except Exception:
            pass
        try:
            self["list"].onSelectionChanged.append(self._selectionChanged)
        except Exception:
            pass
        self.onLayoutFinish.append(self._configureContentLayout)
        self.refreshRows()

    def _configureContentLayout(self):
        media = self.kind in ("movies", "series")
        if self.kind == "live":
            try:
                if self["list"].instance is not None:
                    self["list"].instance.setSelectionEnable(True)
            except Exception:
                pass
        try:
            if eSize is not None and self["list"].instance is not None:
                self["list"].instance.resize(eSize(sx(530 if media else 1140), sy(460)))
        except Exception:
            pass
        for name in ("preview_panel", "preview_poster", "preview_title", "preview_meta", "preview_overview"):
            try:
                (self[name].show if media else self[name].hide)()
            except Exception:
                pass
        for name in getattr(self, "_live_picon_slots", []):
            try:
                (self[name].show if self.kind == "live" else self[name].hide)()
            except Exception:
                pass
        if self.kind == "live":
            # Explicitly give the stock list focus. This is the same list class
            # that worked before inline Picons were introduced.
            try:
                self.setFocus(self["list"])
            except Exception:
                pass
            self._updateLivePiconStrip()
            self._scheduleLivePreview(180)
        elif media:
            self._scheduleMediaPreview(120)

    def _selectionChanged(self):
        self._last_selection_change = time.time()
        if self.kind == "live":
            self._updateLivePiconStrip()
            self._scheduleLivePreview(260)
        elif self.kind in ("movies", "series"):
            self._scheduleMediaPreview(180)

    def _updateLivePiconStrip(self):
        """Render cached Picons beside the normal MenuList without replacing it."""
        if self.kind != "live":
            return
        try:
            top = self["list"].getTopIndex()
            if top < 0:
                top = 0
        except Exception:
            try:
                current = self["list"].getSelectedIndex()
            except Exception:
                current = 0
            top = max(0, current - 4)
        for slot, name in enumerate(getattr(self, "_live_picon_slots", [])):
            idx = top + slot
            try:
                widget = self[name]
                if idx >= len(self.visible_items):
                    widget.hide()
                    continue
                path = picon_local_file(self.visible_items[idx])
                if path and os.path.isfile(path) and widget.instance is not None:
                    try:
                        widget.instance.setPixmapFromFile(path)
                        widget.show()
                    except Exception:
                        widget.hide()
                else:
                    widget.hide()
            except Exception:
                pass

    def cleanup(self):
        try:
            self._live_preview_timer.stop()
        except Exception:
            pass
        try:
            self._media_preview_timer.stop()
        except Exception:
            pass
        self._media_preview_token = None
        self.visible_items = []
        self.original_items = []
        self.search_allowed_groups = None

    def _liveRowEpgText(self, entry):
        current, next_item = epg_now_next_quick(self.profile_id, entry)
        if current:
            return "JETZT %s-%s  %s" % (format_clock(current.get("start")), format_clock(current.get("stop")), clean_text(current.get("title", "")))
        if next_item:
            return "AB %s  %s" % (format_clock(next_item.get("start")), clean_text(next_item.get("title", "")))
        return "EPG wird automatisch geladen …"

    def refreshRows(self):
        try:
            selected = self["list"].getSelectedIndex()
        except Exception:
            selected = 0
        favs = favorite_keys(self.profile_id)
        rows = []
        detected_kind = ""
        if self.visible_items:
            detected_kind = self.visible_items[0].get("type", "")
        for entry in self.visible_items:
            prefix = "* " if entry.get("url", "") in favs else ""
            title = prefix + (entry.get("recent_title") or entry.get("title", "Unbenannt"))
            if detected_kind == "live" and entry_catchup_days(entry) > 0:
                title += "  [REPLAY]"
            if detected_kind == "live":
                epg_text = self._liveRowEpgText(entry)
                # Keep the normal string list so OpenATV owns navigation again.
                # Leading space leaves room for the independent Picon strip.
                rows.append("             %s   |   %s" % (title, epg_text))
            else:
                rows.append(title)
        self["list"].setList(rows)
        if rows:
            try:
                self["list"].moveToIndex(max(0, min(selected, len(rows) - 1)))
            except Exception:
                pass
        if detected_kind == "live":
            self._updateLivePiconStrip()
        extra = "INFO/0 = EPG" if detected_kind == "live" else "INFO/0 = %s" % tr("movie_info")
        if detected_kind == "live":
            extra += "   |   EPG-Taste = Raster   |   EPG + Picons automatisch"
        self["info"].setText("%d %s   |   * = %s   |   %s" % (len(self.visible_items), tr("entries"), tr("favorite"), extra))

    def _kickLivePreview(self):
        if self.kind != "live" or not self.visible_items:
            return
        try:
            index = self["list"].getSelectedIndex()
        except Exception:
            index = 0
        start = max(0, index - 4)
        end = min(len(self.visible_items), index + 14)
        window = (start, end)
        if self._live_preview_job is not None and self._live_preview_job.is_alive():
            self._scheduleLivePreview(350)
            return
        # Revisit the same window periodically, because the automatic XMLTV
        # cache may have finished in the meantime even if short EPG was absent.
        self._live_preview_window = window
        entries = [dict(item) for item in self.visible_items[start:end]]
        self._live_preview_result = None
        self._live_preview_job = threading.Thread(target=self._livePreviewWorker, args=(entries,))
        self._live_preview_job.daemon = True
        self._live_preview_job.start()
        self._scheduleLivePreview(250)

    def _scheduleLivePreview(self, delay=700):
        try:
            self._live_preview_timer.start(int(delay), True)
        except TypeError:
            self._live_preview_timer.start(int(delay))

    def _livePreviewWorker(self, entries):
        meta = load_xtream_meta(self.profile_id)
        use_xtream = meta.get("source") == "xtream"
        def one(entry):
            # Picon and per-channel short EPG are deliberately lazy: only the
            # currently visible window is touched.
            ensure_picon_file(entry)
            if use_xtream and not epg_now_next_quick(self.profile_id, entry)[0]:
                try:
                    xtream_short_epg(self.profile_id, entry, limit=6, force=False)
                except Exception:
                    pass
            return True
        try:
            if ThreadPoolExecutor is not None:
                with ThreadPoolExecutor(max_workers=4) as executor:
                    list(executor.map(one, entries))
            else:
                for entry in entries:
                    one(entry)
            self._live_preview_result = True
        except Exception:
            self._live_preview_result = False

    def _pollLivePreview(self):
        if self.kind != "live":
            return
        if self._live_preview_job is not None and self._live_preview_job.is_alive():
            self._scheduleLivePreview(250)
            return
        had_result = self._live_preview_result is not None
        self._live_preview_job = None
        self._live_preview_result = None
        # Only rebuild rows when fresh EPG/picon data actually arrived.
        # Rebuilding every ~850 ms could fight remote-control navigation.
        if had_result:
            # Do not rebuild the multi-content list while the user is actively
            # moving through it. Native eListbox navigation stays in control.
            if time.time() - getattr(self, "_last_selection_change", 0) > 0.45:
                self.refreshRows()
            else:
                self._scheduleLivePreview(320)
                return
        try:
            index = self["list"].getSelectedIndex()
        except Exception:
            index = 0
        start = max(0, index - 4)
        end = min(len(self.visible_items), index + 14)
        if self._live_preview_window != (start, end):
            self._kickLivePreview()
        else:
            self._scheduleLivePreview(850)

    def _mediaPreviewTimerFired(self):
        if self._media_preview_job is not None:
            self._pollMediaPreview()
        else:
            self._startMediaPreview()

    def _scheduleMediaPreview(self, delay=180):
        if self.kind not in ("movies", "series"):
            return
        try:
            self._media_preview_timer.start(int(delay), True)
        except TypeError:
            self._media_preview_timer.start(int(delay))

    def _previewMetaText(self, metadata):
        metadata = metadata or {}
        parts = []
        release = clean_text(metadata.get("release", ""))
        if release:
            parts.append("Jahr: %s" % release[:4])
        runtime = int(metadata.get("runtime", 0) or 0)
        if runtime:
            parts.append("Laufzeit: %d Min." % runtime)
        rating = _safe_float(metadata.get("rating", 0))
        if rating:
            parts.append("Bewertung: %.1f / 10" % rating)
        genres = metadata.get("genres", []) or []
        if genres:
            parts.append("Genre: %s" % ", ".join(genres[:3]))
        return "\n".join(parts)

    def _applyMediaPreview(self, metadata, loading=False):
        metadata = metadata or {}
        self["preview_title"].setText(clean_text(metadata.get("title", "")) or "Filminfo")
        self["preview_meta"].setText(self._previewMetaText(metadata))
        overview = clean_text(metadata.get("overview", ""))
        if not overview and loading:
            overview = "Filminfos werden geladen …"
        elif not overview:
            overview = "Keine Beschreibung verfügbar."
        self["preview_overview"].setText("Beschreibung:\n%s" % overview)

    def _showPreviewPoster(self, path):
        if not path or ePicLoad is None:
            return
        try:
            self._preview_decoder = ePicLoad()
            try:
                self._preview_decoder.PictureData.get().append(self._previewPosterDecoded)
            except Exception:
                try:
                    self._preview_decoder.PictureData.connect(self._previewPosterDecoded)
                except Exception:
                    return
            self._preview_decoder.setPara((sx(235), sy(340), 1, 1, False, 1, "#00000000"))
            result = self._preview_decoder.startDecode(path)
            if result not in (None, 0):
                _image_log("ePicLoad preview startDecode result=%s file=%s" % (result, path))
        except Exception as error:
            _image_log("ePicLoad preview exception file=%s error=%s" % (path, error))

    def _previewPosterDecoded(self, *args):
        try:
            ptr = self._preview_decoder.getData() if self._preview_decoder is not None else None
            if ptr is not None and self["preview_poster"].instance is not None:
                self["preview_poster"].instance.setPixmap(ptr)
                self["preview_poster"].show()
            elif ptr is None:
                _image_log("ePicLoad preview decoded no pixmap")
        except Exception as error:
            _image_log("ePicLoad preview callback error=%s" % error)

    def _startMediaPreview(self):
        if self.kind not in ("movies", "series") or not self.visible_items:
            return
        try:
            index = self["list"].getSelectedIndex()
        except Exception:
            index = 0
        if index < 0 or index >= len(self.visible_items):
            return
        entry = dict(self.visible_items[index])
        token = "%d|%s" % (index, clean_text(entry.get("url", "")))
        self._media_preview_token = token
        basic = entry_basic_metadata(entry)
        self._applyMediaPreview(basic, loading=True)
        cached = cached_metadata_poster_file(basic)
        if cached:
            self._showPreviewPoster(cached)
        else:
            try:
                self["preview_poster"].hide()
            except Exception:
                pass
        if self._media_preview_job is not None and self._media_preview_job.is_alive():
            self._scheduleMediaPreview(260)
            return
        self._media_preview_result = None
        self._media_preview_job = threading.Thread(target=self._mediaPreviewWorker, args=(token, entry, self.kind))
        self._media_preview_job.daemon = True
        self._media_preview_job.start()
        try:
            self._media_preview_timer.start(220, True)
        except TypeError:
            self._media_preview_timer.start(220)

    def _mediaPreviewWorker(self, token, entry, kind):
        try:
            # Episode rows already inherit their parent series poster; avoid
            # asking get_series_info with an episode id.
            if entry.get("is_episode"):
                metadata = entry_basic_metadata(entry)
            else:
                metadata = best_metadata_lookup(self.profile_id, entry, kind)
            poster = metadata_poster_file(metadata)
            self._media_preview_result = (token, True, metadata, poster, "")
        except Exception as error:
            self._media_preview_result = (token, False, entry_basic_metadata(entry), "", str(error))

    def _pollMediaPreview(self):
        if self._media_preview_job is not None and self._media_preview_job.is_alive():
            try:
                self._media_preview_timer.start(220, True)
            except TypeError:
                self._media_preview_timer.start(220)
            return
        result = self._media_preview_result
        self._media_preview_job = None
        self._media_preview_result = None
        if result and result[0] == self._media_preview_token:
            self._applyMediaPreview(result[2], loading=False)
            if result[3]:
                self._showPreviewPoster(result[3])
        # Selection may have changed while the provider request was running.
        try:
            index = self["list"].getSelectedIndex()
            current_token = "%d|%s" % (index, clean_text(self.visible_items[index].get("url", ""))) if 0 <= index < len(self.visible_items) else ""
        except Exception:
            current_token = ""
        if current_token and current_token != self._media_preview_token:
            self._scheduleMediaPreview(100)

    def currentEntry(self):
        index = self["list"].getSelectedIndex()
        return self.visible_items[index] if 0 <= index < len(self.visible_items) else None

    def search(self):
        self.session.openWithCallback(
            self.searchEntered,
            VirtualKeyBoard,
            title=tr("search_area"),
            text=""
        )

    def searchEntered(self, query):
        if not query:
            return

        if self.kind == "mixed":
            allowed_map = self.search_allowed_groups if isinstance(self.search_allowed_groups, dict) else {}
            results = []
            for entry in playlist_entries(self.profile_id, query=query):
                kind = entry.get("type")
                if kind not in ("movies", "series"):
                    continue
                group = clean_text(entry.get("group")) or "Ohne Kategorie"
                if group in set(allowed_map.get(kind, [])):
                    results.append(entry)
        else:
            allowed = self.search_allowed_groups
            results = playlist_entries(
                self.profile_id,
                kind=self.kind,
                query=query,
                allowed_groups=allowed
            )

        self.visible_items = results
        self.original_items = list(results)
        self.sort_mode = 0
        self["blue"].setText("BLAU  A-Z")
        self["title"].setText(tr("search_results", query=query))
        self.refreshRows()

    def sortItems(self):
        self.sort_mode = (self.sort_mode + 1) % 3
        if self.sort_mode == 0:
            self.visible_items = list(self.original_items)
            self["blue"].setText("BLAU  A-Z")
        elif self.sort_mode == 1:
            self.visible_items = sorted(
                self.original_items,
                key=lambda item: item.get("title", "").lower()
            )
            self["blue"].setText("BLAU  Z-A")
        else:
            self.visible_items = sorted(
                self.original_items,
                key=lambda item: item.get("title", "").lower(),
                reverse=True
            )
            self["blue"].setText("BLAU  Original")
        self.refreshRows()

    def toggleFavorite(self):
        entry = self.currentEntry()
        if not entry:
            return
        path = favorites_path(self.profile_id)
        favorites = favorite_entries(self.profile_id)
        key = entry.get("url", "")
        if any(item.get("url") == key for item in favorites):
            favorites = [item for item in favorites if item.get("url") != key]
            message = tr("removed_favorite")
        else:
            favorites.append(entry)
            message = tr("added_favorite")
        write_json(path, favorites)
        self.refreshRows()
        self.session.open(MessageBox, message, MessageBox.TYPE_INFO, timeout=2)

    def showGrid(self):
        if self.kind != "live" or not self.visible_items:
            return
        try:
            index = self["list"].getSelectedIndex()
        except Exception:
            index = 0
        self.session.open(EpiEPGGridScreen, self.profile_id, self.visible_items, index)

    def showDetails(self):
        entry = self.currentEntry()
        if not entry:
            return
        kind = entry.get("type")
        if kind == "live":
            self.session.open(EpiEPGScreen, self.profile_id, entry)
            return
        if kind not in ("movies", "series"):
            return
        # Open instantly with metadata already delivered by the category API;
        # detailed provider/TMDb enrichment happens in the detail screen thread.
        self.session.open(EpiDetailScreen, self.profile_id, entry, entry_basic_metadata(entry), kind)

    def playCurrent(self):
        entry = self.currentEntry()
        if not entry or not entry.get("url"):
            return
        kind = entry.get("type")
        if kind == "series" and clean_text(entry.get("url", "")).startswith("xtream-series://"):
            try:
                seasons = xtream_series_seasons(self.profile_id, entry)
                if not seasons:
                    self.session.open(MessageBox, tr("series_empty"), MessageBox.TYPE_INFO, timeout=4)
                    return
                series_title = entry.get("title", "Serie")
                # One-season series go straight to the episode list. With two
                # or more seasons the user first gets a clean season selector.
                if len(seasons) == 1:
                    group = seasons[0]
                    title = "%s - %s" % (series_title, clean_text(group.get("label", "Staffel")))
                    self.session.open(EpiContentScreen, self.profile_id, title, group.get("episodes", []), "series", [series_title])
                else:
                    self.session.open(EpiSeasonScreen, self.profile_id, series_title, seasons)
            except Exception as error:
                self.session.open(MessageBox, tr("series_load_error", error=str(error)), MessageBox.TYPE_ERROR, timeout=6)
            return
        settings = load_global_settings()
        if kind in ("movies", "series") and settings.get("resume_enabled", True):
            position = get_resume_position(self.profile_id, entry.get("url"))
            if position >= 30 * 90000:
                self._resume_entry = entry
                minutes = int(position / 90000 / 60)
                self.session.openWithCallback(
                    self.resumeChoice,
                    MessageBox,
                    tr("continue_question", minutes=minutes),
                    MessageBox.TYPE_YESNO
                )
                return
        self.startPlayback(entry, 0)

    def resumeChoice(self, confirmed):
        entry = getattr(self, "_resume_entry", None)
        if not entry:
            return
        position = get_resume_position(self.profile_id, entry.get("url")) if confirmed else 0
        self.startPlayback(entry, position)

    def startPlayback(self, entry, resume_position):
        try:
            if entry.get("type") == "live":
                current_index = self["list"].getSelectedIndex()
                self.session.openWithCallback(
                    self.livePlayerClosed,
                    EpiLivePlayer,
                    self.profile_id,
                    self.visible_items,
                    current_index
                )
                return

            save_recent_entry(self.profile_id, entry)
            ref = eServiceReference(1, 0, entry.get("url"))
            ref.setName(entry.get("title", "Epi MediaHub"))
            profile = get_profile(self.profile_id) or {}
            preferences = profile.get("preferred_audio", ["deu", "ita", "tur", "eng"])
            if EpiMoviePlayer is not None:
                episode_queue = []
                episode_index = -1
                if entry.get("type") == "series" and entry.get("is_episode"):
                    current_url = clean_text(entry.get("url", ""))
                    current_series_id = clean_text(entry.get("series_id", ""))
                    current_season = entry.get("season")

                    # First use the already loaded season list. Filter strictly
                    # so a "Recently watched" screen can never jump into another
                    # series just because it contains multiple episode entries.
                    for item in self.original_items:
                        if not isinstance(item, dict) or item.get("type") != "series" or not item.get("is_episode"):
                            continue
                        if not clean_text(item.get("url", "")):
                            continue
                        item_series_id = clean_text(item.get("series_id", ""))
                        if current_series_id and item_series_id and item_series_id != current_series_id:
                            continue
                        if current_season is not None and item.get("season") is not None and item.get("season") != current_season:
                            continue
                        episode_queue.append(dict(item))

                    # Screens such as "Recently watched" may only have the one
                    # current episode. Rebuild its season from the provider so
                    # LEFT/RIGHT still knows the neighbouring episodes.
                    if len(episode_queue) <= 1 and current_series_id:
                        try:
                            parent = {
                                "url": "xtream-series://%s" % current_series_id,
                                "title": entry.get("series_title") or entry.get("group") or "Serie",
                                "group": entry.get("parent_group", ""),
                                "type": "series",
                            }
                            seasons = xtream_series_seasons(self.profile_id, parent)
                            rebuilt = []
                            for group in seasons:
                                group_season = group.get("season")
                                if current_season is not None and group_season != current_season:
                                    continue
                                rebuilt.extend([dict(item) for item in group.get("episodes", []) if isinstance(item, dict) and clean_text(item.get("url", ""))])
                            if rebuilt:
                                episode_queue = rebuilt
                        except Exception:
                            pass

                    # Keep provider episode order stable even after entering from
                    # a sorted/search/recent view.
                    episode_queue.sort(key=lambda item: (
                        item.get("episode") is None,
                        item.get("episode") if item.get("episode") is not None else 999999,
                        item.get("_provider_order", 999999)
                    ))
                    for idx, item in enumerate(episode_queue):
                        if clean_text(item.get("url", "")) == current_url:
                            episode_index = idx
                            break
                self.session.openWithCallback(
                    self.vodPlayerClosed,
                    EpiMoviePlayer,
                    ref,
                    preferences,
                    self.profile_id,
                    entry.get("url", ""),
                    resume_position,
                    entry,
                    episode_queue,
                    episode_index
                )
            else:
                self.session.nav.playService(ref)
        except Exception as error:
            self.session.open(
                MessageBox,
                tr("playback_failed", error=str(error)),
                MessageBox.TYPE_ERROR,
                timeout=6
            )

    def vodPlayerClosed(self, *args):
        # If playback was launched from "Recently watched", reload that view so
        # the episode shown there immediately reflects the latest auto-advanced
        # or completed episode.
        if self._is_recent_view and self.kind in ("movies", "series"):
            try:
                profile = get_profile(self.profile_id) or {}
                self.visible_items = visible_recent_entries(self.profile_id, self.kind, profile, 40)
                self.original_items = list(self.visible_items)
            except Exception:
                pass
        self.refreshRows()

    def livePlayerClosed(self, current_url=""):
        if not current_url:
            return
        for index, item in enumerate(self.visible_items):
            if item.get("url", "") == current_url:
                try:
                    self["list"].moveToIndex(index)
                except Exception:
                    pass
                break


class EpiDetailScreen(Screen):
    skin = DETAIL_SKIN

    def __init__(self, session, profile_id, entry, metadata=None, kind=None):
        Screen.__init__(self, session)
        self.profile_id = profile_id
        self.entry = entry
        self.kind = kind or entry.get("type", "movies")
        self.metadata = metadata or entry_basic_metadata(entry)
        self["logo"] = Pixmap()
        self["poster"] = Pixmap()
        self._poster_decoder = None
        self._details_job = None
        self._details_result = None
        self._details_timer = eTimer()
        connect_timer(self._details_timer, self._pollDetails)
        self["title"] = Label("")
        self["rating"] = Label("")
        self["meta"] = Label("")
        self["overview"] = Label("")
        self["source"] = Label("")
        self["red"] = Label("ROT  %s" % tr("back"))
        self["green"] = Label("")
        self["yellow"] = Label("")
        self["blue"] = Label("")
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {"cancel": self.close, "red": self.close, "ok": self.close}, -1)
        self.applyMetadata(self.metadata, loading=True)
        self.onLayoutFinish.append(self._afterLayout)

    def _afterLayout(self):
        cached = cached_metadata_poster_file(self.metadata)
        if cached:
            self.loadPoster(cached)
        self._details_job = threading.Thread(target=self._detailsWorker)
        self._details_job.daemon = True
        self._details_job.start()
        try:
            self._details_timer.start(250, True)
        except TypeError:
            self._details_timer.start(250)

    def _detailsWorker(self):
        try:
            metadata = best_metadata_lookup(self.profile_id, self.entry, self.kind)
            poster = metadata_poster_file(metadata)
            self._details_result = (True, metadata, poster, "")
        except Exception as error:
            self._details_result = (False, self.metadata, "", str(error))

    def _pollDetails(self):
        if self._details_job is not None and self._details_job.is_alive():
            try:
                self._details_timer.start(250, True)
            except TypeError:
                self._details_timer.start(250)
            return
        result = self._details_result
        self._details_job = None
        self._details_result = None
        if result and result[0]:
            self.metadata = result[1] or self.metadata
            self.applyMetadata(self.metadata, loading=False)
            if len(result) > 2 and result[2]:
                self.loadPoster(result[2])
        elif result:
            self["source"].setText(tr("provider_info_error", error=result[3]))

    def applyMetadata(self, metadata, loading=False):
        metadata = metadata or {}
        self["title"].setText(metadata.get("title") or self.entry.get("title", "Filminfo"))
        rating = _safe_float(metadata.get("rating", 0))
        votes = int(metadata.get("votes", 0) or 0)
        if rating:
            rating_text = "★ %.1f / 10" % rating
            if votes:
                rating_text += "   (%d %s)" % (votes, tr("ratings"))
        else:
            rating_text = tr("no_rating")
        self["rating"].setText(rating_text)
        release = clean_text(metadata.get("release", ""))
        year = release[:4] if release else ""
        runtime = int(metadata.get("runtime", 0) or 0)
        genres = ", ".join(metadata.get("genres", []) or [])
        pieces = [value for value in (year, ("%d %s" % (runtime, tr("minutes")) if runtime else ""), genres) if value]
        self["meta"].setText("   •   ".join(pieces))
        overview = clean_text(metadata.get("overview", ""))
        self["overview"].setText(overview or (tr("info_loading") if loading else tr("no_description")))
        source = clean_text(metadata.get("source", "")) or "Provider"
        if loading:
            source += "   ·   %s" % tr("details_loading")
        self["source"].setText("%s: %s" % (tr("data_source"), source))

    def loadPoster(self, path=None):
        path = path or cached_metadata_poster_file(self.metadata)
        if not path or ePicLoad is None:
            return
        try:
            self._poster_decoder = ePicLoad()
            try:
                self._poster_decoder.PictureData.get().append(self.posterDecoded)
            except Exception:
                try:
                    self._poster_decoder.PictureData.connect(self.posterDecoded)
                except Exception:
                    return
            self._poster_decoder.setPara((sx(290), sy(420), 1, 1, False, 1, "#00000000"))
            result = self._poster_decoder.startDecode(path)
            if result not in (None, 0):
                _image_log("ePicLoad detail startDecode result=%s file=%s" % (result, path))
        except Exception as error:
            _image_log("ePicLoad detail exception file=%s error=%s" % (path, error))

    def posterDecoded(self, *args):
        try:
            ptr = self._poster_decoder.getData() if self._poster_decoder is not None else None
            if ptr is not None and self["poster"].instance is not None:
                self["poster"].instance.setPixmap(ptr)
            elif ptr is None:
                _image_log("ePicLoad detail decoded no pixmap")
        except Exception as error:
            _image_log("ePicLoad detail callback error=%s" % error)



class EpiEPGGridScreen(Screen):
    skin = EPG_GRID_SKIN

    def __init__(self, session, profile_id, entries, start_index=0):
        Screen.__init__(self, session)
        self.profile_id = profile_id
        self.entries = [dict(x) for x in list(entries or []) if isinstance(x, dict) and x.get("type") == "live" and clean_text(x.get("url", ""))]
        self.channel_index = max(0, min(int(start_index or 0), max(0, len(self.entries) - 1)))
        self.event_positions = {}
        now = int(time.time())
        self.window_start = int(now // 1800) * 1800 - 1800
        self["logo"] = Pixmap()
        self["title"] = Label("TV-PROGRAMM · EPG")
        self["timeline"] = Label("")
        self["list"] = MenuList([])
        self["detail"] = Label("")
        self["info"] = Label("")
        self["red"] = Label("ROT  Zurück")
        self["green"] = Label("GRÜN  Aufnahme")
        self["yellow"] = Label("GELB  Erinnerung")
        self["blue"] = Label("BLAU  Jetzt")
        self._load_job = None
        self._load_result = None
        self._load_timer = eTimer()
        connect_timer(self._load_timer, self._pollEpgLoad)
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions", "DirectionActions", "EPGCatchUpActions", "InfobarEPGActions"],
            {
                "cancel": self.close,
                "red": self.close,
                "up": self.channelUp,
                "down": self.channelDown,
                "chplus": self.channelDown,
                "chminus": self.channelUp,
                "left": self.eventPrevious,
                "right": self.eventNext,
                "ok": self.playSelected,
                "play": self.playSelected,
                "green": self.recordSelected,
                "yellow": self.remindSelected,
                "blue": self.jumpNow,
                "EPGPressed": self.jumpNow,
            },
            -5
        )
        self.onLayoutFinish.append(self._afterLayout)

    def _afterLayout(self):
        if self.entries:
            try:self["list"].moveToIndex(self.channel_index)
            except Exception:pass
        self.refresh()
        self._startEpgLoad()

    def _entryKey(self, entry=None):
        entry = entry or self.currentEntry()
        return clean_text((entry or {}).get("url", ""))

    def currentEntry(self):
        if not self.entries:
            return None
        try:
            idx = self["list"].getSelectedIndex()
            if 0 <= idx < len(self.entries):
                self.channel_index = idx
        except Exception:
            pass
        return self.entries[self.channel_index] if 0 <= self.channel_index < len(self.entries) else None

    def _events(self, entry=None):
        entry = entry or self.currentEntry()
        if not entry:
            return []
        items = epg_grid_items_for_entry(self.profile_id, entry)
        return sorted([x for x in items if isinstance(x, dict) and int(x.get("start", 0) or 0) > 0], key=lambda x:int(x.get("start",0)))

    def _defaultEventIndex(self, events):
        if not events:
            return -1
        now = int(time.time())
        for i,item in enumerate(events):
            if int(item.get("start",0)) <= now < int(item.get("stop",0)):
                return i
        for i,item in enumerate(events):
            if int(item.get("stop",0)) > self.window_start:
                return i
        return len(events)-1

    def selectedEvent(self):
        entry = self.currentEntry()
        events = self._events(entry)
        if not events:
            return None
        key = self._entryKey(entry)
        idx = self.event_positions.get(key)
        if idx is None or idx < 0 or idx >= len(events):
            idx = self._defaultEventIndex(events)
            self.event_positions[key] = idx
        return events[idx] if 0 <= idx < len(events) else None

    def _syncWindowToEvent(self, event):
        if not event:
            return
        start = int(event.get("start",0) or 0)
        if start < self.window_start or start >= self.window_start + 3*3600:
            self.window_start = int(start // 1800) * 1800 - 1800

    def channelUp(self):
        if not self.entries:return
        self.channel_index=max(0,self.channel_index-1)
        try:self["list"].moveToIndex(self.channel_index)
        except Exception:pass
        self.refresh(); self._startEpgLoad()

    def channelDown(self):
        if not self.entries:return
        self.channel_index=min(len(self.entries)-1,self.channel_index+1)
        try:self["list"].moveToIndex(self.channel_index)
        except Exception:pass
        self.refresh(); self._startEpgLoad()

    def eventPrevious(self):
        entry=self.currentEntry(); events=self._events(entry)
        if not events:return
        key=self._entryKey(entry); idx=self.event_positions.get(key,self._defaultEventIndex(events))
        idx=max(0,idx-1); self.event_positions[key]=idx
        self._syncWindowToEvent(events[idx]); self.refresh()

    def eventNext(self):
        entry=self.currentEntry(); events=self._events(entry)
        if not events:return
        key=self._entryKey(entry); idx=self.event_positions.get(key,self._defaultEventIndex(events))
        idx=min(len(events)-1,idx+1); self.event_positions[key]=idx
        self._syncWindowToEvent(events[idx]); self.refresh()

    def jumpNow(self):
        now=int(time.time()); self.window_start=int(now//1800)*1800-1800
        entry=self.currentEntry(); events=self._events(entry)
        if events:self.event_positions[self._entryKey(entry)]=self._defaultEventIndex(events)
        self.refresh(); self._startEpgLoad()

    def _timelineText(self):
        labels=[]
        for i in range(7):
            labels.append(format_clock(self.window_start+i*1800))
        return "   ·   ".join(labels)

    def _rowText(self, entry, row_index):
        title=clean_text(entry.get("title","Sender"))[:22]
        if entry_catchup_days(entry)>0:title += " [R]"
        events=self._events(entry)
        visible=[]
        wend=self.window_start+3*3600
        selected_idx=self.event_positions.get(self._entryKey(entry), self._defaultEventIndex(events))
        for idx,item in enumerate(events):
            start=int(item.get("start",0)); stop=int(item.get("stop",0))
            if stop <= self.window_start or start >= wend:continue
            text="%s %s"%(format_clock(start),clean_text(item.get("title",""))[:24])
            if row_index==self.channel_index and idx==selected_idx:text="▶ %s ◀"%text
            visible.append(text)
            if len(visible)>=4:break
        if not visible:visible=["— kein EPG im Zeitfenster —"]
        return "%-27s | %s"%(title,"  |  ".join(visible))

    def refresh(self):
        rows=[self._rowText(entry,i) for i,entry in enumerate(self.entries)]
        self["list"].setList(rows or ["Keine Live-Sender verfügbar"])
        if self.entries:
            try:self["list"].moveToIndex(self.channel_index)
            except Exception:pass
        self["timeline"].setText(self._timelineText())
        entry=self.currentEntry(); event=self.selectedEvent()
        if not entry or not event:
            self["detail"].setText("EPG-Daten werden geladen …")
            self["info"].setText("HOCH/RUNTER Sender · LINKS/RECHTS Sendung · EPG/Blau Jetzt")
            return
        start=int(event.get("start",0)); stop=int(event.get("stop",0)); now=int(time.time())
        status="ZUKÜNFTIG"
        if start <= now < stop:status="JETZT"
        elif stop <= now:status="REPLAY" if xtream_catchup_available(self.profile_id,entry,event) else "VERGANGEN"
        desc=clean_text(event.get("desc",""))[:180]
        self["detail"].setText("%s · %s-%s · %s\n%s\n%s"%(time.strftime("%d.%m.%Y",time.localtime(start)),format_clock(start),format_clock(stop),status,clean_text(event.get("title","")),desc))
        self["green"].setText("GRÜN  Aufnahme" if stop>now else "")
        self["yellow"].setText("GELB  Erinnerung" if start>now+10 else "")
        self["info"].setText("OK/PLAY = Live bzw. Replay · HOCH/RUNTER Sender · LINKS/RECHTS Sendung · BLAU = Jetzt")

    def _loadEntries(self):
        if not self.entries:return []
        a=max(0,self.channel_index-3); b=min(len(self.entries),self.channel_index+5)
        return [dict(x) for x in self.entries[a:b]]

    def _startEpgLoad(self):
        if db_source_mode(self.profile_id)!="xtream":return
        if self._load_job is not None and self._load_job.is_alive():return
        entries=self._loadEntries()
        if not entries:return
        self._load_result=None
        self._load_job=threading.Thread(target=self._epgWorker,args=(entries,))
        self._load_job.daemon=True; self._load_job.start()
        try:self._load_timer.start(250,True)
        except TypeError:self._load_timer.start(250)

    def _epgWorker(self, entries):
        def one(entry):
            try:xtream_full_epg(self.profile_id,entry,force=False)
            except Exception:pass
        try:
            if ThreadPoolExecutor is not None and len(entries)>1:
                with ThreadPoolExecutor(max_workers=min(4,len(entries))) as pool:list(pool.map(one,entries))
            else:
                for entry in entries:one(entry)
            self._load_result=True
        except Exception:self._load_result=False

    def _pollEpgLoad(self):
        if self._load_job is not None and self._load_job.is_alive():
            try:self._load_timer.start(250,True)
            except TypeError:self._load_timer.start(250)
            return
        self._load_job=None
        if self._load_result is not None:
            self._load_result=None; self.refresh()

    def playSelected(self):
        entry=self.currentEntry(); event=self.selectedEvent()
        if not entry:return
        now=int(time.time())
        if event and int(event.get("start",0)) < now and int(event.get("stop",0)) <= now:
            url=xtream_catchup_url(self.profile_id,entry,event)
            if not url:
                self.session.open(MessageBox,"Für diese vergangene Sendung stellt der Anbieter kein Replay bereit.",MessageBox.TYPE_INFO,timeout=5); return
            try:
                ref=eServiceReference(1,0,url); ref.setName(clean_text(event.get("title","Replay")))
                player=globals().get("EpiMediathekPlayer")
                if player is not None:self.session.open(player,ref)
                elif MoviePlayer is not None:self.session.open(MoviePlayer,ref,False)
                else:self.session.nav.playService(ref)
            except Exception as error:self.session.open(MessageBox,"Replay konnte nicht gestartet werden:\n%s"%clean_text(error),MessageBox.TYPE_ERROR,timeout=6)
            return
        if event and int(event.get("start",0)) > now:
            self.session.open(MessageBox,"Diese Sendung läuft erst später. GRÜN = Aufnahme, GELB = Erinnerung.",MessageBox.TYPE_INFO,timeout=5); return
        try:
            self.session.open(EpiLivePlayer,self.profile_id,self.entries,self.channel_index)
        except Exception as error:self.session.open(MessageBox,"Live-TV konnte nicht gestartet werden:\n%s"%clean_text(error),MessageBox.TYPE_ERROR,timeout=5)

    def recordSelected(self):
        entry=self.currentEntry(); event=self.selectedEvent()
        if not entry or not event:return
        ok,msg=epimedia_schedule_timer(self.session,entry,event,False)
        self.session.open(MessageBox,msg,MessageBox.TYPE_INFO if ok else MessageBox.TYPE_ERROR,timeout=5)

    def remindSelected(self):
        entry=self.currentEntry(); event=self.selectedEvent()
        if not entry or not event:return
        ok,msg=epimedia_schedule_timer(self.session,entry,event,True)
        self.session.open(MessageBox,msg,MessageBox.TYPE_INFO if ok else MessageBox.TYPE_ERROR,timeout=5)


class EpiEPGScreen(Screen):
    skin = EPG_SKIN

    def __init__(self, session, profile_id, entry):
        Screen.__init__(self, session)
        self.profile_id = profile_id
        self.entry = entry
        self["logo"] = Pixmap()
        self["title"] = Label("EPG - %s" % entry.get("title", tr("channel")))
        self["now"] = Label("")
        self["list"] = MenuList([])
        self["info"] = Label("")
        self["red"] = Label("ROT  %s" % tr("back"))
        self["green"] = Label("")
        self["yellow"] = Label("")
        self["blue"] = Label("")
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {"cancel": self.close, "red": self.close, "ok": self.close}, -1)
        self._epg_job = None
        self._epg_result = None
        self._epg_timer = eTimer()
        connect_timer(self._epg_timer, self._pollXtreamEpg)
        self.refresh()
        if not epg_programmes_for_entry(self.profile_id, self.entry) and db_source_mode(self.profile_id) == "xtream":
            self._startXtreamEpg()

    def _startXtreamEpg(self):
        if self._epg_job is not None and self._epg_job.is_alive():
            return
        self["now"].setText(tr("epg_provider_loading"))
        self["info"].setText(tr("epg_background"))
        self._epg_job = threading.Thread(target=self._xtreamEpgWorker)
        self._epg_job.daemon = True
        self._epg_job.start()
        try:
            self._epg_timer.start(250, True)
        except TypeError:
            self._epg_timer.start(250)

    def _xtreamEpgWorker(self):
        try:
            items = xtream_short_epg(self.profile_id, self.entry, limit=30, force=True)
            self._epg_result = (True, len(items), "")
        except Exception as error:
            self._epg_result = (False, 0, str(error))

    def _pollXtreamEpg(self):
        if self._epg_job is not None and self._epg_job.is_alive():
            try:
                self._epg_timer.start(250, True)
            except TypeError:
                self._epg_timer.start(250)
            return
        result = self._epg_result
        self._epg_job = None
        self._epg_result = None
        self.refresh()
        if result and not result[0]:
            self["info"].setText(tr("epg_provider_unavailable", error=result[2]))

    def refresh(self):
        items = epg_programmes_for_entry(self.profile_id, self.entry)
        now = int(time.time())
        upcoming = [item for item in items if int(item.get("stop", 0)) > now]
        current, next_item = now_next_from_items(items)
        if current:
            self["now"].setText("%s  %s-%s   %s\n%s" % (
                tr("now"), format_clock(current.get("start")), format_clock(current.get("stop")), current.get("title", ""), current.get("desc", "")[:160]
            ))
        elif self._epg_job is None:
            self["now"].setText(tr("epg_no_current"))
        rows = []
        for item in upcoming[:40]:
            prefix = tr("now") if item is current else format_clock(item.get("start"))
            rows.append("%s   %s" % (prefix, item.get("title", "")))
        if not rows:
            rows = [tr("epg_none_found")]
        self["list"].setList(rows)
        if items:
            self["info"].setText(tr("epg_source"))
        elif self._epg_job is None:
            self["info"].setText(tr("epg_none_available"))



class EpiSettings(Screen):
    skin = SETTINGS_SKIN
    AUDIO_CHOICES = [
        ("Deutsch > Italienisch > Türkisch > Englisch", ["deu", "ita", "tur", "eng"]),
        ("Italienisch > Deutsch > Türkisch > Englisch", ["ita", "deu", "tur", "eng"]),
        ("Türkisch > Deutsch > Italienisch > Englisch", ["tur", "deu", "ita", "eng"]),
        ("Englisch > Deutsch > Italienisch > Türkisch", ["eng", "deu", "ita", "tur"]),
    ]
    LANGUAGE_CHOICES = [
        ("Deutsch", "de-DE"),
        ("Italiano", "it-IT"),
        ("Türkçe", "tr-TR"),
        ("English", "en-US"),
        ("Español", "es-ES"),
    ]

    def __init__(self, session, profile_id):
        Screen.__init__(self, session)
        self.profile_id = profile_id
        self.profile = ensure_profile_category_maps(get_profile(profile_id) or default_profile())
        self.settings = load_global_settings()
        self._pending_new_pin = ""
        self._pin_action = ""

        self["logo"] = Pixmap()
        self["title"] = Label(tr("settings_title"))
        self["subtitle"] = Label("")
        self["themePanel"] = Label("")
        self["themeAccent"] = Label("")
        self["themeName"] = Label("")
        self["themePreview"] = Pixmap()
        self["list"] = MenuList([])
        self["info"] = Label("")
        self["red"] = Label("ROT  %s" % tr("back"))
        self["green"] = Label("GRÜN  %s" % tr("load_playlist"))
        self["yellow"] = Label("GELB  %s" % tr("scan"))
        self["blue"] = Label("BLAU  %s" % tr("update_epg"))
        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions", "MenuActions"],
            {
                "cancel": self.close,
                "red": self.close,
                "green": self.loadPlaylist,
                "yellow": self.scanFiles,
                "blue": self.loadEPG,
                "menu": self.openHelp,
                "ok": self.editSelected
            },
            -1
        )

        self.rows = []
        self._playlist_job = None
        self._playlist_result = None
        self._playlist_timer = eTimer()
        connect_timer(self._playlist_timer, self._pollPlaylistJob)
        self.refresh()

    def maskedUrl(self, url):
        if not url:
            return "nicht gesetzt"
        try:
            parsed = urlparse(url)
            if "password" in parse_qs(parsed.query):
                return "%s://%s/... (Zugangsdaten gespeichert)" % (parsed.scheme, parsed.netloc)
        except Exception:
            pass
        return url[:72] + "..." if len(url) > 75 else url

    def refresh(self):
        self.profile = ensure_profile_category_maps(get_profile(self.profile_id) or self.profile)
        self.settings = load_global_settings()
        self["title"].setText(tr("settings_title"))
        self["red"].setText("ROT  %s" % tr("back"))
        self["green"].setText("GRÜN  %s" % tr("load_playlist"))
        self["yellow"].setText("GELB  %s" % tr("scan"))
        self["blue"].setText("BLAU  %s" % tr("update_epg"))
        self["subtitle"].setText("%s: %s" % (tr("playlist"), self.profile.get("name", "Playlist")))
        active_theme = clean_text(self.settings.get("skin_theme", "default")) or "default"
        self["themeName"].setText("%s   ·   %s" % (tr("skin"), theme_display_name(active_theme)))
        if parseColor is not None:
            try:
                if self["themeAccent"].instance is not None:
                    self["themeAccent"].instance.setBackgroundColor(parseColor(theme_accent(active_theme)))
            except Exception:
                pass
        try:
            if self["themePreview"].instance is not None and os.path.isfile(ACTIVE_THEME_MARK):
                self["themePreview"].instance.setPixmapFromFile(ACTIVE_THEME_MARK)
        except Exception:
            pass
        source = self.profile.get("managed_file") or self.maskedUrl(self.profile.get("m3u_url", ""))
        tmdb_state = tr("configured") if clean_text(self.settings.get("tmdb_api_key", "")) else tr("not_configured")
        lang_labels = {"de-DE": "Deutsch", "it-IT": "Italiano", "tr-TR": "Türkçe", "en-US": "English", "es-ES": "Español"}
        selected_app = clean_text(self.settings.get("app_language", "system")) or "system"
        if selected_app == "system":
            app_lang_text = tr("system_active", language=language_display_name(system_app_language()))
        else:
            app_lang_text = language_display_name(selected_app)

        parental = tr("on") if self.settings.get("parental_enabled", False) else tr("off")
        adult_auto = tr("on") if self.settings.get("parental_auto_adult", True) else tr("off")
        pin_state = tr("set") if clean_text(self.settings.get("parental_pin_hash", "")) else tr("not_set")

        self.rows = [
            ("name", "%s: %s" % (tr("playlist_name"), self.profile.get("name", "Playlist"))),
            ("applanguage", "%s: %s" % (tr("app_language"), app_lang_text)),
            ("skin", "%s: %s" % (tr("skin"), theme_display_name(self.settings.get("skin_theme", "default")))),
            ("accesscode", tr("pin_default")),
            ("sourcemode", "%s: %s" % (tr("data_mode"), ("FAST API (Xtream)" if db_source_mode(self.profile_id) == "xtream" else "M3U-Fallback"))),
            ("url", "%s: %s" % (tr("m3u_source"), source)),
            ("epg", "EPG/XMLTV: %s" % (self.maskedUrl(profile_epg_url(self.profile)) if profile_epg_url(self.profile) else "Auto")),
            ("audio", "%s: %s" % (tr("audio_language"), audio_label(self.profile.get("preferred_audio", ["deu", "ita", "tur", "eng"])))),
            ("tmdb", "%s: %s" % (tr("tmdb_key"), tmdb_state)),
            ("language", "%s: %s" % (tr("movie_infos"), lang_labels.get(self.settings.get("metadata_language"), self.settings.get("metadata_language")))),
            ("actorimages", "%s: %s · Saga" % (tr("actor_images"), tr("on") if self.settings.get("actor_category_images", True) else tr("off"))),
            ("resume", "%s: %s" % (tr("resume"), tr("on") if self.settings.get("resume_enabled", True) else tr("off"))),
            ("weather", "%s: %s" % (tr("weather"), tr("on") if self.settings.get("weather_enabled", True) else tr("off"))),
            ("weatherlocation", "%s: %s" % (tr("weather_location"), clean_text(self.settings.get("weather_location", "")) or tr("automatic"))),
            ("parental", "%s: %s" % (tr("parental"), parental)),
            ("adultauto", "%s: %s" % (tr("adult_auto"), adult_auto)),
            ("pin", "%s: %s" % (tr("pin"), pin_state)),
            ("cache", tr("clear_cache")),
            ("updateurl", "%s: %s" % (tr("update_source"), tr("configured") if clean_text(self.settings.get("update_manifest_url", "")) else tr("not_configured"))),
            ("autoupdate", "%s: %s" % (tr("auto_updates"), tr("on") if self.settings.get("auto_update_check", True) else tr("off"))),
            ("autostart", "%s: %s" % (tr("autostart"), tr("yes") if self.settings.get("autostart_app", False) else tr("no"))),
            ("help", tr("playlist_help")),
            ("updatecheck", tr("check_updates", version=PLUGIN_VERSION)),
        ]
        self["list"].setList([row[1] for row in self.rows])
        self["info"].setText(tr("settings_change"))

    def selectedKey(self):
        index = self["list"].getSelectedIndex()
        return self.rows[index][0] if 0 <= index < len(self.rows) else ""

    def editSelected(self):
        key = self.selectedKey()

        if key == "applanguage":
            current = clean_text(self.settings.get("app_language", "system")) or "system"
            choices = [
                (("[%s] " % tr("active") if current == "system" else "") + tr("system"), "system"),
                (("[%s] " % tr("active") if current == "de" else "") + "Deutsch", "de"),
                (("[%s] " % tr("active") if current == "en" else "") + "English", "en"),
                (("[%s] " % tr("active") if current == "tr" else "") + "Türkçe", "tr"),
                (("[%s] " % tr("active") if current == "it" else "") + "Italiano", "it"),
                (("[%s] " % tr("active") if current == "es" else "") + "Español", "es"),
            ]
            self.session.openWithCallback(self.appLanguageChosen, ChoiceBox, title=tr("app_language"), list=choices)
        elif key == "skin":
            current = clean_text(self.settings.get("skin_theme", "default")) or "default"
            current_group = clean_text(theme_meta(current).get("group", "standard"))
            choices = []
            for group in THEME_CATALOG.get("groups", []):
                gid = clean_text(group.get("id", ""))
                label = clean_text(group.get("label", gid))
                if not gid:
                    continue
                if gid == current_group:
                    label = "[AKTIV] " + label
                choices.append((label, gid))
            self.session.openWithCallback(self.skinCategoryChosen, ChoiceBox, title=tr("skin_category"), list=choices)
        elif key == "accesscode":
            self.session.openWithCallback(
                self._familyPinEntered,
                EpiPinScreen,
                tr("pin_default")
            )
        elif key == "sourcemode":
            error = clean_text(self.profile.get("fast_api_error", ""))
            if db_source_mode(self.profile_id) == "xtream":
                self.session.open(MessageBox, "FAST API ist aktiv.", MessageBox.TYPE_INFO, timeout=5)
            else:
                text = "Die Playlist läuft im M3U-Fallback.\n\nOK/JA = FAST API jetzt erneut automatisch erkennen."
                if error:
                    text += "\n\nLetzter FAST-API-Fehler:\n%s" % error
                self.session.openWithCallback(self._retryFastApiConfirmed, MessageBox, text, MessageBox.TYPE_YESNO)
        elif key == "name":
            self.session.openWithCallback(
                self.nameEntered,
                VirtualKeyBoard,
                title="Playlist-Name",
                text=self.profile.get("name", "")
            )
        elif key == "url":
            self.session.openWithCallback(
                self.urlEntered,
                VirtualKeyBoard,
                title="M3U-URL (leer lassen bei FTP-Datei)",
                text=self.profile.get("m3u_url", "")
            )
        elif key == "epg":
            self.session.openWithCallback(
                self.epgEntered,
                VirtualKeyBoard,
                title="EPG/XMLTV-URL (leer = automatisch)",
                text=self.profile.get("epg_url", "")
            )
        elif key == "audio":
            current = self.profile.get("preferred_audio", ["deu", "ita", "tur", "eng"])
            choices = [
                (("[AKTIV] " if value == current else "") + label, value)
                for label, value in self.AUDIO_CHOICES
            ]
            self.session.openWithCallback(
                self.audioChosen,
                ChoiceBox,
                title=tr("audio_language"),
                list=choices
            )
        elif key == "tmdb":
            self.session.openWithCallback(
                self.tmdbEntered,
                VirtualKeyBoard,
                title="TMDb API-Key / Read Access Token",
                text=self.settings.get("tmdb_api_key", "")
            )
        elif key == "language":
            current = self.settings.get("metadata_language", "de-DE")
            choices = [
                (("[AKTIV] " if value == current else "") + label, value)
                for label, value in self.LANGUAGE_CHOICES
            ]
            self.session.openWithCallback(
                self.languageChosen,
                ChoiceBox,
                title=tr("metadata_language"),
                list=choices
            )
        elif key == "actorimages":
            self.settings["actor_category_images"] = not self.settings.get("actor_category_images", True)
            save_global_settings(self.settings)
            self.refresh()
        elif key == "resume":
            self.settings["resume_enabled"] = not self.settings.get("resume_enabled", True)
            save_global_settings(self.settings)
            self.refresh()
        elif key == "weather":
            self.settings["weather_enabled"] = not self.settings.get("weather_enabled", True)
            save_global_settings(self.settings)
            self.refresh()
        elif key == "weatherlocation":
            self.session.openWithCallback(
                self.weatherLocationEntered,
                VirtualKeyBoard,
                title="Wetter-Standort oder 5-stellige PLZ (leer = automatisch)",
                text=self.settings.get("weather_location", "")
            )
        elif key == "parental":
            if self.settings.get("parental_enabled", False):
                self._pin_action = "disable"
                self.session.openWithCallback(
                    self._currentPinEntered,
                    EpiPinScreen,
                    "Kindersicherung deaktivieren - PIN"
                )
            else:
                self._pin_action = "enable"
                self._startNewPin()
        elif key == "adultauto":
            if self.settings.get("parental_enabled", False):
                self._pin_action = "adultauto"
                self.session.openWithCallback(
                    self._currentPinEntered,
                    EpiPinScreen,
                    "18+ Automatik ändern - PIN"
                )
            else:
                self.settings["parental_auto_adult"] = not self.settings.get("parental_auto_adult", True)
                save_global_settings(self.settings)
                self.refresh()
        elif key == "pin":
            if self.settings.get("parental_enabled", False) and clean_text(self.settings.get("parental_pin_hash", "")):
                self._pin_action = "change_pin_auth"
                self.session.openWithCallback(
                    self._currentPinEntered,
                    EpiPinScreen,
                    "Aktuelle Kindersicherungs-PIN"
                )
            else:
                self._pin_action = "change_pin"
                self._startNewPin()
        elif key == "cache":
            self.session.openWithCallback(
                self.clearCacheConfirmed,
                MessageBox,
                "TMDb-Metadaten-Cache löschen?",
                MessageBox.TYPE_YESNO
            )
        elif key == "updateurl":
            self.session.openWithCallback(
                self.updateUrlEntered,
                VirtualKeyBoard,
                title="HTTPS-URL zum Epi MediaHub update.json",
                text=self.settings.get("update_manifest_url", "")
            )
        elif key == "autoupdate":
            self.settings["auto_update_check"] = not self.settings.get("auto_update_check", True)
            save_global_settings(self.settings)
            self.refresh()
        elif key == "autostart":
            self.settings["autostart_app"] = not self.settings.get("autostart_app", False)
            save_global_settings(self.settings)
            self.refresh()
            state = "aktiviert" if self.settings.get("autostart_app", False) else "deaktiviert"
            self.session.open(
                MessageBox,
                "Automatischer Start wurde %s.\nDie Änderung gilt ab dem nächsten Receiver-/Enigma2-Start." % state,
                MessageBox.TYPE_INFO,
                timeout=5
            )
        elif key == "help":
            self.openHelp()
        elif key == "updatecheck":
            self.checkForUpdate()

    def _familyPinEntered(self, pin):
        if pin is None:
            return
        digest = hashlib.sha256(clean_text(pin).encode("utf-8")).hexdigest()
        if digest != FAMILY_PIN_HASH:
            self.session.open(MessageBox, "PIN ist falsch.", MessageBox.TYPE_ERROR, timeout=2)
            return
        self.settings = load_global_settings()
        self.settings["family_skins_unlocked"] = True
        save_global_settings(self.settings)
        self.refresh()
        self.session.open(MessageBox, "Freigeschaltet.", MessageBox.TYPE_INFO, timeout=2)

    def openHelp(self):
        self.session.open(EpiHelpScreen)

    def _startNewPin(self):
        self._pending_new_pin = ""
        self.session.openWithCallback(
            self._newPinFirst,
            EpiPinScreen,
            "Neue vierstellige Kindersicherungs-PIN"
        )

    def _newPinFirst(self, pin):
        if pin is None:
            return
        self._pending_new_pin = pin
        self.session.openWithCallback(
            self._newPinConfirm,
            EpiPinScreen,
            "Neue PIN wiederholen"
        )

    def _newPinConfirm(self, pin):
        if pin is None:
            return
        if pin != self._pending_new_pin:
            self._pending_new_pin = ""
            self.session.open(
                MessageBox,
                "Die PINs stimmen nicht überein.",
                MessageBox.TYPE_ERROR,
                timeout=4
            )
            return

        self.settings = load_global_settings()
        self.settings["parental_pin_hash"] = pin_hash(pin)
        if self._pin_action == "enable":
            self.settings["parental_enabled"] = True
        save_global_settings(self.settings)
        self._pending_new_pin = ""
        self._pin_action = ""
        self.refresh()
        self.session.open(
            MessageBox,
            "Kindersicherungs-PIN gespeichert.",
            MessageBox.TYPE_INFO,
            timeout=3
        )

    def _currentPinEntered(self, pin):
        action = self._pin_action
        if pin is None:
            self._pin_action = ""
            return
        if not pin_matches(pin):
            self._pin_action = ""
            self.session.open(MessageBox, "PIN ist falsch.", MessageBox.TYPE_ERROR, timeout=3)
            return

        self.settings = load_global_settings()
        if action == "disable":
            self.settings["parental_enabled"] = False
            save_global_settings(self.settings)
            self._pin_action = ""
            self.refresh()
        elif action == "adultauto":
            self.settings["parental_auto_adult"] = not self.settings.get("parental_auto_adult", True)
            save_global_settings(self.settings)
            self._pin_action = ""
            self.refresh()
        elif action == "change_pin_auth":
            self._pin_action = "change_pin"
            self._startNewPin()

    def _retryFastApiConfirmed(self, confirmed):
        if confirmed:
            # Reuses the existing background playlist worker. In 0.7.1 it tries
            # direct URL, redirects and cached M3U stream credentials before any
            # full M3U download.
            self.loadPlaylist()

    def nameEntered(self, value):
        if not clean_text(value):
            return
        self.profile["name"] = clean_text(value)
        update_profile(self.profile)
        self.refresh()

    def urlEntered(self, value):
        if value is None:
            return
        self.profile["m3u_url"] = clean_text(value)
        if self.profile["m3u_url"]:
            self.profile["managed_file"] = ""
        self.profile["expiry"] = ""
        self.profile["source_mode"] = "m3u"
        try:
            meta = xtream_meta_path(self.profile.get("id", ""))
            if os.path.exists(meta):
                os.remove(meta)
        except Exception:
            pass
        update_profile(self.profile)
        self.refresh()

    def epgEntered(self, value):
        if value is None:
            return
        self.profile["epg_url"] = clean_text(value)
        update_profile(self.profile)
        self.refresh()

    def audioChosen(self, selection):
        if not selection:
            return
        self.profile["preferred_audio"] = selection[1]
        update_profile(self.profile)
        self.refresh()

    def tmdbEntered(self, value):
        if value is None:
            return
        old_value = clean_text(self.settings.get("tmdb_api_key", ""))
        new_value = clean_text(value)
        self.settings["tmdb_api_key"] = new_value
        save_global_settings(self.settings)
        # A previous lookup may have been negatively cached while no key was
        # configured. Force an immediate retry after the key/token changes.
        if new_value != old_value:
            try:
                if os.path.isfile(ACTOR_CACHE_FILE):
                    os.remove(ACTOR_CACHE_FILE)
            except Exception:
                pass
        self.refresh()
        if new_value and new_value != old_value:
            self.session.open(
                MessageBox,
                "TMDb wurde gespeichert. Schauspielerbilder werden beim Öffnen der Film-/Serien-Kategorien automatisch geladen.",
                MessageBox.TYPE_INFO,
                timeout=5
            )

    def skinCategoryChosen(self, selection):
        if not selection:
            return
        group_id = selection[1]
        group_data = None
        for group in THEME_CATALOG.get("groups", []):
            if clean_text(group.get("id", "")) == group_id:
                group_data = group
                break
        if not group_data:
            return
        current = clean_text(self.settings.get("skin_theme", "default")) or "default"
        choices = []
        family_unlocked = bool(self.settings.get("family_skins_unlocked", False))
        for theme_id in group_data.get("themes", []):
            if theme_id not in THEME_CATALOG.get("themes", {}):
                continue
            meta = theme_meta(theme_id)
            if meta.get("family", False) and not family_unlocked:
                continue
            label = theme_display_name(theme_id)
            if theme_id == current:
                label = "[AKTIV] " + label
            choices.append((label, theme_id))
        if choices:
            self.session.openWithCallback(self.skinChosen, ChoiceBox, title=tr("skin_select"), list=choices)

    def skinChosen(self, selection):
        if not selection:
            return
        theme_id = clean_text(selection[1])
        if theme_id not in THEME_CATALOG.get("themes", {}):
            return
        self.settings["skin_theme"] = theme_id
        save_global_settings(self.settings)
        prepare_active_theme(theme_id)
        self.refresh()
        try:
            if self["themePreview"].instance is not None and os.path.isfile(ACTIVE_THEME_MARK):
                self["themePreview"].instance.setPixmapFromFile(ACTIVE_THEME_MARK)
        except Exception:
            pass
        self.session.open(MessageBox, tr("skin_saved"), MessageBox.TYPE_INFO, timeout=7)

    def appLanguageChosen(self, selection):
        if not selection:
            return
        self.settings["app_language"] = selection[1]
        save_global_settings(self.settings)
        self.refresh()

    def languageChosen(self, selection):
        if not selection:
            return
        self.settings["metadata_language"] = selection[1]
        save_global_settings(self.settings)
        self.refresh()

    def weatherLocationEntered(self, value):
        if value is None:
            return
        self.settings["weather_location"] = clean_text(value)
        save_global_settings(self.settings)
        # Force the next home-screen visit to refresh this location.
        try:
            if os.path.exists(WEATHER_CACHE_FILE):
                os.remove(WEATHER_CACHE_FILE)
        except Exception:
            pass
        self.refresh()

    def updateUrlEntered(self, value):
        if value is None:
            return
        self.settings["update_manifest_url"] = clean_text(value)
        save_global_settings(self.settings)
        self.refresh()

    def checkForUpdate(self):
        url = clean_text(self.settings.get("update_manifest_url", ""))
        if not url:
            self.session.open(MessageBox, "Noch keine Update-Quelle eingerichtet.\nDafür brauchen wir später eine HTTPS-Adresse mit update.json.", MessageBox.TYPE_INFO, timeout=6)
            return
        try:
            manifest = fetch_update_manifest(url)
            remote = clean_text(manifest.get("version", ""))
            if not remote:
                raise Exception("Versionsnummer fehlt im Manifest.")
            if version_tuple(remote) <= version_tuple(PLUGIN_VERSION):
                self.session.open(MessageBox, "Epi MediaHub ist aktuell (v%s)." % PLUGIN_VERSION, MessageBox.TYPE_INFO, timeout=4)
                return
            self._pending_update_manifest = manifest
            self.session.openWithCallback(self._updateConfirmed, MessageBox, "Epi MediaHub v%s ist verfügbar.\nJetzt herunterladen und installieren?" % remote, MessageBox.TYPE_YESNO)
        except Exception as error:
            self.session.open(MessageBox, "Update-Prüfung fehlgeschlagen:\n%s" % str(error), MessageBox.TYPE_ERROR, timeout=7)

    def _updateConfirmed(self, confirmed):
        if not confirmed:
            return
        manifest = getattr(self, "_pending_update_manifest", None)
        if not manifest:
            return
        try:
            download_and_install_update(manifest)
            if TryQuitMainloop is not None:
                self.session.openWithCallback(self._restartAfterUpdate, MessageBox, "Update wurde installiert.\nEnigma2 jetzt neu starten?", MessageBox.TYPE_YESNO)
            else:
                self.session.open(MessageBox, "Update installiert. Bitte die Enigma2-GUI neu starten.", MessageBox.TYPE_INFO, timeout=6)
        except Exception as error:
            self.session.open(MessageBox, "Update konnte nicht installiert werden:\n%s" % str(error), MessageBox.TYPE_ERROR, timeout=8)

    def _restartAfterUpdate(self, confirmed):
        if confirmed and TryQuitMainloop is not None:
            self.session.open(TryQuitMainloop, 3)

    def clearCacheConfirmed(self, confirmed):
        if not confirmed:
            return
        try:
            if os.path.exists(METADATA_CACHE_FILE):
                os.remove(METADATA_CACHE_FILE)
            if os.path.exists(ACTOR_CACHE_FILE):
                os.remove(ACTOR_CACHE_FILE)
            if os.path.isdir(ACTOR_CACHE_DIR):
                for filename in os.listdir(ACTOR_CACHE_DIR):
                    path = os.path.join(ACTOR_CACHE_DIR, filename)
                    if os.path.isfile(path):
                        try:
                            os.remove(path)
                        except Exception:
                            pass
        except Exception:
            pass
        self.session.open(MessageBox, "Metadaten- und Schauspieler-Cache gelöscht.", MessageBox.TYPE_INFO, timeout=3)

    def loadPlaylist(self):
        if self._playlist_job is not None and self._playlist_job.is_alive():
            self.session.open(MessageBox, "Die Playlist wird bereits geladen.", MessageBox.TYPE_INFO, timeout=3)
            return

        profile = dict(self.profile)
        self._playlist_result = None
        self["green"].setText("GRÜN  Lädt ...")
        self["info"].setText(
            "Playlist wird im Hintergrund geladen und schnell indiziert. Die Box bleibt bedienbar ..."
        )
        self._playlist_job = threading.Thread(target=self._playlistWorker, args=(profile,))
        self._playlist_job.daemon = True
        self._playlist_job.start()
        try:
            self._playlist_timer.start(300, True)
        except TypeError:
            self._playlist_timer.start(300)

    def _playlistWorker(self, profile):
        try:
            count = int(download_playlist(profile))
            profile["last_update"] = time.strftime("%d.%m.%Y %H:%M")
            if profile.get("m3u_url") and clean_text(profile.get("source_mode", "")) != "xtream":
                profile["expiry"] = try_fetch_expiry(profile.get("m3u_url", ""))
            self._playlist_result = (True, profile, count, "")
        except Exception as error:
            self._playlist_result = (False, profile, 0, str(error))

    def _pollPlaylistJob(self):
        if self._playlist_job is not None and self._playlist_job.is_alive():
            try:
                self._playlist_timer.start(300, True)
            except TypeError:
                self._playlist_timer.start(300)
            return

        result = self._playlist_result
        self._playlist_job = None
        self._playlist_result = None
        self["green"].setText("GRÜN  Playlist laden")

        if not result:
            self.refresh()
            return

        ok, profile, count, error = result
        if ok:
            update_profile(profile)
            self.profile = profile
            self.refresh()
            if clean_text(profile.get("source_mode", "")) == "xtream":
                message = "FAST API bereit: %d Kategorien geladen. Inhalte werden erst beim Öffnen der Kategorie abgerufen." % count
            else:
                message = "Playlist geladen und indiziert: %d Einträge" % count
            self.session.open(MessageBox, message, MessageBox.TYPE_INFO, timeout=6)
        else:
            self.refresh()
            self.session.open(
                MessageBox,
                "Playlist konnte nicht geladen werden:\n%s" % error,
                MessageBox.TYPE_ERROR,
                timeout=8
            )

    def scanFiles(self):
        added, updated = scan_local_playlists()
        self.session.open(
            MessageBox,
            "Playlist-Scan fertig.\nNeu: %d   Aktualisiert/entfernt: %d\n\nSchnellimport: %s" % (added, updated, PLAYLIST_TEXT_FILE),
            MessageBox.TYPE_INFO,
            timeout=5
        )
        self.refresh()

    def loadEPG(self):
        try:
            count = download_epg(self.profile)
            self.profile = get_profile(self.profile_id) or self.profile
            self.refresh()
            self.session.open(
                MessageBox,
                "EPG aktualisiert: %d Sendungen im Cache" % count,
                MessageBox.TYPE_INFO,
                timeout=6
            )
        except Exception as error:
            self.session.open(
                MessageBox,
                "EPG konnte nicht geladen werden:\n%s" % str(error),
                MessageBox.TYPE_ERROR,
                timeout=8
            )


def route_after_splash(session):
    scan_local_playlists()
    data = load_profiles()
    profiles = data.get("profiles", [])
    if len(profiles) == 1:
        profile_id = profiles[0].get("id")
        set_active_profile(profile_id)
        session.open(EpiMediaHubHome, profile_id)
    elif len(profiles) > 1:
        session.openWithCallback(lambda profile_id=None: open_home_after_selection(session, profile_id), EpiProfileSelect)
    else:
        session.openWithCallback(lambda profile_id=None: open_home_after_selection(session, profile_id), EpiProfileSelect)


def open_home_after_selection(session, profile_id):
    if profile_id:
        set_active_profile(profile_id)
        session.open(EpiMediaHubHome, profile_id)


def main(session, **kwargs):
    ensure_data_dir()
    session.openWithCallback(lambda *args: route_after_splash(session), EpiSplash)


# Keep timers/session alive globally for boot and standby-wakeup launches.
# Opening a full-screen plugin directly inside WHERE_SESSIONSTART or while
# Enigma2 is still closing its Standby screen can be too early on some images,
# so both paths use a short delayed launch.
_BOOT_AUTOSTART_TIMER = None
_BOOT_AUTOSTART_SESSION = None
_STANDBY_WAKE_TIMER = None
_STANDBY_SESSION = None
_STANDBY_HOOK_INSTALLED = False


def _epimedia_dialog_active(session):
    try:
        dialog = getattr(session, "current_dialog", None)
        if dialog is None:
            return False
        cls = dialog.__class__
        module = clean_text(getattr(cls, "__module__", ""))
        name = clean_text(getattr(cls, "__name__", ""))
        return module == __name__ and name.startswith("Epi")
    except Exception:
        return False


def _run_boot_autostart():
    global _BOOT_AUTOSTART_TIMER, _BOOT_AUTOSTART_SESSION
    session = _BOOT_AUTOSTART_SESSION
    try:
        if _BOOT_AUTOSTART_TIMER is not None:
            _BOOT_AUTOSTART_TIMER.stop()
    except Exception:
        pass
    _BOOT_AUTOSTART_TIMER = None
    _BOOT_AUTOSTART_SESSION = None
    if session is None:
        return
    try:
        if load_global_settings().get("autostart_app", False) and not _epimedia_dialog_active(session):
            main(session)
    except Exception:
        pass


def _run_standby_wake():
    global _STANDBY_WAKE_TIMER
    session = _STANDBY_SESSION
    try:
        if _STANDBY_WAKE_TIMER is not None:
            _STANDBY_WAKE_TIMER.stop()
    except Exception:
        pass
    _STANDBY_WAKE_TIMER = None
    if session is None:
        return
    try:
        if load_global_settings().get("autostart_app", False) and not _epimedia_dialog_active(session):
            main(session)
    except Exception:
        pass


def _on_leave_standby():
    global _STANDBY_WAKE_TIMER
    # Give the receiver skin/InfoBar a brief moment to finish restoring itself
    # before putting Epi MediaHub back on top.
    try:
        if _STANDBY_WAKE_TIMER is not None:
            _STANDBY_WAKE_TIMER.stop()
    except Exception:
        pass
    try:
        _STANDBY_WAKE_TIMER = eTimer()
        connect_timer(_STANDBY_WAKE_TIMER, _run_standby_wake)
        try:
            _STANDBY_WAKE_TIMER.start(1300, True)
        except TypeError:
            _STANDBY_WAKE_TIMER.start(1300)
    except Exception:
        _run_standby_wake()


def _standby_counter_changed(_element=None):
    # config.misc.standbyCounter fires when normal standby starts. The Standby
    # screen's onClose callback is the most compatible signal for wake-up on
    # OpenATV/OpenPLi-style images.
    try:
        screen = getattr(Standby, "inStandby", None) if Standby is not None else None
        callbacks = getattr(screen, "onClose", None) if screen is not None else None
        if callbacks is not None and _on_leave_standby not in callbacks:
            callbacks.append(_on_leave_standby)
    except Exception:
        pass


def _install_standby_hook(session):
    global _STANDBY_SESSION, _STANDBY_HOOK_INSTALLED
    _STANDBY_SESSION = session
    if _STANDBY_HOOK_INSTALLED or config is None or Standby is None:
        return
    try:
        counter = config.misc.standbyCounter
        try:
            counter.addNotifier(_standby_counter_changed, initial_call=False)
        except TypeError:
            counter.addNotifier(_standby_counter_changed)
        _STANDBY_HOOK_INSTALLED = True
    except Exception:
        pass


def session_start(reason, **kwargs):
    global _BOOT_AUTOSTART_TIMER, _BOOT_AUTOSTART_SESSION
    # Enigma2 calls SESSIONSTART with reason == 0 when a GUI session starts.
    if reason != 0:
        return
    session = kwargs.get("session")
    if session is None:
        return

    # Install the standby watcher regardless of the current setting. This also
    # makes enabling Autostart later in Settings effective without a GUI reboot.
    _install_standby_hook(session)

    try:
        if not load_global_settings().get("autostart_app", False):
            return
    except Exception:
        return
    _BOOT_AUTOSTART_SESSION = session
    try:
        _BOOT_AUTOSTART_TIMER = eTimer()
        connect_timer(_BOOT_AUTOSTART_TIMER, _run_boot_autostart)
        try:
            _BOOT_AUTOSTART_TIMER.start(5000, True)
        except TypeError:
            _BOOT_AUTOSTART_TIMER.start(5000)
    except Exception:
        _run_boot_autostart()


def main_menu_hook(menuid, **kwargs):
    """Always expose Epi MediaHub in the receiver's main menu."""
    if menuid != "mainmenu":
        return []
    return [("Epi MediaHub", main, "epimediahub_mainmenu", 45)]


def Plugins(**kwargs):
    descriptors = [
        PluginDescriptor(
            name="Epi MediaHub",
            description="Epi MediaHub - M3U, EPG & VOD Player",
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon="plugin.png",
            fnc=main,
        ),
        PluginDescriptor(
            name="Epi MediaHub",
            description="Epi MediaHub im Hauptmenü",
            where=PluginDescriptor.WHERE_MENU,
            fnc=main_menu_hook,
        )
    ]
    try:
        descriptors.append(
            PluginDescriptor(
                name="Epi MediaHub Autostart",
                description="Optionaler automatischer Start von Epi MediaHub",
                where=PluginDescriptor.WHERE_SESSIONSTART,
                fnc=session_start,
            )
        )
    except Exception:
        pass
    return descriptors
