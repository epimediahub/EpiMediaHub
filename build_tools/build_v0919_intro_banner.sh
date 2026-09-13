#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"
ROOT=/tmp/epimedia0919/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub
PLUGIN="$ROOT/plugin.py"

rm -rf /tmp/epimedia0919
mkdir -p /tmp/epimedia0919/{ar,data,control,pkg}
cd /tmp/epimedia0919/ar
ar x "$WORKSPACE/EpiMediaHub_v0.9.18.ipk"
tar -xzf data.tar.gz -C ../data
tar -xzf control.tar.gz -C ../control
cp debian-binary ../pkg/debian-binary

python3 -m pip install --quiet pillow
export ROOT PLUGIN
python3 - <<'PY'
import json, math, os, random, struct, wave
from pathlib import Path
from PIL import Image

root = Path(os.environ['ROOT'])
theme_dir = root / 'themes'
banner_dir = theme_dir / 'banner_marks'
banner_dir.mkdir(parents=True, exist_ok=True)

catalog = json.loads((theme_dir / 'catalog.json').read_text(encoding='utf-8'))
themes = catalog.get('themes', {})

# Build a dedicated very-low-opacity mark for the Live-TV banner.  The exit
# dialog and the rest of the UI keep the normal center mark, so readability is
# improved only where EPG text sits on top of the artwork.
for theme_id in themes:
    source = theme_dir / 'center_marks' / ('%s.png' % theme_id)
    if not source.is_file():
        source = theme_dir / 'marks' / ('%s.png' % theme_id)
    if not source.is_file():
        continue
    try:
        image = Image.open(str(source)).convert('RGBA')
        alpha = image.getchannel('A').point(lambda p: int(p * 0.16))
        image.putalpha(alpha)
        # Quantization keeps 115 banner marks compact.
        try:
            image = image.quantize(colors=64, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
        except Exception:
            pass
        image.save(str(banner_dir / ('%s.png' % theme_id)), optimize=True)
    except Exception:
        pass
print('Banner marks:', len(list(banner_dir.glob('*.png'))))

# New 3.2-second Epi signature melody.  Six musical hits are aligned with the
# visual frame milestones (0, 2, 4, 6, 8, 9), followed by one clean final decay.
sr = 44100
duration = 3.2
count = int(sr * duration)
buf = [0.0] * count

# Deterministic original synth motif: E - G# - B - E - B, then an E-major seal.
def env(t, dur, attack=0.018, release=0.24):
    if t < 0 or t >= dur:
        return 0.0
    a = min(1.0, t / max(attack, 1e-6))
    r = min(1.0, (dur - t) / max(release, 1e-6))
    return a * r * math.exp(-1.15 * t / max(dur, 0.001))

def add_note(start, dur, freq, amp=0.28, bell=False):
    s0 = max(0, int(start * sr))
    s1 = min(count, int((start + dur) * sr))
    for i in range(s0, s1):
        t = (i - s0) / float(sr)
        e = env(t, dur)
        phase = 2.0 * math.pi * freq * t
        v = math.sin(phase)
        v += 0.34 * math.sin(phase * 2.0 + 0.10)
        v += 0.13 * math.sin(phase * 3.0 + 0.27)
        if bell:
            v += 0.10 * math.sin(phase * 5.0 + 0.4)
        buf[i] += amp * e * v / 1.57

def add_bass(start, dur, freq, amp=0.19):
    s0 = max(0, int(start * sr)); s1 = min(count, int((start + dur) * sr))
    for i in range(s0, s1):
        t = (i - s0) / float(sr)
        e = env(t, dur, 0.008, 0.30)
        buf[i] += amp * e * (0.78 * math.sin(2*math.pi*freq*t) + 0.22 * math.sin(4*math.pi*freq*t))

# Frame transitions are every 180 ms for the reveal. Hits land on frames 0/2/4/6/8/9.
hits = [
    (0.00, 0.34, 329.63, 0.24),  # E4
    (0.36, 0.36, 415.30, 0.25),  # G#4
    (0.72, 0.38, 493.88, 0.27),  # B4
    (1.08, 0.42, 659.25, 0.28),  # E5
    (1.44, 0.46, 987.77, 0.24),  # B5
]
for start, dur, freq, amp in hits:
    add_note(start, dur, freq, amp, bell=True)

# Final musical logo at frame 9 (1.62 s), with a longer, memorable resolve.
for freq, amp in ((659.25,0.23),(830.61,0.18),(987.77,0.17)):
    add_note(1.62, 1.45, freq, amp, bell=True)
add_bass(0.00, 0.46, 82.41, 0.14)   # E2 opening pulse
add_bass(1.62, 1.20, 82.41, 0.18)   # final seal

# Subtle airy rise into the final logo, deterministic and intentionally quiet.
rng = random.Random(1919)
for i in range(int(1.10*sr), int(1.66*sr)):
    t = i / float(sr)
    x = (t - 1.10) / 0.56
    noise = (rng.random() * 2.0 - 1.0)
    buf[i] += noise * 0.018 * x * x

peak = max(0.001, max(abs(x) for x in buf))
gain = 0.88 / peak
wav_path = root / 'intro_sound.wav'
with wave.open(str(wav_path), 'wb') as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sr)
    frames = bytearray()
    for x in buf:
        v = max(-1.0, min(1.0, x * gain))
        frames.extend(struct.pack('<h', int(v * 32767.0)))
    wf.writeframes(bytes(frames))
