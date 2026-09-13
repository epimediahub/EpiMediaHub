#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.28.ipk"
T=/tmp/epimedia0929
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
if 'PLUGIN_VERSION = "0.9.28"' not in t:
    raise SystemExit('Expected v0.9.28 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.28"','PLUGIN_VERSION = "0.9.29"',1)

# A Mediathek stream is not a recording selected from OpenATV's MovieSelection.
# The stock MoviePlayer defaults to fromMovieSelection=True and EXIT behaviour is
# configurable (first EXIT can hide the infobar / show a popup).  Provide a tiny
# wrapper that keeps all normal seek/audio/subtitle capabilities but guarantees
# EXIT/BACK and STOP close the stream immediately back to the Mediathek list.
anchor='class EpiMediathekList(Screen):\n'
if anchor not in t:
    raise SystemExit('Mediathek list anchor missing')
player=r'''if MoviePlayer is not None:
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


'''
t=t.replace(anchor,player+anchor,1)

old='''            if MoviePlayer is not None:
                self.session.open(MoviePlayer,ref)
                _mediathek_debug("play_opened_standard", title)
            else:
                self.session.nav.playService(ref)
                _mediathek_debug("play_started_nav", title)
'''
new='''            if EpiMediathekPlayer is not None:
                self.session.open(EpiMediathekPlayer,ref)
                _mediathek_debug("play_opened_mediathek", title)
            else:
                self.session.nav.playService(ref)
                _mediathek_debug("play_started_nav", title)
'''
if old not in t:
    raise SystemExit('v0.9.28 MoviePlayer playback block missing')
t=t.replace(old,new,1)

p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.29/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.29 direct EXIT from Mediathek streams/' "$T/control/control"

python3 -m py_compile "$P"
grep -q 'PLUGIN_VERSION = "0.9.29"' "$P"
grep -q 'class EpiMediathekPlayer(MoviePlayer)' "$P"
grep -q 'fromMovieSelection=False' "$P"
grep -q '"leavePlayerOnExit":self.epiExit' "$P"
grep -q '"cancel":self.epiExit' "$P"
grep -q 'play_opened_mediathek' "$P"
# Rai stays PIN-free; unrelated Family/parental features stay intact.
grep -q 'FAMILY_PIN_HASH' "$P"
grep -q 'family_skins_unlocked' "$P"
grep -q '_familyPinEntered' "$P"
python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
a=t.index('class EpiMediathekDirectory(Screen):'); b=t.index('class EpiMediathekList(Screen):',a); d=t[a:b]
if 'Family · Rai International' in d or '_pin_done' in d:
    raise SystemExit('Rai PIN gate returned')
p=t[t.index('class EpiMediathekPlayer(MoviePlayer):'):t.index('class EpiMediathekList(Screen):')]
for needle in ('fromMovieSelection=False','leavePlayerOnExit','cancel','self.close()'):
    if needle not in p: raise SystemExit('Player exit guard missing: '+needle)
print('v0.9.29 Mediathek EXIT guard: OK')
PY

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.29.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"
if ar p EpiMediaHub_v0.9.29.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.29.ipk)
echo "v0.9.29 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.29.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.29.ipk" > EpiMediaHub_v0.9.29.ipk.sha256
printf '{\n  "version": "0.9.29",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.29.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.29.ipk.sha256
rm -f EpiMediaHub_v0.9.28.ipk EpiMediaHub_v0.9.28.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.29 Mediathek direct exit'
git push
