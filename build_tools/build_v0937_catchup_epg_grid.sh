#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.36.ipk"
T=/tmp/epimedia0937
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

def must(old, new, count=1, label='anchor'):
    global t
    found=t.count(old)
    if found < count:
        raise SystemExit('%s missing: expected >=%d got %d' % (label,count,found))
    t=t.replace(old,new,count)

if 'PLUGIN_VERSION = "0.9.36"' not in t:
    raise SystemExit('Expected v0.9.36 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.36"','PLUGIN_VERSION = "0.9.37"',1)

# Native OpenATV timer integration. Graceful fallback keeps non-OpenATV images usable.
config_anchor='''try:\n    from Components.config import config\nexcept Exception:\n    config = None\n'''
timer_import='''try:\n    from RecordTimer import RecordTimerEntry, AFTEREVENT\n    from ServiceReference import ServiceReference\nexcept Exception:\n    RecordTimerEntry = None\n    AFTEREVENT = None\n    ServiceReference = None\n'''
must(config_anchor, config_anchor+'\n'+timer_import, label='timer import')

# New caches/schema markers.
must('_XTREAM_EPG_MEMORY_CACHE = {}\n_PICON_PIXMAP_CACHE = {}',
     '_XTREAM_EPG_MEMORY_CACHE = {}\n_XTREAM_FULL_EPG_MEMORY_CACHE = {}\n_DB_SCHEMA_READY = set()\n_PICON_PIXMAP_CACHE = {}', label='global cache')

# Graphical multi-channel EPG screen (string rows deliberately keep native MenuList navigation reliable).
grid_skin=r'''EPG_GRID_SKIN = build_fullscreen_skin(
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

'''
must('MEDIATHEK_HOME_SKIN = build_fullscreen_skin(', grid_skin+'MEDIATHEK_HOME_SKIN = build_fullscreen_skin(', label='grid skin')

# One-time Xtream live-cache migration: force loaded Live categories to refresh so archive flags arrive.
old_load='''def load_xtream_meta(profile_id):\n    data = read_json(xtream_meta_path(profile_id), {})\n    return data if isinstance(data, dict) else {}\n'''
new_load='''def load_xtream_meta(profile_id):\n    data = read_json(xtream_meta_path(profile_id), {})\n    if not isinstance(data, dict):\n        return {}\n    if data.get("source") == "xtream" and int(data.get("catchup_schema", 0) or 0) < 1:\n        data.setdefault("loaded_categories", {})["live"] = []\n        data.setdefault("full_loaded", {})["live"] = False\n        data["catchup_schema"] = 1\n        try:\n            write_json(xtream_meta_path(profile_id), data)\n        except Exception:\n            pass\n    return data\n'''
must(old_load,new_load,label='load_xtream_meta')

# New profiles are born on the current entry schema.
must('''        "full_loaded": {"live": False, "movies": False, "series": False},\n        "created": int(time.time()),''',
     '''        "full_loaded": {"live": False, "movies": False, "series": False},\n        "catchup_schema": 1,\n        "created": int(time.time()),''', label='xtream meta schema')

# Keep provider archive capability on every live entry.
needle='''        if kind == "series":\n            sid = item.get("series_id", item.get("stream_id", ""))'''
insert='''        if kind == "live":\n            try:\n                common["tv_archive"] = int(item.get("tv_archive", 0) or 0)\n            except Exception:\n                common["tv_archive"] = 0\n            try:\n                common["tv_archive_duration"] = max(0, int(item.get("tv_archive_duration", 0) or 0))\n            except Exception:\n                common["tv_archive_duration"] = 0\n        if kind == "series":\n            sid = item.get("series_id", item.get("stream_id", ""))'''
must(needle,insert,label='live archive metadata')