print('Intro WAV:', wav_path.stat().st_size, 'bytes')
PY

python3 - <<'PY'
import os, re
from pathlib import Path

p = Path(os.environ['PLUGIN'])
t = p.read_text(encoding='utf-8')

def once(old, new, label):
    global t
    n = t.count(old)
    if n != 1:
        raise SystemExit('%s: expected 1 match, got %d' % (label, n))
    t = t.replace(old, new, 1)

once('PLUGIN_VERSION = "0.9.18"', 'PLUGIN_VERSION = "0.9.19"', 'version')
once(
    'ACTIVE_THEME_HOME_MOTIF = "/tmp/epimediahub_active_home_motif.png"\n',
    'ACTIVE_THEME_HOME_MOTIF = "/tmp/epimediahub_active_home_motif.png"\nACTIVE_THEME_BANNER_MARK = "/tmp/epimediahub_active_banner_mark.png"\n',
    'banner path'
)
once(
    '    home_source = os.path.join(THEME_DIR, "home_motifs", "%s.png" % theme_id)\n',
    '    home_source = os.path.join(THEME_DIR, "home_motifs", "%s.png" % theme_id)\n    banner_source = os.path.join(THEME_DIR, "banner_marks", "%s.png" % theme_id)\n',
    'banner source'
)
once(
    '        for src, dst in ((source, ACTIVE_THEME_BACKGROUND), (mark_source, ACTIVE_THEME_MARK), (home_source, ACTIVE_THEME_HOME_MOTIF)):\n',
    '        for src, dst in ((source, ACTIVE_THEME_BACKGROUND), (mark_source, ACTIVE_THEME_MARK), (home_source, ACTIVE_THEME_HOME_MOTIF), (banner_source, ACTIVE_THEME_BANNER_MARK)):\n',
    'banner copy'
)

# Use the dedicated 16%-opacity artwork in the Live-TV banner and keep it farther
# to the right/smaller so channel and EPG text remain dominant.
once(
    "    '<ePixmap position=\"%s\" size=\"%s\" pixmap=\"%s\" alphatest=\"blend\" scale=\"1\" zPosition=\"0\" />' % (pos(930, 12), size(300, 196), ACTIVE_THEME_CENTER_MARK) +\n",
    "    '<ePixmap position=\"%s\" size=\"%s\" pixmap=\"%s\" alphatest=\"blend\" scale=\"1\" zPosition=\"0\" />' % (pos(1010, 20), size(230, 180), ACTIVE_THEME_BANNER_MARK) +\n",
    'live banner mark'
)

# Explicit frame timing: 9 reveal transitions x 180 ms = 1.62 s, then the final
# logo holds for 1.58 s. Total visual duration is exactly the 3.20 s WAV length.
old_start = '''    def startTimer(self):
        self._frame = 0
        if not self._paintFrame():
            self.finish()
            return
        # Paint the first frame before changing the nav service.  This avoids a
        # short black flash on slower boxes and makes the audio start deterministic.
        self._startIntroAudio()
        self._scheduleNext(260)
'''
new_start = '''    def startTimer(self):
        self._frame = 0
        if not self._paintFrame():
            self.finish()
            return
        # v0.9.19: sound and visuals share the same 3.20 s timeline.
        # The melody hits frames 0/2/4/6/8/9 and the final chord decays while
        # the completed logo remains on screen.
        self._startIntroAudio()
        self._scheduleNext(180)
'''
once(old_start, new_start, 'intro start timing')

old_next = '''        # The supplied intro sound is about 3.9 seconds long. Keep the final
        # logo visible long enough for the sound to finish cleanly.
        self._scheduleNext(1600 if self._frame == len(INTRO_FRAMES) - 1 else 250)
'''
new_next = '''        # Frames 1-9 advance on a strict 180 ms beat grid. Once frame 9 is
        # visible, hold it for 1.58 s so animation and the 3.20 s signature
        # melody end together.
        self._scheduleNext(1580 if self._frame == len(INTRO_FRAMES) - 1 else 180)
'''
once(old_next, new_next, 'intro frame timing')

