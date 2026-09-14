#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.38.ipk"
T=/tmp/epimedia0939
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

if 'PLUGIN_VERSION = "0.9.38"' not in t:
    raise SystemExit('Expected v0.9.38 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.38"','PLUGIN_VERSION = "0.9.39"',1)

def replace_exact(old,new,count,label):
    global t
    found=t.count(old)
    if found != count:
        raise SystemExit('%s: expected %d matches, got %d' % (label,count,found))
    t=t.replace(old,new,count)

# OpenATV 7.6 compatibility: remote EpiMediaHub playback now uses service type 1.
# This forces the native Enigma2/GStreamer path instead of the replaceable 4097
# ServiceMP3 path. Keep the local intro WAV and timer/recording service refs on
# 4097 because those are different use cases and were not part of the silent
# Live/VOD/Mediathek report.
replace_exact('eServiceReference(4097, 0, next_url)',
              'eServiceReference(1, 0, next_url)',1,'series EOF next stream')
replace_exact('eServiceReference(4097, 0, target_url)',
              'eServiceReference(1, 0, target_url)',1,'series manual switch')
replace_exact('eServiceReference(4097, 0, entry.get("url", ""))',
              'eServiceReference(1, 0, entry.get("url", ""))',1,'live stream')
replace_exact('eServiceReference(4097,0,url)',
              'eServiceReference(1,0,url)',2,'mediathek and replay streams')
replace_exact('eServiceReference(4097, 0, entry.get("url"))',
              'eServiceReference(1, 0, entry.get("url"))',1,'VOD initial stream')

notes='''_RELEASE_NOTES = {\n    "0.9.39": {\n        "de": ["Audio-Kompatibilitätsfix für OpenATV 7.6: Live-TV, Filme/Serien, Replay und Mediathek nutzen für Remote-Streams jetzt den nativen Enigma2/GStreamer-Pfad (Service-Typ 1) statt des ersetzbaren 4097-Playerpfads.", "Intro-Audio, Aufnahmen/Timer, Mediathek-Navigation, EPG/Catchup, Family-PIN und alle Einstellungen aus v0.9.38 bleiben unverändert."],\n        "en": ["OpenATV 7.6 audio compatibility fix: Live TV, movies/series, replay and Mediathek remote streams now use the native Enigma2/GStreamer path (service type 1) instead of the replaceable 4097 player path.", "Intro audio, recording/timers, Mediathek navigation, EPG/catchup, Family PIN and all v0.9.38 settings remain unchanged."],\n        "tr": ["OpenATV 7.6 ses uyumluluk düzeltmesi: Canlı TV, film/dizi, tekrar ve Mediathek uzak akışları artık değiştirilebilir 4097 oynatıcı yolu yerine yerel Enigma2/GStreamer yolunu (servis tipi 1) kullanıyor.", "Giriş sesi, kayıt/zamanlayıcı, Mediathek gezinmesi, EPG/Catchup, Family PIN ve v0.9.38 ayarları değişmedi."],\n        "it": ["Correzione compatibilità audio OpenATV 7.6: TV live, film/serie, replay e flussi remoti Mediathek usano ora il percorso nativo Enigma2/GStreamer (tipo servizio 1) invece del percorso 4097 sostituibile.", "Audio intro, registrazioni/timer, navigazione Mediathek, EPG/Catchup, Family PIN e impostazioni v0.9.38 restano invariati."],\n        "es": ["Corrección de compatibilidad de audio para OpenATV 7.6: TV en directo, películas/series, replay y flujos remotos de Mediathek usan ahora la ruta nativa Enigma2/GStreamer (tipo de servicio 1) en lugar de la ruta 4097 reemplazable.", "Audio de introducción, grabaciones/temporizadores, navegación Mediathek, EPG/Catchup, Family PIN y ajustes de v0.9.38 permanecen sin cambios."],\n    },'''
if '_RELEASE_NOTES = {' not in t:
    raise SystemExit('Release notes anchor missing')
t=t.replace('_RELEASE_NOTES = {',notes,1)

p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.39/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.39 OpenATV native stream audio compatibility/' "$T/control/control"

python3 -m py_compile "$P"

# Audio/backend guards: exactly six remote playback refs are native type 1.
grep -Fq 'PLUGIN_VERSION = "0.9.39"' "$P"
python3 - <<'PY'
import os,re
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
if len(re.findall(r'eServiceReference\(\s*1\s*,',t)) != 6:
    raise SystemExit('Expected exactly six native type-1 playback refs')
for forbidden in (
    'eServiceReference(4097, 0, next_url)',
    'eServiceReference(4097, 0, target_url)',
    'eServiceReference(4097, 0, entry.get("url", ""))',
    'eServiceReference(4097,0,url)',
    'eServiceReference(4097, 0, entry.get("url"))',
):
    if forbidden in t:
        raise SystemExit('Old 4097 remote playback ref remains: '+forbidden)
# Local intro and recording/timer path deliberately remain on 4097.
if 'eServiceReference(4097, 0, INTRO_SOUND)' not in t:
    raise SystemExit('Intro local service ref changed unexpectedly')
if 'eServiceReference(4097, 0, url)' not in t:
    raise SystemExit('Recording/timer service ref changed unexpectedly')
print('v0.9.39 native stream backend guard: OK')
PY

# Critical existing features/fixes must survive unchanged.
grep -Fq 'class EpiMediathekPlayer(MoviePlayer)' "$P"
grep -Fq 'directory_back_parent_ok' "$P"
grep -Fq 'list_back_parent_ok' "$P"
grep -Fq 'home_back_parent_ok' "$P"
grep -Fq 'class EpiEPGGridScreen(Screen)' "$P"
grep -Fq 'def xtream_catchup_url' "$P"
grep -Fq 'RecordTimerEntry' "$P"
grep -Fq 'class EpiWebPlaylistSetup(Screen)' "$P"
grep -Fq 'def _playlist_web_generate_qr' "$P"
grep -Fq 'FAMILY_PIN_HASH' "$P"
grep -Fq 'family_skins_unlocked' "$P"
grep -Fq 'parental_pin_hash' "$P"
grep -Fq 'list_widget("list",160,130,570,465,23,50)' "$P"
grep -Fq 'self["list"]=MenuList([x["label"] for x in self.items])' "$P"

python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
# Rai app-local PIN stays absent while unrelated Family/parental controls remain.
ms=t.index('class EpiMediathekHome(Screen):'); me=t.index('class EpiMediaHubHome(Screen):',ms); m=t[ms:me]
if '_pin_done' in m or ('Rai' in m and 'openWithCallback(self._pin' in m):
    raise SystemExit('Rai provider PIN gate reintroduced')
print('v0.9.39 regression guards: OK')
PY

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.39.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"

if ar p EpiMediaHub_v0.9.39.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.39.ipk)
echo "v0.9.39 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.39.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.39.ipk" > EpiMediaHub_v0.9.39.ipk.sha256
printf '{\n  "version": "0.9.39",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.39.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.39.ipk.sha256
rm -f EpiMediaHub_v0.9.38.ipk EpiMediaHub_v0.9.38.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.39 native stream audio compatibility'
git push