# SQLite migration for existing caches. JSON fallback already preserves arbitrary entry fields.
old_db='''def _db_connect(profile_id):\n    if sqlite3 is None:\n        return None\n    connection = sqlite3.connect(playlist_db_path(profile_id))\n    connection.row_factory = sqlite3.Row\n    return connection\n'''
new_db='''def _db_connect(profile_id):\n    if sqlite3 is None:\n        return None\n    connection = sqlite3.connect(playlist_db_path(profile_id))\n    connection.row_factory = sqlite3.Row\n    if profile_id not in _DB_SCHEMA_READY:\n        try:\n            columns = set(row[1] for row in connection.execute("PRAGMA table_info(entries)").fetchall())\n            for name, definition in (("source_id", "TEXT"), ("tv_archive", "INTEGER DEFAULT 0"), ("tv_archive_duration", "INTEGER DEFAULT 0")):\n                if name not in columns:\n                    connection.execute("ALTER TABLE entries ADD COLUMN %s %s" % (name, definition))\n            connection.commit()\n            _DB_SCHEMA_READY.add(profile_id)\n        except Exception:\n            pass\n    return connection\n'''
must(old_db,new_db,label='db migration')

# Both Xtream empty DB and M3U DB get the same compatible columns.
must('CREATE TABLE entries (ord INTEGER PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, group_name TEXT NOT NULL, logo TEXT, tvg_id TEXT, tvg_name TEXT, url TEXT NOT NULL)',
     'CREATE TABLE entries (ord INTEGER PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, group_name TEXT NOT NULL, logo TEXT, tvg_id TEXT, tvg_name TEXT, url TEXT NOT NULL, source_id TEXT, tv_archive INTEGER DEFAULT 0, tv_archive_duration INTEGER DEFAULT 0)', label='empty db schema')
must('''                tvg_name TEXT,\n                url TEXT NOT NULL\n            )''',
     '''                tvg_name TEXT,\n                url TEXT NOT NULL,\n                source_id TEXT,\n                tv_archive INTEGER DEFAULT 0,\n                tv_archive_duration INTEGER DEFAULT 0\n            )''', label='m3u db schema')

# M3U rows have no Xtream archive metadata.
must('''                    pending.get("tvg_name", ""), line\n                ))''',
     '''                    pending.get("tvg_name", ""), line, "", 0, 0\n                ))''', label='m3u db tuple')
t=t.replace('INSERT INTO entries(ord,kind,title,group_name,logo,tvg_id,tvg_name,url) VALUES(?,?,?,?,?,?,?,?)',
            'INSERT INTO entries(ord,kind,title,group_name,logo,tvg_id,tvg_name,url,source_id,tv_archive,tv_archive_duration) VALUES(?,?,?,?,?,?,?,?,?,?,?)')

# Xtream category cache stores the extra columns.
old_row='''            rows.append((base_ord + idx + 1, kind, entry.get("title", ""), group_name, entry.get("logo", ""), entry.get("tvg_id", ""), entry.get("tvg_name", ""), entry.get("url", "")))'''
new_row='''            rows.append((base_ord + idx + 1, kind, entry.get("title", ""), group_name, entry.get("logo", ""), entry.get("tvg_id", ""), entry.get("tvg_name", ""), entry.get("url", ""), entry.get("source_id", ""), int(entry.get("tv_archive", 0) or 0), int(entry.get("tv_archive_duration", 0) or 0)))'''
must(old_row,new_row,label='xtream db tuple')

# Restore metadata when reading SQLite rows.
old_rowentry='''def _row_to_entry(row):\n    return {\n        "title": row["title"],\n        "group": row["group_name"],\n        "logo": row["logo"] or "",\n        "tvg_id": row["tvg_id"] or "",\n        "tvg_name": row["tvg_name"] or "",\n        "url": row["url"],\n        "type": row["kind"],\n    }\n'''
new_rowentry='''def _row_to_entry(row):\n    try:\n        keys = set(row.keys())\n    except Exception:\n        keys = set()\n    return {\n        "title": row["title"],\n        "group": row["group_name"],\n        "logo": row["logo"] or "",\n        "tvg_id": row["tvg_id"] or "",\n        "tvg_name": row["tvg_name"] or "",\n        "url": row["url"],\n        "type": row["kind"],\n        "source_id": (row["source_id"] or "") if "source_id" in keys else "",\n        "tv_archive": int(row["tv_archive"] or 0) if "tv_archive" in keys else 0,\n        "tv_archive_duration": int(row["tv_archive_duration"] or 0) if "tv_archive_duration" in keys else 0,\n    }\n'''
must(old_rowentry,new_rowentry,label='row_to_entry')
t=t.replace('SELECT ord,kind,title,group_name,logo,tvg_id,tvg_name,url FROM entries',
            'SELECT ord,kind,title,group_name,logo,tvg_id,tvg_name,url,source_id,tv_archive,tv_archive_duration FROM entries')

