#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.27.ipk"
T=/tmp/epimedia0928
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
if 'PLUGIN_VERSION = "0.9.27"' not in t:
    raise SystemExit('Expected v0.9.27 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.27"','PLUGIN_VERSION = "0.9.28"',1)

anchor='MEDIATHEK_API_URL = "https://mediathekviewweb.de/api/query"\n'
if anchor not in t:
    raise SystemExit('Mediathek API anchor missing')
helper='''MEDIATHEK_API_URL = "https://mediathekviewweb.de/api/query"\nMEDIATHEK_DEBUG_LOG = "/tmp/epimediahub_mediathek.log"\n\ndef _mediathek_debug(event, detail=""):\n    try:\n        with open(MEDIATHEK_DEBUG_LOG, "a") as handle:\n            handle.write("%s | %s | %s\\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), clean_text(event), clean_text(detail)))\n    except Exception:\n        pass\n'''
t=t.replace(anchor,helper,1)

# Instrument Mediathek list creation/layout/close so a GUI restart leaves a trail in /tmp.
old='''        self.onLayoutFinish.append(self._layout)\n\n    def _timer_start(self,timer,delay):'''
new='''        self.onLayoutFinish.append(self._layout)\n        _mediathek_debug("list_init", "%s | %s" % (self.source_kind, self.channel_label))\n\n    def _timer_start(self,timer,delay):'''
if old not in t: raise SystemExit('list init anchor missing')
t=t.replace(old,new,1)

old='''    def _layout(self):\n        try:self["poster"].hide()'''
new='''    def _layout(self):\n        _mediathek_debug("list_layout", "%s | %s" % (self.source_kind, self.channel_label))\n        try:self["poster"].hide()'''
if old not in t: raise SystemExit('layout anchor missing')
t=t.replace(old,new,1)

old='''    def safeClose(self):\n        # Important: do not dismantle MenuList callbacks, native pixmaps or\n        # Enigma2 components manually while Screen.close() is running.  Let\n        # Enigma2 own teardown.  We only stop future timers and mark the screen.\n        if self._closing:return\n        self._closing=True\n        try:self._load_timer.stop()\n        except Exception:pass\n        try:self._poster_timer.stop()\n        except Exception:pass\n        self.close()\n'''
new='''    def safeClose(self):\n        # Keep the BACK path deliberately minimal.  Record the transition before\n        # Enigma2 owns teardown so a later GUI restart can be diagnosed.\n        if self._closing:return\n        _mediathek_debug("list_close_begin", "%s | %s" % (self.source_kind, self.channel_label))\n        self._closing=True\n        try:self._load_timer.stop()\n        except Exception as error:_mediathek_debug("load_timer_stop_error", str(error))\n        try:self._poster_timer.stop()\n        except Exception as error:_mediathek_debug("poster_timer_stop_error", str(error))\n        _mediathek_debug("list_close_call", "%s | %s" % (self.source_kind, self.channel_label))\n        self.close()\n'''
if old not in t: raise SystemExit('safeClose block missing')
t=t.replace(old,new,1)

# Mediathek playback must not use the app-specific VOD player.  That player is
# designed around playlist/resume/episode state.  Use the image-native standard
# MoviePlayer for all Mediathek streams so BACK/EXIT follows Enigma2's own path.
start=t.find('    def playSelected(self):', t.find('class EpiMediathekList(Screen):'))
end=t.find('\n\nclass EpiMediaHubHome(Screen):', start)
if start<0 or end<0: raise SystemExit('playSelected boundaries missing')
block=t[start:end]
# Preserve openSearch/searchEntered and replace only playSelected at the end.
play_start=block.rfind('    def playSelected(self):')
if play_start<0: raise SystemExit('playSelected missing in block')
prefix=block[:play_start]
new_play='''    def playSelected(self):\n        if self._closing:return\n        entry=self.selectedEntry()\n        url=clean_text(entry.get("url","")) if entry else ""\n        if not url:return\n        title=clean_text(entry.get("title","Mediathek"))\n        _mediathek_debug("play_open", "%s | %s | %s" % (self.source_kind, self.channel_label, title))\n        try:\n            ref=eServiceReference(4097,0,url)\n            ref.setName(title or "Mediathek")\n            if MoviePlayer is not None:\n                self.session.open(MoviePlayer,ref)\n                _mediathek_debug("play_opened_standard", title)\n            else:\n                self.session.nav.playService(ref)\n                _mediathek_debug("play_started_nav", title)\n        except Exception as error:\n            _mediathek_debug("play_open_error", str(error))\n            try:self.session.open(MessageBox,"Wiedergabe fehlgeschlagen:\\n%s"%str(error),MessageBox.TYPE_ERROR,timeout=7)\n            except Exception:pass\n'''
t=t[:start]+prefix+new_play+t[end:]

# Also mark provider transitions.  Rai stays direct and PIN-free.
dir_start=t.find('class EpiMediathekDirectory(Screen):')
dir_end=t.find('class EpiMediathekList(Screen):',dir_start)
if dir_start<0 or dir_end<0: raise SystemExit('directory class boundaries missing')
dir_block=t[dir_start:dir_end]
old='''    def openSelected(self):\n        x=self.selected()\n        if not x:return\n        self._open_item(x)\n'''
new='''    def openSelected(self):\n        x=self.selected()\n        if not x:return\n        _mediathek_debug("provider_open", "%s | %s" % (clean_text(x.get("kind","")), clean_text(x.get("label",""))))\n        self._open_item(x)\n'''
if old not in dir_block: raise SystemExit('direct provider open block missing')
dir_block=dir_block.replace(old,new,1)
t=t[:dir_start]+dir_block+t[dir_end:]

p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.28/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.28 standard Mediathek player and diagnostics/' "$T/control/control"

python3 -m py_compile "$P"
grep -q 'PLUGIN_VERSION = "0.9.28"' "$P"
grep -q 'MEDIATHEK_DEBUG_LOG = "/tmp/epimediahub_mediathek.log"' "$P"
grep -q 'play_opened_standard' "$P"
grep -q 'FAMILY_PIN_HASH' "$P"
grep -q 'family_skins_unlocked' "$P"
grep -q '_familyPinEntered' "$P"
python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
a=t.index('class EpiMediathekList(Screen):'); b=t.index('class EpiMediaHubHome(Screen):',a); x=t[a:b]
play=x[x.index('    def playSelected(self):'):]
if 'EpiMoviePlayer' in play: raise SystemExit('Custom EpiMoviePlayer still used by Mediathek')
if 'MoviePlayer' not in play: raise SystemExit('Standard MoviePlayer missing')
d=t[t.index('class EpiMediathekDirectory(Screen):'):a]
if 'Family · Rai International' in d or '_pin_done' in d: raise SystemExit('Rai PIN gate returned')
print('v0.9.28 Mediathek player/debug guard: OK')
PY

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.28.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"
if ar p EpiMediaHub_v0.9.28.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.28.ipk)
echo "v0.9.28 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.28.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.28.ipk" > EpiMediaHub_v0.9.28.ipk.sha256
printf '{\n  "version": "0.9.28",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.28.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.28.ipk.sha256
rm -f EpiMediaHub_v0.9.27.ipk EpiMediaHub_v0.9.27.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.28 standard Mediathek player and diagnostics'
git push
