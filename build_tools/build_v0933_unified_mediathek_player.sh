#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.32.ipk"
T=/tmp/epimedia0933
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
if 'PLUGIN_VERSION = "0.9.32"' not in t:
    raise SystemExit('Expected v0.9.32 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.32"','PLUGIN_VERSION = "0.9.33"',1)

mstart=t.index('class EpiMediathekHome(Screen):')
mend=t.index('class EpiMediaHubHome(Screen):',mstart)
m=t[mstart:mend]

if 'class EpiMediathekPlayer(MoviePlayer):' not in m:
    raise SystemExit('EpiMediathekPlayer missing from Mediathek block')

# One central player launcher for the entire Mediathek.  All provider-specific
# stream paths resolve a URL, then use this helper.  This guarantees the same
# EXIT/BACK/STOP semantics everywhere (Rai, TRT, ARD/ZDF, ORF, SRF, ARTE, ...).
list_anchor='class EpiMediathekList(Screen):\n'
if list_anchor not in m:
    raise SystemExit('EpiMediathekList anchor missing')
helper='''def _open_mediathek_stream(session,url,title="Mediathek",source=""):\n    url=clean_text(url)\n    title=clean_text(title) or "Mediathek"\n    if not url:\n        raise RuntimeError("Kein abspielbarer Stream gefunden.")\n    ref=eServiceReference(4097,0,url)\n    ref.setName(title)\n    _mediathek_debug("player_route","%s | %s" % (clean_text(source),title))\n    if EpiMediathekPlayer is not None:\n        session.open(EpiMediathekPlayer,ref)\n        _mediathek_debug("play_opened_mediathek",title)\n    else:\n        session.nav.playService(ref)\n        _mediathek_debug("play_started_nav",title)\n    return True\n\n\n'''
m=m.replace(list_anchor,helper+list_anchor,1)

# TRT previously bypassed the Mediathek player and opened OpenATV MoviePlayer
# directly.  Route it through the central launcher instead.
old_trt='''                ref=eServiceReference(4097,0,url); ref.setName(x.get("label","TRT")); self.session.open(MoviePlayer,ref) if MoviePlayer is not None else self.session.nav.playService(ref)\n'''
new_trt='''                _open_mediathek_stream(self.session,url,x.get("label","TRT"),"trt")\n'''
if old_trt not in m:
    raise SystemExit('TRT stock MoviePlayer path not found')
m=m.replace(old_trt,new_trt,1)

# Replace the generic content-list player entry with the same central launcher.
ls=m.index('class EpiMediathekList(Screen):')
play=m.index('    def playSelected(self):',ls)
# playSelected is the final method in the class before the Mediathek block ends.
old_play=m[play:]
new_play='''    def playSelected(self):\n        if self._closing:return\n        entry=self.selectedEntry()\n        url=clean_text(entry.get("url","")) if entry else ""\n        if not url:return\n        title=clean_text(entry.get("title","Mediathek"))\n        _mediathek_debug("play_open","%s | %s | %s" % (self.source_kind,self.channel_label,title))\n        try:\n            _open_mediathek_stream(self.session,url,title,self.source_kind)\n        except Exception as error:\n            _mediathek_debug("play_open_error",str(error))\n            try:self.session.open(MessageBox,"Wiedergabe fehlgeschlagen:\\n%s"%str(error),MessageBox.TYPE_ERROR,timeout=7)\n            except Exception:pass\n\n\n'''
m=m[:play]+new_play

# Safety: no Mediathek provider or list may bypass the unified player anymore.
for forbidden in ('self.session.open(MoviePlayer,ref)','self.session.open(EpiMoviePlayer'):
    if forbidden in m:
        raise SystemExit('Non-unified Mediathek player path remains: '+forbidden)
if '_open_mediathek_stream(self.session,url,x.get("label","TRT"),"trt")' not in m:
    raise SystemExit('TRT unified player route missing')
if '_open_mediathek_stream(self.session,url,title,self.source_kind)' not in m:
    raise SystemExit('Generic Mediathek unified player route missing')

t=t[:mstart]+m+t[mend:]
p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.33/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.33 unified player for all Mediathek streams/' "$T/control/control"

python3 -m py_compile "$P"
grep -q 'PLUGIN_VERSION = "0.9.33"' "$P"
grep -q 'def _open_mediathek_stream' "$P"
grep -q 'class EpiMediathekPlayer(MoviePlayer)' "$P"
grep -q 'fromMovieSelection=False' "$P"
grep -q 'player_route' "$P"
grep -q 'directory_back_parent_ok' "$P"
grep -q 'list_back_parent_ok' "$P"
# Rai stays PIN-free; unrelated Family/parental features stay intact.
grep -q 'FAMILY_PIN_HASH' "$P"
grep -q 'family_skins_unlocked' "$P"
grep -q '_familyPinEntered' "$P"
python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
a=t.index('class EpiMediathekHome(Screen):'); b=t.index('class EpiMediaHubHome(Screen):',a); m=t[a:b]
for needle in ('def _open_mediathek_stream','session.open(EpiMediathekPlayer,ref)','_open_mediathek_stream(self.session,url,x.get("label","TRT"),"trt")','_open_mediathek_stream(self.session,url,title,self.source_kind)'):
    if needle not in m: raise SystemExit('Unified Mediathek player guard missing: '+needle)
for forbidden in ('self.session.open(MoviePlayer,ref)','self.session.open(EpiMoviePlayer'):
    if forbidden in m: raise SystemExit('Bypass player path remains: '+forbidden)
print('v0.9.33 unified Mediathek player guard: OK')
PY

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.33.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"
if ar p EpiMediaHub_v0.9.33.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.33.ipk)
echo "v0.9.33 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.33.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.33.ipk" > EpiMediaHub_v0.9.33.ipk.sha256
printf '{\n  "version": "0.9.33",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.33.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.33.ipk.sha256
rm -f EpiMediaHub_v0.9.32.ipk EpiMediaHub_v0.9.32.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.33 unified Mediathek player'
git push