# Full Xtream EPG + archive URL generation.
catchup_code=r'''
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

'''
must('# -------------------- EPG --------------------',catchup_code+'# -------------------- EPG --------------------',label='catchup helpers')

# Server offset persistence needs the profile id in meta; harmless for existing/new profiles.
must('''    meta = dict(cfg)\n    meta.update({''','''    meta = dict(cfg)\n    meta["profile_id"] = profile.get("id", "")\n    meta.update({''',label='meta profile id')

# Native RecordTimer helper.
timer_code=r'''
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

'''
must('# -------------------- TMDb metadata --------------------',timer_code+'# -------------------- TMDb metadata --------------------',label='timer helper')

# Mark Replay-capable channels in Live lists and advertise the EPG key.
must('''            title = prefix + (entry.get("recent_title") or entry.get("title", "Unbenannt"))\n            if detected_kind == "live":''',
     '''            title = prefix + (entry.get("recent_title") or entry.get("title", "Unbenannt"))\n            if detected_kind == "live" and entry_catchup_days(entry) > 0:\n                title += "  [REPLAY]"\n            if detected_kind == "live":''',label='replay marker')
must('''        if detected_kind == "live":\n            extra += "   |   EPG + Picons automatisch"''',
     '''        if detected_kind == "live":\n            extra += "   |   EPG-Taste = Raster   |   EPG + Picons automatisch"''',label='grid hint')

# Multi-channel EPG / catch-up UI.
grid_class=r'''
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
                ref=eServiceReference(4097,0,url); ref.setName(clean_text(event.get("title","Replay")))
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


'''
must('class EpiEPGScreen(Screen):',grid_class+'class EpiEPGScreen(Screen):',label='grid class')

# EPG key opens the grid from Live list.
must('''                "showEventInfo": self.showDetails\n            },''',
     '''                "showEventInfo": self.showDetails,\n                "EPGPressed": self.showGrid\n            },''',label='content epg action')
show_details_anchor='''    def showDetails(self):\n        entry = self.currentEntry()'''
show_grid='''    def showGrid(self):\n        if self.kind != "live" or not self.visible_items:\n            return\n        try:\n            index = self["list"].getSelectedIndex()\n        except Exception:\n            index = 0\n        self.session.open(EpiEPGGridScreen, self.profile_id, self.visible_items, index)\n\n'''
must(show_details_anchor,show_grid+show_details_anchor,label='content showGrid')

# EPG key also works while watching live TV, without stopping the current stream.
must('''            ["OkCancelActions", "DirectionActions", "InfoActions"],''',
     '''            ["OkCancelActions", "DirectionActions", "InfoActions", "InfobarEPGActions"],''',label='live player action contexts')
must('''                "showEventInfo": self.showBanner,\n            },''',
     '''                "showEventInfo": self.showBanner,\n                "EPGPressed": self.openGrid,\n            },''',label='live player epg action')
exit_anchor='''    def exitToList(self):\n        try:\n            self._banner_timer.stop()'''
open_grid='''    def openGrid(self):\n        if not self.entries:\n            return\n        self.session.open(EpiEPGGridScreen, self.profile_id, self.entries, self.index)\n\n'''
must(exit_anchor,open_grid+exit_anchor,label='live player openGrid')