notes_anchor = '_RELEASE_NOTES = {\n'
notes = '''_RELEASE_NOTES = {
    "0.9.19": {
        "de": ["Senderbanner besser lesbar: Das Skin-Logo ist deutlich transparenter, kleiner und weiter rechts platziert.", "Intro neu synchronisiert: 10 Animationsframes und eine neue markantere Epi-Signaturmelodie laufen jetzt auf derselben 3,2-Sekunden-Zeitleiste."],
        "en": ["Improved Live-TV banner readability: the skin logo is much more transparent, smaller and moved farther right.", "Intro resynced: all 10 animation frames and a new, more memorable Epi signature melody now share the same 3.2-second timeline."],
        "tr": ["Canlı TV bandı daha okunaklı: tema logosu daha şeffaf, daha küçük ve daha sağda.", "Giriş yeniden senkronize edildi: 10 animasyon karesi ve yeni, daha akılda kalıcı Epi melodisi aynı 3,2 saniyelik zaman çizgisinde ilerliyor."],
        "it": ["Banner Live-TV più leggibile: il logo del tema è molto più trasparente, più piccolo e spostato a destra.", "Intro risincronizzata: i 10 fotogrammi e la nuova melodia Epi più riconoscibile condividono ora la stessa timeline di 3,2 secondi."],
        "es": ["Banner de TV en directo más legible: el logo del tema es mucho más transparente, pequeño y está más a la derecha.", "Intro resincronizada: los 10 fotogramas y una nueva melodía Epi más reconocible comparten ahora la misma línea temporal de 3,2 segundos."]
    },
'''
if notes_anchor not in t:
    raise SystemExit('release notes anchor missing')
t = t.replace(notes_anchor, notes, 1)

p.write_text(t, encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.19/' /tmp/epimedia0919/control/control
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.19 intro sync and banner readability/' /tmp/epimedia0919/control/control

python3 -m py_compile "$PLUGIN"
grep -q 'PLUGIN_VERSION = "0.9.19"' "$PLUGIN"
grep -q 'ACTIVE_THEME_BANNER_MARK' "$PLUGIN"
grep -q 'self._scheduleNext(180)' "$PLUGIN"
grep -q 'self._scheduleNext(1580 if self._frame == len(INTRO_FRAMES) - 1 else 180)' "$PLUGIN"

# Verify generated WAV is exactly 3.2 seconds at 44.1kHz mono 16-bit PCM.
python3 - <<'PY'
import os, wave
path=os.path.join(os.environ['ROOT'],'intro_sound.wav')
with wave.open(path,'rb') as w:
    duration=w.getnframes()/float(w.getframerate())
    print('Intro duration: %.3f s, rate=%d, channels=%d' % (duration,w.getframerate(),w.getnchannels()))
    if abs(duration-3.2) > 0.01 or w.getframerate()!=44100 or w.getnchannels()!=1:
        raise SystemExit('Unexpected intro WAV format/timing')
PY

tar --owner=0 --group=0 -czf /tmp/epimedia0919/pkg/control.tar.gz -C /tmp/epimedia0919/control .
tar --owner=0 --group=0 -czf /tmp/epimedia0919/pkg/data.tar.gz -C /tmp/epimedia0919/data .
cd /tmp/epimedia0919/pkg
ar r "$WORKSPACE/EpiMediaHub_v0.9.19.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$WORKSPACE"

SIZE=$(stat -c%s EpiMediaHub_v0.9.19.ipk)
echo "v0.9.19 size: $SIZE bytes"
if [ "$SIZE" -gt 25165824 ]; then
    echo "ERROR: v0.9.19 exceeds 24 MiB guard" >&2
    exit 1
fi
SHA=$(sha256sum EpiMediaHub_v0.9.19.ipk | awk '{print $1}')
echo "$SHA  EpiMediaHub_v0.9.19.ipk" > EpiMediaHub_v0.9.19.ipk.sha256
python3 - <<PY
import json
p='update.json'
d=json.load(open(p,encoding='utf-8'))
d['version']='0.9.19'
d['url']='https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.19.ipk'
d['sha256']='$SHA'
open(p,'w',encoding='utf-8').write(json.dumps(d,indent=2)+'\n')
PY
sha256sum -c EpiMediaHub_v0.9.19.ipk.sha256

rm -f EpiMediaHub_v0.9.18.ipk EpiMediaHub_v0.9.18.ipk.sha256
rm -rf inspection
rm -f .github/workflows/inspect-enigma-v0918-intro.yml

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A EpiMediaHub_v0.9.18.ipk EpiMediaHub_v0.9.18.ipk.sha256 EpiMediaHub_v0.9.19.ipk EpiMediaHub_v0.9.19.ipk.sha256 update.json inspection .github/workflows/inspect-enigma-v0918-intro.yml
git commit -m 'Publish EpiMediaHub v0.9.19 intro and banner polish'
git push
