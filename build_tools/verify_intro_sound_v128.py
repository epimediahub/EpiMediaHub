#!/usr/bin/env python3
import math
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path

def read(path):
    with wave.open(str(path), 'rb') as source:
        assert (source.getframerate(), source.getnchannels(), source.getsampwidth(), source.getnframes()) == (48000, 2, 2, 278400)
        samples = array('h', source.readframes(source.getnframes()))
        if sys.byteorder != 'little': samples.byteswap()
        return samples

values = read(Path(sys.argv[1]))
with tempfile.TemporaryDirectory() as temporary:
    old = Path(temporary) / 'old.wav'
    subprocess.run([sys.executable, str(Path(__file__).with_name('generate_intro_sound_v127.py')), str(old)], check=True)
    previous = read(old)
assert values[:round(4.42 * 48000) * 2] == previous[:round(4.42 * 48000) * 2]
assert max(map(abs, values)) < 30000
assert all(value == 0 for value in values[-200:])
def rms(samples): return math.sqrt(sum(float(v) ** 2 for v in samples) / len(samples))
section = slice(round(4.43 * 48000) * 2, round(4.75 * 48000) * 2)
gain = 20 * math.log10(rms(values[section]) / rms(previous[section]))
assert gain > 6.0, f'Final accent too weak: {gain:.1f}dB'
print(f'Final heartbeat verified: {gain:.1f}dB stronger, earlier scenes identical, no clipping or abrupt tail')