# Release notes for the two major features.
notes='''_RELEASE_NOTES = {\n    "0.9.37": {\n        "de": [\n            "Xtream Catch-up/Replay: Archivsender und verfügbare vergangene Sendungen lassen sich direkt aus dem EPG starten.",\n            "Neue Mehrsender-EPG-Rasteransicht mit Live/Replay, Aufnahme-Timer und Erinnerungs-/Zap-Timer über Enigma2.",\n        ],\n        "en": [\n            "Xtream catch-up/replay for provider archive channels directly from the EPG.",\n            "New multi-channel EPG grid with live/replay playback plus native Enigma2 recording and reminder timers.",\n        ],\n        "tr": [\n            "Xtream arşiv kanalları için EPG üzerinden Catch-up/Replay desteği.",\n            "Canlı/Replay, kayıt ve hatırlatma zamanlayıcılı yeni çok kanallı EPG görünümü.",\n        ],\n        "it": [\n            "Catch-up/Replay Xtream per i canali archivio direttamente dalla guida EPG.",\n            "Nuova griglia EPG multicanale con Live/Replay, registrazioni e promemoria Enigma2.",\n        ],\n        "es": [\n            "Catch-up/Replay Xtream para canales con archivo directamente desde la EPG.",\n            "Nueva parrilla EPG multicanal con Live/Replay, grabaciones y recordatorios Enigma2.",\n        ],\n    },'''
must('_RELEASE_NOTES = {',notes,label='release notes')

p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.37/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.37 Xtream catch-up, EPG grid and Enigma2 timers/' "$T/control/control"

python3 -m py_compile "$P"

grep -q 'PLUGIN_VERSION = "0.9.37"' "$P"
grep -q 'class EpiEPGGridScreen(Screen)' "$P"
grep -q 'def xtream_full_epg' "$P"
grep -q 'get_simple_data_table' "$P"
grep -q 'def xtream_catchup_url' "$P"
grep -q '/timeshift/' "$P"
grep -q 'tv_archive_duration' "$P"
grep -q 'RecordTimerEntry' "$P"
grep -q 'def epimedia_schedule_timer' "$P"
grep -q 'EPGPressed.*self.showGrid' "$P"
grep -q 'EPGPressed.*self.openGrid' "$P"
grep -q '\[REPLAY\]' "$P"
# Existing critical fixes/features must survive.
grep -q 'class EpiMediathekPlayer(MoviePlayer)' "$P"
grep -q 'class EpiWebPlaylistSetup(Screen)' "$P"
grep -q 'def _playlist_web_generate_qr' "$P"
grep -q 'FAMILY_PIN_HASH' "$P"
grep -q 'family_skins_unlocked' "$P"
grep -q 'parental_pin_hash' "$P"
grep -q 'directory_back_parent_ok' "$P"
grep -q 'list_back_parent_ok' "$P"
grep -q 'home_back_parent_ok' "$P"

python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
checks=[
 '"tv_archive": int(row["tv_archive"] or 0)',
 '"tv_archive_duration": int(row["tv_archive_duration"] or 0)',
 'action=get_simple_data_table' if False else '"get_simple_data_table"',
 'RecordTimerEntry(service_ref, begin, end, title, desc, 0',
 'xtream_catchup_available(self.profile_id,entry,event)',
 'self.session.open(EpiEPGGridScreen, self.profile_id, self.visible_items, index)',
 'self.session.open(EpiEPGGridScreen, self.profile_id, self.entries, self.index)',
]
for c in checks:
    if c not in t: raise SystemExit('v0.9.37 guard missing: '+c)
# Catch-up is provider-gated and cannot fabricate replay for ordinary M3U streams.
segment=t[t.index('def xtream_catchup_available'):t.index('def _xtream_server_offset')]
if 'db_source_mode(profile_id) != "xtream"' not in segment or 'entry_catchup_days(entry) <= 0' not in segment:
    raise SystemExit('Catch-up provider guard missing')
# Rai/local Family PIN behavior must stay untouched.
ms=t.index('class EpiMediathekHome(Screen):'); me=t.index('class EpiMediaHubHome(Screen):',ms); m=t[ms:me]
if '_pin_done' in m or ('Rai' in m and 'openWithCallback(self._pin' in m):
    raise SystemExit('Rai provider PIN gate reintroduced')
print('v0.9.37 catch-up + EPG grid/timer guard: OK')
PY

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.37.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"
if ar p EpiMediaHub_v0.9.37.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.37.ipk)
echo "v0.9.37 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.37.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.37.ipk" > EpiMediaHub_v0.9.37.ipk.sha256
printf '{\n  "version": "0.9.37",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.37.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.37.ipk.sha256
rm -f EpiMediaHub_v0.9.36.ipk EpiMediaHub_v0.9.36.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.37 catch-up and EPG grid'
git push
